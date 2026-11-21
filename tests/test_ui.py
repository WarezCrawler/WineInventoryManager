"""Click-through tests of the screens, with NiceGUI's simulated user (no browser). They use a small
hand-made database, so they also run in CI.

The `user` fixture resets NiceGUI before each test, which removes the pages. The `screen` fixture
therefore loads the page modules again after that reset."""
import importlib

import pytest
from nicegui import ui
from nicegui.testing import User

from winedb.db import connect

PAGE_MODULES = ("winedb.ui.menu", "winedb.ui.stock_change", "winedb.ui.stock_mass", "winedb.ui.app")


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "wine.db"
    monkeypatch.setenv("WINE_DB_PATH", str(path))
    conn = connect(path)
    conn.executescript("""
        INSERT INTO customers (customer_id, customer_name) VALUES (7, 'Æble Ørsted');
        INSERT INTO invoice_header (invoice_id, customer_id, is_closed, is_deleted) VALUES
            (1, 7, 0, 0), (2, 7, 1, 0), (3, 0, 0, 0), (4, 7, 0, 1);
        INSERT INTO items (item_id, item_code, name, vintage, item_type, bottle_size, country)
            VALUES (10, 'RA_10', 'Rosso', 2010, 'Rød', 'Alm', 'Italien'), (11, 'BL_11', 'Blanc', 2011, 'Hvid', 'Halv', 'Frankrig');
        INSERT INTO items (item_id, item_code, name, vintage, is_discontinued)
            VALUES (20, 'OLD_EMPTY', 'Gone', 2001, 1), (21, '21_fejl', 'Gone with stock', 2002, 1);
        INSERT INTO stock_transactions (item_id, warehouse_id, quantity) VALUES (21, 2, 30);
        INSERT INTO warehouses (warehouse_id, warehouse_name) VALUES (1, 'Main'), (2, 'Fridge');
        INSERT INTO stock_transactions (item_id, warehouse_id, quantity, comment, created_at)
            VALUES (10, 1, 12, 'Opening', '2013-06-21 00:00:05');
        INSERT INTO invoice_lines (item_id, warehouse_id, invoice_id, quantity) VALUES (10, 1, 1, 2);
    """)
    conn.close()
    return path


@pytest.fixture
def screen(user: User, db) -> User:
    for name in PAGE_MODULES:
        importlib.reload(importlib.import_module(name))
    return user


def element(user: User, kind, text: str):
    """The one element of `kind` whose label or text contains `text`."""
    found = user.find(kind=kind, content=text).elements
    assert len(found) == 1, f"{len(found)} {kind.__name__} elements with {text!r}"
    return found.pop()


def rows(db) -> list[tuple]:
    conn = connect(db)
    try:
        return [tuple(r) for r in conn.execute(
            "SELECT item_id, warehouse_id, quantity, comment, created_at FROM stock_transactions ORDER BY stock_line_id")]
    finally:
        conn.close()


# --- Main menu (step 5) ---

async def test_menu_lists_open_invoices_in_english(screen: User):
    await screen.open("/")
    await screen.should_see("Wine Inventory Manager")
    table = screen.find(ui.table).elements.pop()   # table cells are rows, not text that should_see finds
    assert [(r["invoice_id"], r["customer_name"], r["is_deleted"]) for r in table.rows] == [
        (4, "Æble Ørsted", "Yes"),      # newest first; data stays as it is
        (3, "(no customer)", ""),       # customer 0
        (1, "Æble Ørsted", ""),         # closed invoice 2 is left out
    ]


async def test_menu_open_invoice_needs_a_selection_and_later_buttons_are_disabled(screen: User):
    await screen.open("/")
    assert not element(screen, ui.button, "Open invoice").enabled
    assert element(screen, ui.button, "Wine list").props.get("disable") is True


async def test_menu_stock_change_button_opens_the_screen(screen: User):
    await screen.open("/")
    screen.find("Stock change").click()
    await screen.should_see("Latest 20 movements")


# --- Stock change screen (step 6) ---

