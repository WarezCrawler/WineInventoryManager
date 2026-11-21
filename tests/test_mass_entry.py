"""Mass registration of stock changes: reading pasted rows, finding wines by id or code, saving all or nothing."""
import pytest

from winedb.db import connect
from winedb.mass_entry import check, parse
from winedb.masterdata import find_item_by_code, resolve_item
from winedb.stock import add_movements, on_hand
from winedb.validation import ValidationError, is_timestamp


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    c.executescript("""
        INSERT INTO items (item_id, item_code, name, vintage) VALUES
            (182, '182', 'La Cote', 2009), (216, '216_fejl', 'Olivar', 2007), (300, 'SAbSe_RA09', 'Seleccion', 2009),
            (7, '300', 'Clash', 2001);
        INSERT INTO warehouses (warehouse_id, warehouse_name) VALUES (1, 'Main'), (2, 'Fridge');
    """)
    yield c
    c.close()


def stock_rows(conn):
    return conn.execute("SELECT item_id, warehouse_id, quantity, comment, created_at FROM stock_transactions ORDER BY stock_line_id").fetchall()


# --- finding a wine ---

def test_code_is_found_ignoring_case(conn):
    assert find_item_by_code(conn, " sabse_ra09 ")["item_id"] == 300
    assert find_item_by_code(conn, "nope") is None


@pytest.mark.parametrize("key, item_id", [("216", 216), ("216_fejl", 216), ("SAbSe_RA09", 300), ("182", 182)])
def test_wine_by_id_or_code(conn, key, item_id):
    item, problem = resolve_item(conn, key)
    assert problem is None and item["item_id"] == item_id


def test_a_number_that_is_an_id_and_another_wines_code_is_refused(conn):
    item, problem = resolve_item(conn, "300")       # id of SAbSe_RA09, code of wine 7
    assert item is None and "Use the code" in problem


@pytest.mark.parametrize("key", ["", "999", "XYZ"])
def test_unknown_wine(conn, key):
    assert resolve_item(conn, key)[0] is None


# --- reading pasted text ---

def test_excel_paste_with_heading_and_empty_lines():
    text = "Lager_ID\tVin_ID\tQuantity\tKommentar\n1\t216\t6\tDelivery 42\n\n2\tSAbSe_RA09\t-2\t\n"
    assert parse(text) == [(2, ["1", "216", "6", "Delivery 42"]), (4, ["2", "SAbSe_RA09", "-2", ""])]


def test_semicolons_without_tabs():
    assert parse("1;216;6;Ok") == [(1, ["1", "216", "6", "Ok"])]


def test_check_gives_rows_preview_and_no_problems(conn):
    rows, preview, problems = check(conn, "1\t216\t6\tDelivery\n2\tsabse_ra09\t-2")
    assert problems == []
    assert rows == [{"warehouse_id": 1, "item_id": 216, "quantity": 6, "comment": "Delivery"},
                    {"warehouse_id": 2, "item_id": 300, "quantity": -2, "comment": ""}]
    assert [(p["line"], p["warehouse"], p["wine"], p["status"]) for p in preview] == [
        (1, "Main", "216_fejl – Olivar 2007", "OK"), (2, "Fridge", "SAbSe_RA09 – Seleccion 2009", "OK")]


def test_check_reports_every_problem_with_its_line(conn):
    rows, preview, problems = check(conn, "1\t216\t6\n9\tXYZ\t0\n1\t300\t1.5\n1\t216\t1\tok\textra")
    assert len(rows) == 1
    assert [p["status"] for p in preview] == ["OK", "Problem", "Problem", "Problem"]
    assert any(p.startswith("Line 2: no warehouse") for p in problems)
    assert any(p.startswith("Line 2: no wine has") for p in problems)
    assert any(p.startswith("Line 2: the quantity '0'") for p in problems)
    assert any(p.startswith("Line 3:") and "Use the code" in p for p in problems)
    assert any(p.startswith("Line 3: the quantity '1.5'") for p in problems)
    assert any(p.startswith("Line 4: too many columns") for p in problems)


def test_nothing_pasted(conn):
    assert check(conn, "  \n")[2] == ["Paste at least one row."]


# --- saving all or nothing ---

def test_all_rows_are_saved_with_the_same_date(conn):
    ids = add_movements(conn, [{"warehouse_id": 1, "item_id": 216, "quantity": 6, "comment": "In"},
                               {"warehouse_id": 1, "item_id": 216, "quantity": -2}])
    assert len(ids) == 2 and on_hand(conn, 216, 1) == 4
    saved = stock_rows(conn)
    assert saved[0][:4] == (216, 1, 6, "In") and saved[1][:4] == (216, 1, -2, None)
    assert saved[0][4] == saved[1][4] and is_timestamp(saved[0][4])


def test_one_bad_row_saves_nothing(conn):
    with pytest.raises(ValidationError) as e:
        add_movements(conn, [{"warehouse_id": 1, "item_id": 216, "quantity": 6},
                             {"warehouse_id": 1, "item_id": 999, "quantity": 0}])
    assert e.value.problems == ["Row 2: Choose a wine.",
                                "Row 2: Enter a whole number other than 0 as the quantity (negative to remove stock)."]
    assert stock_rows(conn) == []


def test_no_rows(conn):
    with pytest.raises(ValidationError):
        add_movements(conn, [])
