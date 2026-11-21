"""Invoice data functions on a small hand-made database."""
from winedb.db import connect
from winedb.invoices import open_invoices


def test_open_invoices_newest_first_with_customer_name(tmp_path):
    conn = connect(tmp_path / "t.db")
    conn.executescript("""
        INSERT INTO customers (customer_id, customer_name) VALUES (7, 'Æble Ørsted');
        INSERT INTO invoice_header (invoice_id, customer_id, is_closed, is_deleted) VALUES
            (1, 7, 0, 0),
            (2, 7, 1, 0),
            (3, 0, 0, 0),
            (4, 7, 0, 1),
            (5, 99, NULL, NULL);
    """)
    assert open_invoices(conn) == [
        {"invoice_id": 5, "customer_id": 99, "customer_name": None, "is_deleted": 0},   # customer missing
        {"invoice_id": 4, "customer_id": 7, "customer_name": "Æble Ørsted", "is_deleted": 1},
        {"invoice_id": 3, "customer_id": 0, "customer_name": None, "is_deleted": 0},    # draft, customer 0
        {"invoice_id": 1, "customer_id": 7, "customer_name": "Æble Ørsted", "is_deleted": 0},
    ]


def test_no_invoices_gives_an_empty_list(tmp_path):
    assert open_invoices(connect(tmp_path / "t.db")) == []
