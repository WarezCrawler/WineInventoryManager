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


# --- Invoice lines (step 8) ---

from winedb.invoices import cancel_line, cost_prices, lines, sales_prices, save_line, totals  # noqa: E402
from winedb.logic import default_cost  # noqa: E402
from winedb.stock import on_hand  # noqa: E402


@pytest.fixture
def sale(conn):
    conn.executescript("""
        INSERT INTO items (item_id, item_code, name, vintage) VALUES (100, 'SAbSe_RA09', 'Seleccion', 2009), (101, 'X', 'Other', 2010);
        INSERT INTO prices_sales (sales_price_id, item_id, price_type, sales_price, vat_rate) VALUES
            (1, 100, 'Alm', 165, 0.25), (2, 100, 'Tilbud', 150, 0.25), (3, 101, '0P', 99.5, 0);
        INSERT INTO prices_cost (cost_price_id, item_id, price_type, cost_price) VALUES
            (5, 100, 'rå', 70), (7, 100, 'standard', 82.5), (6, 100, 'Standard', 80);
        INSERT INTO stock_transactions (item_id, warehouse_id, quantity) VALUES (100, 1, 24);
    """)
    number = create_header(conn, 7, warehouse_id=1)
    return conn, number


def line(**fields):
    base = {"item_id": 100, "warehouse_id": 1, "quantity": 2, "sales_price": 165, "price_type": "Alm",
            "vat_rate": 0.25, "discount": 0, "cost_price": 80}
    return {**base, **fields}


def test_default_cost_is_the_first_standard_row():
    assert default_cost([{"cost_price_id": 5, "price_type": "rå", "cost_price": 70},
                         {"cost_price_id": 7, "price_type": "standard", "cost_price": 82.5},
                         {"cost_price_id": 6, "price_type": "Standard", "cost_price": 80}]) == 80
    assert default_cost([{"cost_price_id": 5, "price_type": "rå", "cost_price": 70}]) == 0
    assert default_cost([]) == 0


def test_price_lists_of_a_wine(sale):
    conn, _ = sale
    assert [p["price_type"] for p in sales_prices(conn, 100)] == ["Alm", "Tilbud"]
    assert default_cost(cost_prices(conn, 100)) == 80


def test_new_line_is_stored_with_calculated_amounts(sale):
    conn, number = sale
    line_id = save_line(conn, number, line(quantity=3, discount=15, comment=" gift "))
    row = dict(conn.execute("SELECT * FROM invoice_lines WHERE sales_line_id = ?", (line_id,)).fetchone())
    assert (row["amount_incl_vat"], row["amount_ex_vat"], row["amount_cost"]) == (480.0, 384.0, 240.0)
    assert (row["invoice_id"], row["item_id"], row["warehouse_id"], row["quantity"]) == (number, 100, 1, 3)
    assert (row["price_type"], row["comment"], row["is_deleted"]) == ("Alm", "gift", 0)
    assert row["created_at"] and on_hand(conn, 100, 1) == 21


def test_hand_typed_price_has_no_price_type_and_keeps_the_vat_rate(sale):
    conn, number = sale
    line_id = save_line(conn, number, line(sales_price=170, price_type=""))
    assert tuple(conn.execute("SELECT price_type, vat_rate, amount_incl_vat FROM invoice_lines WHERE sales_line_id = ?",
                              (line_id,)).fetchone()) == (None, 0.25, 340.0)


def test_changed_line_recalculates_its_amounts(sale):
    conn, number = sale
    line_id = save_line(conn, number, line())
    save_line(conn, number, line(quantity=-1, vat_rate=0), line_id)
    assert tuple(conn.execute("SELECT quantity, amount_incl_vat, amount_ex_vat FROM invoice_lines WHERE sales_line_id = ?",
                              (line_id,)).fetchone()) == (-1, -165.0, -165.0)
    assert len(lines(conn, number)) == 1


def test_cancelled_line_stays_with_zero_and_flag_and_leaves_stock_and_totals(sale):
    conn, number = sale
    keep = save_line(conn, number, line(quantity=1))
    wrong = save_line(conn, number, line(quantity=6, comment="typo"))
    assert on_hand(conn, 100, 1) == 17 and totals(conn, number)["amount_incl_vat"] == 1155.0
    cancel_line(conn, number, wrong)
    rows = {r["sales_line_id"]: r for r in lines(conn, number)}
    assert rows[wrong]["is_deleted"] == 1 and rows[wrong]["quantity"] == 0 and rows[wrong]["amount_incl_vat"] == 0
    assert rows[wrong]["comment"].startswith("Cancelled ") and "quantity was 6. typo" in rows[wrong]["comment"]
    assert rows[keep]["is_deleted"] == 0
    assert on_hand(conn, 100, 1) == 23 and totals(conn, number) == {"amount_ex_vat": 132.0, "amount_incl_vat": 165.0, "amount_cost": 80.0}
    with pytest.raises(ValidationError, match="cancelled"):
        save_line(conn, number, line(), wrong)
    with pytest.raises(ValidationError, match="cancelled"):
        cancel_line(conn, number, wrong)


def test_line_rules(sale):
    conn, number = sale
    count = conn.execute("SELECT COUNT(*) FROM invoice_lines").fetchone()[0]
    with pytest.raises(ValidationError) as e:
        save_line(conn, number, line(item_id=999, warehouse_id=None, quantity=1.5, sales_price="x", vat_rate=1))
    assert len(e.value.problems) == 5
    with pytest.raises(ValidationError, match="other than 0"):
        save_line(conn, number, line(quantity=0))
    assert conn.execute("SELECT COUNT(*) FROM invoice_lines").fetchone()[0] == count


def test_lines_of_a_closed_invoice_cannot_be_changed(sale):
    conn, number = sale
    line_id = save_line(conn, number, line())
    close(conn, number)
    with pytest.raises(InvoiceClosedError):
        save_line(conn, number, line(quantity=5), line_id)
    with pytest.raises(InvoiceClosedError):
        save_line(conn, number, line())
    with pytest.raises(InvoiceClosedError):
        cancel_line(conn, number, line_id)


def test_a_line_of_another_invoice_is_refused(sale):
    conn, number = sale
    other = create_header(conn, 7, warehouse_id=1)
    line_id = save_line(conn, other, line())
    with pytest.raises(ValidationError, match="not a line of invoice"):
        save_line(conn, number, line(), line_id)