async def test_stock_change_shows_stock_and_saves(screen: User, db):
    await screen.open("/stock-change")
    element(screen, ui.select, "Wine").value = 10
    element(screen, ui.select, "Warehouse").value = 1
    await screen.should_see("On-hand stock: 10")           # 12 in, 2 sold
    await screen.should_see("Country: Italien")            # wine details, data as it is
    history = screen.find(ui.table).elements.pop()
    assert [(r["quantity"], r["comment"]) for r in history.rows] == [(12, "Opening")]   # latest movements
    element(screen, ui.number, "Quantity").value = -3
    await screen.should_see("after this change: 7")
    element(screen, ui.input, "Comment").value = "Tasting"
    element(screen, ui.input, "Date").value = "2026-11-21 10:00:00"
    screen.find("Save").click()
    await screen.should_see("The stock change is saved.")
    await screen.should_see("On-hand stock: 7")
    assert [r["quantity"] for r in history.rows] == [-3, 12]                          # the new movement is first
    assert rows(db)[-1] == (10, 1, -3, "Tasting", "2026-11-21 10:00:00")
    assert element(screen, ui.number, "Quantity").value is None   # ready for the next change


async def test_stock_change_reports_problems_and_writes_nothing(screen: User, db):
    before = rows(db)
    await screen.open("/stock-change")
    element(screen, ui.number, "Quantity").value = 0
    element(screen, ui.input, "Date").value = "21-11-2026"
    screen.find("Save").click()
    await screen.should_see("Choose a wine.")
    await screen.should_see("Choose a warehouse.")
    await screen.should_see("Enter a whole number other than 0")
    await screen.should_see("Enter the date in the form YYYY-MM-DD HH:MM:SS.")
    assert rows(db) == before


async def test_stock_change_cancel_returns_to_the_menu(screen: User):
    await screen.open("/stock-change")
    screen.find("Cancel").click()
    await screen.should_see("Open invoices")


async def test_stock_change_picker_shows_the_code_and_hides_discontinued_wines_without_stock(screen: User):
    await screen.open("/stock-change")
    options = element(screen, ui.select, "Wine").options
    assert options[10].startswith("Code RA_10 – Rosso 2010")
    assert 20 not in options                                          # discontinued, stock 0
    assert options[21] == "Code 21_fejl – Gone with stock 2002 (discontinued)"
    assert list(options)[-1] == 21                                    # discontinued wines come last


# --- Mass stock registration (step 6, Access "Import vinlager tilgange/afgange") ---

async def test_menu_mass_registration_button_opens_the_screen(screen: User):
    await screen.open("/")
    screen.find("Mass stock registration").click()
    await screen.should_see("Paste rows from Excel")


async def test_mass_registration_check_then_save_all(screen: User, db):
    before = rows(db)
    await screen.open("/stock-mass")
    save = element(screen, ui.button, "Save all")
    assert not save.enabled                                   # nothing checked yet
    element(screen, ui.textarea, "Rows").value = "Lager\tVin\tAntal\tKommentar\n1\tRA_10\t6\tDelivery\n2\t11\t-1\t"
    screen.find("Check").click()
    await screen.should_see("2 row(s) are correct.")
    preview = screen.find(ui.table).elements.pop()
    assert [(r["warehouse"], r["wine"], r["quantity"], r["status"]) for r in preview.rows] == [
        ("Main", "RA_10 – Rosso 2010", 6, "OK"), ("Fridge", "BL_11 – Blanc 2011", -1, "OK")]
    assert save.enabled
    screen.find("Save all").click()
    await screen.should_see("Saved 2 stock change(s).")
    new = rows(db)[len(before):]
    assert [r[:4] for r in new] == [(10, 1, 6, "Delivery"), (11, 2, -1, None)]
    assert new[0][4] == new[1][4]                             # one date for the whole batch


async def test_mass_registration_with_a_bad_row_saves_nothing(screen: User, db):
    before = rows(db)
    await screen.open("/stock-mass")
    element(screen, ui.textarea, "Rows").value = "1\tRA_10\t6\n9\tNOPE\t0"
    screen.find("Check").click()
    await screen.should_see("Line 2: no warehouse has the id '9'.")
    await screen.should_see("Line 2: no wine has the id or code 'NOPE'.")
    assert not element(screen, ui.button, "Save all").enabled
    assert rows(db) == before


async def test_mass_registration_changed_text_must_be_checked_again(screen: User):
    await screen.open("/stock-mass")
    area = element(screen, ui.textarea, "Rows")
    area.value = "1\tRA_10\t6"
    screen.find("Check").click()
    await screen.should_see("1 row(s) are correct.")
    area.value = "1\tRA_10\t7"
    await screen.should_see("The rows changed. Check them again.")
    assert not element(screen, ui.button, "Save all").enabled
