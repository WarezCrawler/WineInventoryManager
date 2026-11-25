"""Maintenance of master data and reopening an invoice (step 10) on a small hand-made database."""
import pytest

from winedb.db import connect
from winedb.invoices import close, closed_invoices, cost_prices, create_header, get_header, reopen, sales_prices
from winedb.logic import default_cost
from winedb.masterdata import (delete_cost_price, delete_sales_price, get_customer_record, get_wine, list_customer_records,
                               list_customers, list_warehouse_records, list_wines, save_cost_price, save_customer,
                               save_sales_price, save_warehouse, save_wine, set_customer_hidden, set_wine_discontinued,
                               suggestions)
from winedb.stock import wines_for_stock_change
from winedb.validation import ValidationError


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    c.executescript("""
        INSERT INTO items (item_id, item_code, name, vintage, producer, item_type, bottle_size) VALUES
            (1, 'A1', 'Malvasia', 2012, 'Abel Mendoza', 'Hvid', 'Alm'),
            (2, 'B2', 'Rosenberg', 2009, 'Becker', 'Rød', 'MGM');
        INSERT INTO items (item_id, item_code, name, vintage, is_discontinued) VALUES (3, 'OLD', 'Gone', 0, 1);
        INSERT INTO customers (customer_id, customer_name, postal_code, city, is_hidden) VALUES
            (7, 'Æble Ørsted', 2700, 'Brønshøj', 0), (8, 'Hidden Ltd', NULL, NULL, 1);
        INSERT INTO warehouses (warehouse_id, warehouse_name) VALUES (1, 'Main');
    """)
    yield c
    c.close()


WINE = {"item_code": "NEW1", "name": "Ancely", "vintage": 2007, "producer": "Negly", "country": "Frankrig",
        "region": "", "item_type": "Rød", "bottle_size": "Alm", "drink_by_year": None, "mature_year": 2012,
        "is_discontinued": False, "is_private": False, "comment": " good "}


# Wines

def test_add_a_wine_with_all_fields(conn):
    item_id = save_wine(conn, WINE)
    wine = get_wine(conn, item_id)
    assert (wine["item_code"], wine["name"], wine["vintage"], wine["mature_year"], wine["comment"]) == ("NEW1", "Ancely", 2007, 2012, "good")
    assert (wine["region"], wine["drink_by_year"], wine["is_discontinued"]) == (None, None, 0)


def test_a_new_wine_needs_code_name_and_vintage_and_a_unique_code(conn):
    with pytest.raises(ValidationError) as e:
        save_wine(conn, {**WINE, "item_code": " ", "name": "", "vintage": "x", "mature_year": 2012.5})
    assert e.value.fields == {"item_code": "Enter the wine code.", "name": "Enter the name.",
                              "vintage": "Enter the vintage as a number.", "mature_year": "Enter the mature year as a whole number."}
    with pytest.raises(ValidationError, match="Another wine .id 1. has the code a1"):
        save_wine(conn, {**WINE, "item_code": "a1"})                 # upper and lower case are the same
    with pytest.raises(ValidationError, match="Enter the vintage"):
        save_wine(conn, {"item_code": "X", "name": "Y"})             # a missing field counts as empty


def test_edit_checks_only_changed_fields(conn):
    conn.execute("UPDATE items SET mature_year = 'soon' WHERE item_id = 2")   # an old row that breaks a rule
    save_wine(conn, {**get_wine(conn, 2), "comment": "edited"}, 2)   # the year is not changed: no check
    assert (get_wine(conn, 2)["comment"], get_wine(conn, 2)["mature_year"]) == ("edited", "soon")
    with pytest.raises(ValidationError, match="mature year as a number"):
        save_wine(conn, {**get_wine(conn, 2), "mature_year": "later"}, 2)       # a changed field is checked
    save_wine(conn, {**get_wine(conn, 1), "item_code": "A1"}, 1)     # its own code is not a duplicate
    with pytest.raises(ValidationError, match="has the code B2"):
        save_wine(conn, {**get_wine(conn, 1), "item_code": "B2"}, 1)
    with pytest.raises(ValidationError, match="does not exist"):
        save_wine(conn, WINE, 99)


def test_delete_a_wine_marks_it_discontinued_and_can_be_undone(conn):
    set_wine_discontinued(conn, 1, True)
    assert get_wine(conn, 1)["is_discontinued"] == 1
    assert [w["item_id"] for w in list_wines(conn)] == [2]                       # hidden from the list
    assert [w["item_id"] for w in list_wines(conn, include_discontinued=True)] == [3, 1, 2]
    assert 1 not in {w["item_id"] for w in wines_for_stock_change(conn)}       # and from the pickers (no stock)
    set_wine_discontinued(conn, 1, False)
    assert get_wine(conn, 1)["is_discontinued"] == 0


def test_suggestions_are_the_values_in_the_data(conn):
    assert suggestions(conn, "items", "item_type") == ["Hvid", "Rød"]
    assert suggestions(conn, "items", "bottle_size") == ["Alm", "MGM"]           # variants stay as they are
    with pytest.raises(ValueError):
        suggestions(conn, "customers", "customer_name")


