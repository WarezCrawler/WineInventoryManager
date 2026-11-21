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


# --- the grid: paste placement and rows to check ---

from winedb.mass_entry import blank_row, check_rows, grid_rows_to_check, paste_into, with_new_row  # noqa: E402

EXCEL = "Lager\tVin\tAntal\tKommentar\r\n1\t216\t6\tDelivery 42\r\n2\tSAbSe_RA09\t-2\t\r\n"


def grid(n=3):
    return [blank_row(i) for i in range(1, n + 1)]


def test_excel_block_fills_from_the_first_cell_and_skips_the_heading():
    rows = grid()
    assert paste_into(rows, EXCEL, 0, "warehouse") == 0
    assert [(r["warehouse"], r["wine"], r["quantity"], r["comment"]) for r in rows] == [
        ("1", "216", "6", "Delivery 42"), ("2", "SAbSe_RA09", "-2", ""), ("", "", "", "")]


def test_paste_lower_in_the_grid_grows_it():
    rows = grid(2)
    paste_into(rows, "1\t216\t6\n1\t216\t7\n", 1, "warehouse")
    assert [r["line"] for r in rows] == [1, 2, 3] and rows[2]["quantity"] == "7"


def test_paste_from_the_wine_column_fills_to_the_right_and_counts_what_does_not_fit():
    rows = grid()
    assert paste_into(rows, "216\t6\tok\textra\n", 0, "wine") == 1
    assert (rows[0]["warehouse"], rows[0]["wine"], rows[0]["quantity"], rows[0]["comment"]) == ("", "216", "6", "ok")


def test_one_copied_excel_cell_goes_into_the_selected_cell():
    rows = grid()
    paste_into(rows, "SAbSe_RA09\r\n", 2, "wine")
    assert rows[2]["wine"] == "SAbSe_RA09" and rows[2]["warehouse"] == ""


def test_blank_rows_are_not_checked_and_lines_keep_the_grid_numbers(conn):
    rows = grid(4)
    paste_into(rows, "1\t216\t6\n", 2, "warehouse")
    to_check = grid_rows_to_check(rows)
    assert to_check == [(3, ["1", "216", "6", ""])]
    to_save, preview, problems = check_rows(conn, to_check)
    assert problems == [] and preview[0]["line"] == 3 and preview[0]["problems"] == []


def test_problems_per_row_are_sentences(conn):
    _, preview, problems = check_rows(conn, [(5, ["9", "NOPE", "0", ""])])
    assert preview[0]["problems"][0] == "No warehouse has the id '9'."
    assert problems[0] == "Line 5: no warehouse has the id '9'."


def test_the_grid_always_ends_with_one_new_row():
    tab, nl = chr(9), chr(10)
    assert [r["line"] for r in with_new_row([])] == [1]                       # an empty grid: only the new row
    rows = with_new_row([blank_row(1)])
    paste_into(rows, nl.join(tab.join(["1", "216", q]) for q in ("6", "7", "8")) + nl, 0, "warehouse")
    with_new_row(rows)
    assert len(rows) == 4 and rows[2]["quantity"] == "8" and rows[3]["wine"] == ""   # 3 pasted + 1 new row
    rows += [blank_row(5), blank_row(6)]
    assert len(with_new_row(rows)) == 4                                       # extra empty rows at the end go
