"""on_hand() on a small hand-made database. The golden test (test_golden.py) checks it against the real data."""
import pytest

from winedb.db import connect
from winedb.stock import on_hand


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    c.executescript("""
        INSERT INTO invoice_header (invoice_id, is_deleted) VALUES (1, 0), (2, 1), (3, NULL);
        INSERT INTO stock_transactions (item_id, warehouse_id, quantity) VALUES
            (10, 1, 6), (10, 1, -2), (10, 2, 50), (11, 1, 5), (10, 1, NULL);
        INSERT INTO invoice_lines (item_id, warehouse_id, invoice_id, quantity) VALUES
            (10, 1, 1, 3),
            (10, 1, 2, 100),
            (10, 1, 3, 1),
            (10, 1, 99, 1),
            (10, 2, 1, 4),
            (10, 1, 1, NULL);
    """)
    yield c
    c.close()


def test_movements_minus_sales_for_one_wine_and_warehouse(conn):
    # 6 - 2 received; 3 (invoice 1) + 1 (invoice 3, flag NULL) + 1 (invoice 99, missing) sold.
    # Invoice 2 is soft deleted and does not count. NULL quantities count as 0.
    assert on_hand(conn, 10, 1) == -1


def test_other_warehouses_and_wines_are_separate(conn):
    assert on_hand(conn, 10, 2) == 46
    assert on_hand(conn, 11, 1) == 5


def test_no_rows_gives_zero(conn):
    assert on_hand(conn, 12, 1) == 0


def test_adding_and_removing_stock_changes_on_hand(conn):
    before = on_hand(conn, 11, 1)
    conn.execute("INSERT INTO stock_transactions (item_id, warehouse_id, quantity) VALUES (11, 1, 6)")
    conn.execute("INSERT INTO stock_transactions (item_id, warehouse_id, quantity) VALUES (11, 1, -2)")
    assert on_hand(conn, 11, 1) == before + 4


# --- add_movement() and recent_movements() (design doc §5.5, step 6) ---

from winedb.stock import add_movement, recent_movements  # noqa: E402
from winedb.validation import ValidationError, is_timestamp  # noqa: E402


@pytest.fixture
def master(conn):
    conn.executescript("""
        INSERT INTO items (item_id, item_code, name, vintage) VALUES (10, 'A_10', 'Vin', 2010), (11, 'B_11', 'Vin 2', 2011);
        INSERT INTO warehouses (warehouse_id, warehouse_name) VALUES (1, 'Main'), (2, 'Fridge');
    """)
    return conn


def test_plus_six_and_minus_two_change_on_hand_by_four(master):
    before = on_hand(master, 11, 1)
    first = add_movement(master, 11, 1, 6, created_at="2026-11-20 10:00:00")
    second = add_movement(master, 11, 1, -2, "Broken bottles", created_at="2026-11-21 09:30:00")
    assert on_hand(master, 11, 1) == before + 4
    rows = {r["stock_line_id"]: dict(r) for r in master.execute(
        "SELECT * FROM stock_transactions WHERE stock_line_id IN (?, ?)", (first, second))}
    assert rows[first] == {"stock_line_id": first, "created_at": "2026-11-20 10:00:00", "item_id": 11, "quantity": 6,
                           "comment": None, "warehouse_id": 1}
    assert rows[second]["created_at"] == "2026-11-21 09:30:00" and rows[second]["comment"] == "Broken bottles"


def test_date_is_now_when_not_given(master):
    line = add_movement(master, 11, 2, 1)
    assert is_timestamp(master.execute("SELECT created_at FROM stock_transactions WHERE stock_line_id = ?", (line,)).fetchone()[0])


def test_whole_float_quantity_from_the_screen_is_stored_as_an_integer(master):
    line = add_movement(master, 11, 1, 3.0)
    assert master.execute("SELECT typeof(quantity) FROM stock_transactions WHERE stock_line_id = ?", (line,)).fetchone()[0] == "integer"


def test_every_problem_is_reported_and_nothing_is_written(master):
    count = master.execute("SELECT COUNT(*) FROM stock_transactions").fetchone()[0]
    with pytest.raises(ValidationError) as e:
        add_movement(master, 999, 9, 0, created_at="21-11-2026")
    assert len(e.value.problems) == 4   # wine, warehouse, quantity, date
    assert master.execute("SELECT COUNT(*) FROM stock_transactions").fetchone()[0] == count


@pytest.mark.parametrize("quantity", [0, 1.5, None, True, "6"])
def test_quantity_must_be_a_whole_number_other_than_zero(master, quantity):
    with pytest.raises(ValidationError):
        add_movement(master, 11, 1, quantity)


def test_an_empty_comment_is_stored_as_null(master):
    line = add_movement(master, 11, 1, 1, "   ")
    assert master.execute("SELECT comment FROM stock_transactions WHERE stock_line_id = ?", (line,)).fetchone()[0] is None


def test_recent_movements_newest_first(master):
    master.execute("INSERT INTO stock_transactions (item_id, warehouse_id, quantity, created_at) VALUES (11, 1, 12, '2013-06-21 00:00:05')")
    master.execute("INSERT INTO stock_transactions (item_id, warehouse_id, quantity, created_at) VALUES (11, 1, 1, NULL)")
    add_movement(master, 11, 1, -1, created_at="2026-11-21 08:00:00")
    rows = recent_movements(master, 11, 1)
    # Newest first; rows without a date (the fixture has one: 5) come last, newest of them first.
    assert [r["quantity"] for r in rows] == [-1, 12, 1, 5]
    assert len(recent_movements(master, 11, 1, limit=2)) == 2


# --- wines offered on the stock change screen (owner decision 2026-11-21) ---

from winedb.stock import on_hand_by_item, on_hand_table, wines_for_stock_change  # noqa: E402


def test_on_hand_table_and_totals_use_the_same_formula(conn):
    table = on_hand_table(conn)
    assert table[(10, 1)] == on_hand(conn, 10, 1) == -1 and table[(10, 2)] == 46 and table[(11, 1)] == 5
    assert on_hand_by_item(conn) == {10: 45, 11: 5}


def test_discontinued_wines_without_stock_are_hidden(conn):
    conn.executescript("""
        INSERT INTO items (item_id, item_code, name, vintage, is_discontinued) VALUES
            (10, 'b_active', 'A', 2010, 0),
            (11, 'C_GONE_WITH_STOCK', 'B', 2011, 1),
            (12, 'A_GONE_EMPTY', 'C', 2012, 1),
            (13, 'D_GONE_NEGATIVE', 'D', 2013, 1),
            (14, 'a_active_empty', 'E', 2014, 0),
            (15, 'E_GONE_NETS_TO_ZERO', 'F', 2015, 1);
        INSERT INTO stock_transactions (item_id, warehouse_id, quantity) VALUES (13, 1, -2), (15, 1, 5), (15, 2, -5);
    """)
    wines = wines_for_stock_change(conn)
    # Active wines first (by code, ignoring case), then discontinued wines with stock other than 0.
    assert [w["item_code"] for w in wines] == ["a_active_empty", "b_active", "C_GONE_WITH_STOCK", "D_GONE_NEGATIVE"]
    assert [w["on_hand_total"] for w in wines] == [0, 45, 5, -2]