# Prices

def test_add_edit_and_delete_sales_prices(conn):
    first = save_sales_price(conn, 1, {"price_type": "Alm", "sales_price": 125, "vat_rate": 0.25})
    second = save_sales_price(conn, 1, {"price_type": "Tilbud", "sales_price": 99.5, "vat_rate": 0})
    save_sales_price(conn, 1, {"price_type": "Alm", "sales_price": 130, "vat_rate": 0.25}, first)
    assert [(p["price_type"], p["sales_price"], p["vat_rate"]) for p in sales_prices(conn, 1)] == [("Alm", 130, 0.25), ("Tilbud", 99.5, 0)]
    delete_sales_price(conn, 1, second)                                          # really deleted (decision 19)
    assert conn.execute("SELECT COUNT(*) FROM prices_sales WHERE sales_price_id = ?", (second,)).fetchone()[0] == 0


def test_price_rules(conn):
    with pytest.raises(ValidationError) as e:
        save_sales_price(conn, 1, {"price_type": "", "sales_price": "", "vat_rate": 1})
    assert e.value.fields == {"sales_price": "Enter the sales price.", "vat_rate": "Enter the VAT rate from 0 % to under 100 %."}
    with pytest.raises(ValidationError, match="Choose a wine first"):
        save_cost_price(conn, 99, {"cost_price": 10})
    other = save_sales_price(conn, 2, {"sales_price": 10, "vat_rate": 0.25})
    with pytest.raises(ValidationError, match="not a price of wine 1"):
        delete_sales_price(conn, 1, other)                                       # a price of another wine


def test_cost_prices_feed_the_default_cost(conn):
    raw = save_cost_price(conn, 1, {"price_type": "rå", "cost_price": 70})
    standard = save_cost_price(conn, 1, {"price_type": "Standard", "cost_price": 80})
    assert default_cost(cost_prices(conn, 1)) == 80
    delete_cost_price(conn, 1, standard)
    assert default_cost(cost_prices(conn, 1)) == 0 and [c["cost_price_id"] for c in cost_prices(conn, 1)] == [raw]


# Customers and warehouses

def test_add_edit_and_hide_a_customer(conn):
    number = save_customer(conn, {"customer_name": " New Shop ", "postal_code": "8000", "city": "Århus", "email": "a@b.dk",
                                  "on_mailing_list": True})
    c = get_customer_record(conn, number)
    assert (c["customer_name"], c["postal_code"], c["city"], c["on_mailing_list"], c["is_hidden"]) == ("New Shop", 8000, "Århus", 1, 0)
    with pytest.raises(ValidationError) as e:
        save_customer(conn, {"customer_name": "", "postal_code": "27OO"}, number)
    assert set(e.value.fields) == {"customer_name", "postal_code"}
    set_customer_hidden(conn, number, True)                                      # "Delete" = hide, as Access
    assert number not in {r["customer_id"] for r in list_customer_records(conn)}
    assert number not in {r["customer_id"] for r in list_customers(conn)}        # nor in the invoice picker
    assert {r["customer_id"] for r in list_customer_records(conn, include_hidden=True)} >= {number, 8}
    set_customer_hidden(conn, number, False)
    assert get_customer_record(conn, number)["is_hidden"] == 0


def test_a_new_row_gets_the_access_defaults_for_empty_fields(conn):
    number = save_customer(conn, {"customer_name": "No address", "postal_code": None, "city": ""})
    c = get_customer_record(conn, number)
    assert (c["postal_code"], c["city"], c["is_hidden"], c["on_mailing_list"]) == (0, None, 0, 0)   # Access: Post_nr 0
    save_customer(conn, {**c, "postal_code": ""}, number)              # an edit that empties it stores NULL
    assert get_customer_record(conn, number)["postal_code"] is None


def test_add_and_edit_a_warehouse(conn):
    new = save_warehouse(conn, {"warehouse_name": "Cellar", "comment": ""})
    save_warehouse(conn, {"warehouse_name": "Cellar 2", "comment": "Under the house"}, new)
    assert list_warehouse_records(conn)[-1] == {"warehouse_id": new, "warehouse_name": "Cellar 2", "comment": "Under the house"}
    with pytest.raises(ValidationError, match="Enter the warehouse name"):
        save_warehouse(conn, {"warehouse_name": " "})


# Reopen an invoice

def test_reopen_is_the_reverse_of_close(conn):
    number = create_header(conn, 7, warehouse_id=1, comment="x")
    before = get_header(conn, number)
    close(conn, number)
    assert [i["invoice_id"] for i in closed_invoices(conn)] == [number]
    reopen(conn, number)
    assert get_header(conn, number) == before                                    # nothing else changed
    assert closed_invoices(conn) == []
    with pytest.raises(ValidationError, match="is not closed"):
        reopen(conn, number)
    with pytest.raises(ValidationError, match="does not exist"):
        reopen(conn, 999)
