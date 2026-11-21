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
