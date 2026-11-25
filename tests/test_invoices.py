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


# --- Invoice header (step 7) ---

from datetime import date  # noqa: E402

import pytest  # noqa: E402

from winedb.invoices import (InvoiceClosedError, close, create_header, date_text, get_header,  # noqa: E402
                             set_deleted, update_header)
from winedb.masterdata import list_customers  # noqa: E402
from winedb.validation import ValidationError  # noqa: E402


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    c.executescript("""
        INSERT INTO customers (customer_id, customer_name, address, postal_code, city, phone, is_hidden) VALUES
            (7, 'Æble Ørsted', 'Vej 1', 8000, 'Århus', '1234', 0),
            (8, 'aage', NULL, NULL, NULL, NULL, 0),
            (9, 'Hidden', NULL, NULL, NULL, NULL, 1),
            (10, 'Bent', NULL, NULL, NULL, NULL, NULL);
        INSERT INTO warehouses (warehouse_id, warehouse_name) VALUES (1, 'Main'), (2, 'Fridge');
        INSERT INTO invoice_header (invoice_id, customer_id, is_closed, warehouse_id, invoice_date)
            VALUES (54, 0, 0, NULL, NULL), (60, 7, 1, 1, '2014-01-02 00:00:00');
    """)
    yield c
    c.close()


def stored(conn, invoice_id):
    return dict(conn.execute("SELECT * FROM invoice_header WHERE invoice_id = ?", (invoice_id,)).fetchone())


def test_create_edit_flag_and_close_store_the_row_as_access_would(conn):
    # Design doc §8 step 7: create, edit, set the delete flag, close.
    number = create_header(conn, 7, warehouse_id=1, invoice_date="2026-11-21", comment=" First ")
    assert number == 61                                    # the next number after the highest
    assert stored(conn, number) == {"invoice_id": 61, "customer_id": 7, "is_closed": 0, "comment": "First",
                                    "warehouse_id": 1, "invoice_date": "2026-11-21 00:00:00",
                                    "hide_subtotals": 0, "is_deleted": 0}
    update_header(conn, number, {"warehouse_id": 2, "hide_subtotals": True, "comment": ""})
    set_deleted(conn, number, True)
    close(conn, number)
    assert stored(conn, number) == {"invoice_id": 61, "customer_id": 7, "is_closed": 1, "comment": None,
                                    "warehouse_id": 2, "invoice_date": "2026-11-21 00:00:00",
                                    "hide_subtotals": 1, "is_deleted": 1}


def test_new_invoice_is_dated_today_by_default(conn):
    number = create_header(conn, 7)
    assert stored(conn, number)["invoice_date"] == date.today().strftime("%Y-%m-%d 00:00:00")
    assert stored(conn, number)["warehouse_id"] is None    # optional, as in Access


@pytest.mark.parametrize("customer", [None, 0, 99])
def test_new_invoice_needs_a_customer(conn, customer):
    with pytest.raises(ValidationError, match="Choose a customer"):
        create_header(conn, customer)


def test_every_problem_is_reported_and_nothing_is_written(conn):
    count = conn.execute("SELECT COUNT(*) FROM invoice_header").fetchone()[0]
    with pytest.raises(ValidationError) as e:
        create_header(conn, 0, warehouse_id=9, invoice_date="21-11-2026")
    assert len(e.value.problems) == 3
    assert conn.execute("SELECT COUNT(*) FROM invoice_header").fetchone()[0] == count


def test_old_draft_with_customer_0_can_be_edited_without_a_customer(conn):
    update_header(conn, 54, {"comment": "Still a draft"})    # only the changed field is checked
    assert stored(conn, 54)["comment"] == "Still a draft" and stored(conn, 54)["customer_id"] == 0
    with pytest.raises(ValidationError):
        update_header(conn, 54, {"customer_id": 0})          # but a changed customer must be real
    update_header(conn, 54, {"customer_id": 8})
    assert stored(conn, 54)["customer_id"] == 8


def test_a_closed_invoice_cannot_be_changed(conn):
    before = stored(conn, 60)
    for action in (lambda: update_header(conn, 60, {"comment": "x"}), lambda: set_deleted(conn, 60, True),
                   lambda: close(conn, 60)):
        with pytest.raises(InvoiceClosedError):
            action()
    assert stored(conn, 60) == before


def test_delete_flag_can_be_removed_again(conn):
    set_deleted(conn, 54, True)
    set_deleted(conn, 54, False)
    assert stored(conn, 54)["is_deleted"] == 0


def test_header_shows_customer_and_warehouse(conn):
    h = get_header(conn, 60)
    assert (h["customer_name"], h["address"], h["postal_code"], h["city"], h["phone"], h["warehouse_name"]) == (
        "Æble Ørsted", "Vej 1", 8000, "Århus", "1234", "Main")
    assert get_header(conn, 54)["customer_name"] is None and get_header(conn, 999) is None


def test_date_text():
    assert date_text("2026-11-21") == date_text(date(2026, 11, 21)) == "2026-11-21 00:00:00"
    assert date_text("") is None
    with pytest.raises(ValueError):
        date_text("21-11-2026")


def test_customer_picker_lists_customers_that_are_not_hidden_by_name(conn):
    assert [c["customer_name"] for c in list_customers(conn)] == ["aage", "Bent", "Æble Ørsted"]
