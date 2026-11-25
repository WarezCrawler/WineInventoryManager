"""Click-through tests of the screens, with NiceGUI's simulated user (no browser). They use a small
hand-made database, so they also run in CI.

The `user` fixture resets NiceGUI before each test, which removes the pages. The `screen` fixture
therefore loads the page modules again after that reset."""
import importlib

import pytest
from nicegui import ui
from nicegui.testing import User

from winedb.db import connect

PAGE_MODULES = ("winedb.ui.menu", "winedb.ui.stock_change", "winedb.ui.stock_mass", "winedb.ui.invoice_header", "winedb.ui.app")


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "wine.db"
    monkeypatch.setenv("WINE_DB_PATH", str(path))
    conn = connect(path)
    conn.executescript("""
        INSERT INTO customers (customer_id, customer_name, address, postal_code, city) VALUES (7, 'Æble Ørsted', 'Vej 1', 8000, 'Århus');
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

TAB, CRLF = chr(9), chr(13) + chr(10)


def excel(*lines) -> str:
    """Text as Excel puts it on the clipboard: tabs between cells, CR LF after each row."""
    return "".join(TAB.join(str(c) for c in line) + CRLF for line in lines)


async def test_menu_mass_registration_button_opens_the_screen(screen: User):
    await screen.open("/")
    screen.find("Mass stock registration").click()
    await screen.should_see("paste from Excel")


def mass_grid(user: User):
    return user.find(ui.aggrid).elements.pop()


def paste(user: User, text: str, row: int = 0, col: str = "warehouse"):
    """What the browser sends when the user pastes cells from Excel into the grid (see stock_mass.PASTE_JS)."""
    user.find(ui.aggrid).trigger("paste", {"text": text, "row": row, "col": col})


def edit(user: User, line: int, field: str, value):
    """What AG Grid sends when the user changes a cell."""
    user.find(ui.aggrid).trigger("cellValueChanged", {"colId": field, "newValue": value, "data": {"line": line}})


async def test_mass_registration_paste_from_excel_check_then_save_all(screen: User, db):
    before = rows(db)
    await screen.open("/stock-mass")
    save = element(screen, ui.button, "Save all")
    assert not save.enabled                                   # nothing checked yet
    paste(screen, excel(("Lager", "Vin", "Antal", "Kommentar"), (1, "RA_10", 6, "Delivery"), (2, 11, -1, "")))
    grid = mass_grid(screen)
    assert [(r["warehouse"], r["wine"], r["quantity"]) for r in grid.options["rowData"][:3]] == [
        ("1", "RA_10", "6"), ("2", "11", "-1"), ("", "", "")]  # heading skipped, filled from the first cell
    screen.find("Check").click()
    await screen.should_see("2 row(s) are correct.")
    data = mass_grid(screen).options["rowData"]
    assert [r["status"] for r in data[:2]] == ["OK", "OK"]
    assert save.enabled
    screen.find("Save all").click()
    await screen.should_see("Saved 2 stock change(s).")
    new = rows(db)[len(before):]
    assert [r[:4] for r in new] == [(10, 1, 6, "Delivery"), (11, 2, -1, None)]
    assert new[0][4] == new[1][4]                             # one date for the whole batch
    assert all(r["wine"] == "" for r in mass_grid(screen).options["rowData"])   # the grid is empty again


async def test_mass_registration_problems_show_in_the_rows_and_nothing_is_saved(screen: User, db):
    before = rows(db)
    await screen.open("/stock-mass")
    paste(screen, excel((1, "RA_10", 6), (9, "NOPE", 0)))
    screen.find("Check").click()
    await screen.should_see("1 row(s) have problems")
    data = mass_grid(screen).options["rowData"]
    assert data[0]["status"] == "OK"
    assert "No warehouse has the id '9'." in data[1]["status"]
    assert "No wine has the id or code 'NOPE'." in data[1]["status"]
    assert not element(screen, ui.button, "Save all").enabled
    assert rows(db) == before


async def test_mass_registration_typing_in_a_cell_and_changes_need_a_new_check(screen: User):
    await screen.open("/stock-mass")
    edit(screen, 1, "warehouse", "1")
    edit(screen, 1, "wine", "RA_10")
    edit(screen, 1, "quantity", 6)
    screen.find("Check").click()
    await screen.should_see("1 row(s) are correct.")
    edit(screen, 1, "quantity", 7)
    await screen.should_see("The rows changed. Check them before you save.")
    assert not element(screen, ui.button, "Save all").enabled
    screen.find("Check").click()                              # the next check uses the changed cell
    await screen.should_see("1 row(s) are correct.")
    assert mass_grid(screen).options["rowData"][0]["quantity"] == "7"


def lines(user: User) -> list[tuple]:
    return [(r["line"], r["wine"]) for r in mass_grid(user).options["rowData"]]


async def test_mass_registration_grid_is_one_new_row_and_grows_by_the_pasted_rows(screen: User):
    await screen.open("/stock-mass")
    assert lines(screen) == [(1, "")]                                   # only the new row, as in Access
    paste(screen, excel((1, "RA_10", 1), (1, "BL_11", 2), (1, "RA_10", 3)))
    assert lines(screen) == [(1, "RA_10"), (2, "BL_11"), (3, "RA_10"), (4, "")]   # 3 pasted + the new row
    paste(screen, excel((2, "BL_11", 5), (2, "BL_11", 6)), row=3)      # paste into the new row
    assert lines(screen) == [(1, "RA_10"), (2, "BL_11"), (3, "RA_10"), (4, "BL_11"), (5, "BL_11"), (6, "")]
    screen.find("Clear").click()
    assert lines(screen) == [(1, "")]


async def test_mass_registration_typing_in_the_new_row_adds_the_next_new_row(screen: User):
    await screen.open("/stock-mass")
    edit(screen, 1, "warehouse", "1")
    assert lines(screen) == [(1, ""), (2, "")]                          # row 1 is in use, row 2 is the new row
    edit(screen, 1, "wine", "RA_10")
    assert len(lines(screen)) == 2                                      # still one new row only
    edit(screen, 2, "wine", "BL_11")
    assert len(lines(screen)) == 3


def test_the_browser_paste_handler_sends_excel_text_with_its_cell():
    from winedb.ui.stock_mass import PASTE_JS
    assert "[" + chr(92) + "t" + chr(92) + "n]" in PASTE_JS    # the regular expression for tab or line break
    assert "row-index" in PASTE_JS and "col-id" in PASTE_JS and "preventDefault" in PASTE_JS


async def test_mass_registration_warehouse_and_wine_cells_have_lists_and_show_names(screen: User):
    await screen.open("/stock-mass")
    columns = {c["field"]: c for c in mass_grid(screen).options["columnDefs"]}
    assert columns["warehouse"]["refData"] == {"1": "1 – Main", "2": "2 – Fridge"}
    wine_names = columns["wine"]["refData"]
    assert wine_names["RA_10"] == "RA_10 – Rosso 2010"             # a code shows its wine
    assert wine_names["10"] == "10 = RA_10 – Rosso 2010"           # an id too
    assert "OLD_EMPTY" not in wine_names                           # same wines as the stock change picker
    # Warehouse: double-click, Enter or F2 open the list; typing opens the text editor.
    selector = columns["warehouse"][":cellEditorSelector"]
    assert "agSelectCellEditor" in selector and "agTextCellEditor" in selector and '"1", "2"' in selector
    # Wine: a text box with suggestions (a datalist) that the browser filters on code and name.
    editor = columns["wine"][":cellEditor"]
    assert editor.startswith("class {") and "datalist" in editor and "getValue()" in editor
    assert '["21_fejl", "21_fejl' in editor and "Gone with stock 2002" in editor and '"OLD_EMPTY"' not in editor
    assert "warehouse_name" not in columns and "wine_name" not in columns


# --- Invoice header screen (step 7) ---

def header_row(db, invoice_id):
    conn = connect(db)
    try:
        row = conn.execute("SELECT * FROM invoice_header WHERE invoice_id = ?", (invoice_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


async def test_menu_invoice_details_without_selection_opens_a_new_invoice(screen: User):
    await screen.open("/")
    screen.find("Invoice details").click()
    await screen.should_see("New invoice")


async def test_new_invoice_is_created_with_a_customer_and_stored_as_access_would(screen: User, db):
    await screen.open("/invoice/new")
    assert not element(screen, ui.button, "Close invoice").enabled          # nothing to close yet
    screen.find("Save").click()
    await screen.should_see("Choose a customer.")                         # a new invoice needs a customer
    element(screen, ui.select, "Customer").value = 7
    await screen.should_see("Vej 1")                                      # the customer's address, read-only
    element(screen, ui.select, "Default warehouse").value = 2
    element(screen, ui.input, "Invoice date").value = "2026-11-21"
    element(screen, ui.textarea, "Comment").value = "Tasting"
    screen.find("Save").click()
    await screen.should_see("Invoice 5")                                  # the next number; the page shows it
    assert header_row(db, 5) == {"invoice_id": 5, "customer_id": 7, "is_closed": 0, "comment": "Tasting",
                                 "warehouse_id": 2, "invoice_date": "2026-11-21 00:00:00",
                                 "hide_subtotals": 0, "is_deleted": 0}


async def test_open_invoice_is_edited_and_only_changes_are_saved(screen: User, db):
    await screen.open("/invoice/1")
    await screen.should_see("Invoice 1")
    assert element(screen, ui.select, "Customer").value == 7
    element(screen, ui.checkbox, "Hide subtotals").value = True
    screen.find("Save").click()
    await screen.should_see("Invoice 1 is saved.")
    assert header_row(db, 1)["hide_subtotals"] == 1 and header_row(db, 1)["customer_id"] == 7


async def test_old_draft_without_customer_can_get_a_comment(screen: User, db):
    await screen.open("/invoice/3")
    await screen.should_see("(no customer)")
    element(screen, ui.textarea, "Comment").value = "Still a draft"
    screen.find("Save").click()
    await screen.should_see("Invoice 3 is saved.")
    assert header_row(db, 3)["comment"] == "Still a draft" and header_row(db, 3)["customer_id"] == 0


async def test_delete_flag_shows_the_access_warning_and_is_saved(screen: User, db):
    await screen.open("/invoice/1")
    element(screen, ui.checkbox, "Delete").value = True
    await screen.should_see("Be aware that this invoice will be suppressed")
    screen.find("Save").click()
    await screen.should_see("Invoice 1 is saved.")
    assert header_row(db, 1)["is_deleted"] == 1


async def test_close_asks_first_then_the_invoice_is_closed_and_read_only(screen: User, db):
    await screen.open("/invoice/1")
    screen.find("Close invoice").click()
    await screen.should_see("Close invoice 1? A closed invoice cannot be changed.")
    screen.find(marker="cancel-close").click()
    assert header_row(db, 1)["is_closed"] == 0
    screen.find("Close invoice").click()
    await screen.should_see("Close invoice 1?")
    screen.find(marker="confirm-close").click()
    await screen.should_see("This invoice is closed. It cannot be changed.")
    assert header_row(db, 1)["is_closed"] == 1


async def test_closed_invoice_is_read_only(screen: User):
    await screen.open("/invoice/2")
    await screen.should_see("This invoice is closed. It cannot be changed.")
    assert not element(screen, ui.button, "Save").enabled
    assert not element(screen, ui.select, "Customer").enabled


async def test_unknown_invoice(screen: User):
    await screen.open("/invoice/999")
    await screen.should_see("Invoice 999 does not exist.")
