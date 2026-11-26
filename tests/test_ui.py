"""Click-through tests of the screens, with NiceGUI's simulated user (no browser). They use a small
hand-made database, so they also run in CI.

The `user` fixture resets NiceGUI before each test, which removes the pages. The `screen` fixture
therefore loads the page modules again after that reset."""
import importlib

import pytest
from nicegui import ui
from nicegui.testing import User

from winedb.db import connect

PAGE_MODULES = ("winedb.ui.menu", "winedb.ui.stock_change", "winedb.ui.stock_mass", "winedb.ui.invoice_header", "winedb.ui.invoice_lines", "winedb.ui.invoice_preview", "winedb.ui.master_screens", "winedb.ui.closed_invoices", "winedb.ui.app")


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
        INSERT INTO invoice_lines (item_id, warehouse_id, invoice_id, quantity, sales_price, vat_rate, amount_incl_vat, amount_ex_vat)
            VALUES (10, 1, 1, 2, 100, 0.25, 200, 160);
        INSERT INTO prices_sales (sales_price_id, item_id, price_type, sales_price, vat_rate) VALUES (1, 10, 'Alm', 165, 0.25), (2, 10, '0P', 120, 0);
        INSERT INTO prices_cost (cost_price_id, item_id, price_type, cost_price) VALUES (1, 10, 'Standard', 80);
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
    assert [c["label"] for c in table.columns] == ["Invoice no.", "Customer no.", "Customer name", "Bottles", "Wines",
                                                   "Total excl. VAT", "Deleted"]
    assert [(r["total_quantity"], r["wine_count"], r["amount_ex_vat"]) for r in table.rows if r["invoice_id"] == 1] == [(2, 1, 160)]
    assert [(r["invoice_id"], r["customer_name"], r["is_deleted"]) for r in table.rows] == [
        (4, "Æble Ørsted", "Yes"),      # newest first; data stays as it is
        (3, "(no customer)", ""),       # customer 0
        (1, "Æble Ørsted", ""),         # closed invoice 2 is left out
    ]


async def test_menu_open_invoice_needs_a_selection_and_later_buttons_are_disabled(screen: User):
    await screen.open("/")
    assert not element(screen, ui.button, "Open invoice lines").enabled
    assert element(screen, ui.button, "Stock report").props.get("disable") is True


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
    screen.find(marker="invoice").click()                  # the button "Invoice"
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


# --- Invoice lines screen (step 8) ---

def line_rows(db, invoice_id):
    conn = connect(db)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY sales_line_id", (invoice_id,))]
    finally:
        conn.close()


def select_line(user: User, line_id: int):
    """What the browser sends when the user clicks a row of the lines grid."""
    grid = user.find(ui.table).elements.pop()
    row = next(r for r in grid.rows if r["sales_line_id"] == line_id)
    user.find(ui.table).trigger("selection", {"rows": [row], "keys": [line_id], "added": True})


async def test_menu_open_invoice_opens_the_lines_of_the_selected_invoice(screen: User):
    await screen.open("/")
    table = screen.find(ui.table).elements.pop()
    row = next(r for r in table.rows if r["invoice_id"] == 1)
    screen.find(ui.table).trigger("selection", {"rows": [row], "keys": [1], "added": True})   # the user clicks the row
    assert element(screen, ui.button, "Open invoice lines").enabled            # enabled by the selection
    screen.find(kind=ui.button, content="Open invoice lines").click()
    await screen.should_see("Invoice 1 – lines")


async def test_new_line_with_picked_price_and_default_cost_is_saved(screen: User, db):
    await screen.open("/invoice/1/lines")
    await screen.should_see("Invoice total excl. VAT: 160.00")
    element(screen, ui.select, "Wine").value = 10
    assert element(screen, ui.number, "Unit cost price").value == 80          # Access: the Standard cost
    element(screen, ui.select, "Pick a sales price").value = 1                # Alm 165, 25 % VAT
    assert element(screen, ui.number, "Unit price").value == 165 and element(screen, ui.number, "VAT %").value == 25
    element(screen, ui.select, "Warehouse").value = 1                         # the invoice has no warehouse
    await screen.should_see("On-hand stock in this warehouse: 10")
    element(screen, ui.number, "Quantity").value = 3
    element(screen, ui.number, "Discount").value = 15
    await screen.should_see("Line total incl. VAT: 480.00 · excl. VAT: 384.00 · cost: 240.00")
    screen.find("Save line").click()
    await screen.should_see("is saved.")
    new = line_rows(db, 1)[-1]
    assert (new["item_id"], new["warehouse_id"], new["quantity"], new["sales_price"], new["price_type"], new["vat_rate"],
            new["discount"], new["cost_price"]) == (10, 1, 3, 165, "Alm", 0.25, 15, 80)
    assert (new["amount_incl_vat"], new["amount_ex_vat"], new["amount_cost"], new["is_deleted"]) == (480, 384, 240, 0)
    await screen.should_see("Invoice total excl. VAT: 544.00")


async def test_typed_price_clears_the_price_type(screen: User, db):
    await screen.open("/invoice/1/lines")
    element(screen, ui.select, "Wine").value = 10
    element(screen, ui.select, "Pick a sales price").value = 1
    element(screen, ui.number, "Unit price").value = 170                      # typed by hand
    await screen.should_see("Price typed by hand")
    element(screen, ui.select, "Warehouse").value = 1
    element(screen, ui.number, "Quantity").value = 1
    screen.find("Save line").click()
    await screen.should_see("is saved.")
    assert (line_rows(db, 1)[-1]["price_type"], line_rows(db, 1)[-1]["vat_rate"]) == (None, 0.25)


async def test_line_problems_are_shown_at_the_fields_and_nothing_is_saved(screen: User, db):
    before = line_rows(db, 1)
    await screen.open("/invoice/1/lines")
    element(screen, ui.select, "Wine").value = 10
    element(screen, ui.number, "Quantity").value = 2
    screen.find("Save line").click()
    await screen.should_see("Choose a warehouse. Enter the sales price. Enter the VAT rate.")   # the invoice has no warehouse
    marked = {name: element(screen, kind, name).props.get("error-message")
              for kind, name in ((ui.select, "Wine"), (ui.select, "Warehouse"), (ui.number, "Quantity"),
                                 (ui.number, "Unit price"), (ui.number, "VAT %"))}
    assert marked == {"Wine": None, "Warehouse": "Choose a warehouse.", "Quantity": None,
                      "Unit price": "Enter the sales price.", "VAT %": "Enter the VAT rate."}
    element(screen, ui.select, "Warehouse").value = 1                        # a changed field loses its mark
    assert element(screen, ui.select, "Warehouse").props.get("error") is None
    assert line_rows(db, 1) == before


async def test_an_unexpected_error_on_save_is_shown(screen: User, db, monkeypatch, caplog):
    import sys

    def broken(*args, **kwargs):
        raise RuntimeError("disk full")
    monkeypatch.setattr(sys.modules["winedb.ui.invoice_lines"], "save_line", broken)
    await screen.open("/invoice/1/lines")
    screen.find("Save line").click()
    await screen.should_see("Unexpected error: disk full")
    assert "Saving a line of invoice 1 failed" in caplog.text     # also in the log, with the traceback
    caplog.clear()                                                # expected: do not fail the test on it


async def test_cancel_line_asks_first_then_zero_and_flag(screen: User, db):
    await screen.open("/invoice/1/lines")
    line_id = line_rows(db, 1)[0]["sales_line_id"]
    select_line(screen, line_id)
    await screen.should_see(f"Line {line_id}")
    screen.find("Cancel line").click()
    await screen.should_see("Its quantity and amounts become 0")
    screen.find(marker="keep-line").click()
    assert line_rows(db, 1)[0]["is_deleted"] == 0
    screen.find("Cancel line").click()
    await screen.should_see("Its quantity and amounts become 0")
    screen.find(marker="confirm-cancel").click()
    await screen.should_see(f"Line {line_id} is cancelled.")
    row = line_rows(db, 1)[0]
    assert (row["is_deleted"], row["quantity"], row["amount_incl_vat"]) == (1, 0, 0)
    grid = screen.find(ui.table).elements.pop()
    assert grid.rows[0]["line_status"] == "Cancelled"
    await screen.should_see("Invoice total excl. VAT: 0.00")


async def test_closed_invoice_lines_are_read_only(screen: User):
    await screen.open("/invoice/2/lines")
    await screen.should_see("This invoice is closed. Its lines are read-only.")
    assert not element(screen, ui.button, "Save line").enabled
    assert not element(screen, ui.select, "Wine").enabled


async def test_close_invoice_from_the_lines_screen(screen: User, db):
    await screen.open("/invoice/1/lines")
    screen.find("Close invoice").click()
    await screen.should_see("Close invoice 1?")
    screen.find(marker="confirm-close").click()
    await screen.should_see("This invoice is closed. Its lines are read-only.")
    assert header_row(db, 1)["is_closed"] == 1


# --- Invoice preview and PDF (step 9) ---

import json  # noqa: E402
import sys  # noqa: E402
from datetime import date  # noqa: E402

from winedb.invoices import cancel_line, save_line  # noqa: E402


@pytest.fixture
def pdf_folder(tmp_path, monkeypatch):
    folder = tmp_path / "pdf"
    folder.mkdir()
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"invoice_address": "Firm address", "invoice_bank_details": "Bank details",
                                    "invoice_payment_terms": "8 days", "invoice_pdf_folder": str(folder)}), encoding="utf-8")
    monkeypatch.setenv("WINE_SETTINGS_PATH", str(settings))
    return folder


@pytest.fixture
def opened(screen: User, monkeypatch) -> list:
    """The PDFs the screen opens in the viewer (not opened for real in a test)."""
    files = []
    monkeypatch.setattr(sys.modules["winedb.ui.invoice_preview"], "open_file", files.append)
    return files


async def test_menu_generate_invoice_opens_the_preview_of_the_selected_invoice(screen: User):
    await screen.open("/")
    assert not element(screen, ui.button, "Generate invoice").enabled
    table = screen.find(ui.table).elements.pop()
    row = next(r for r in table.rows if r["invoice_id"] == 1)
    screen.find(ui.table).trigger("selection", {"rows": [row], "keys": [1], "added": True})
    screen.find(kind=ui.button, content="Generate invoice").click()
    await screen.should_see("Invoice 1 – preview")


async def test_preview_shows_the_lines_totals_and_texts(screen: User, pdf_folder):
    await screen.open("/invoice/1/preview")
    await screen.should_see("Invoice no. 00001")
    await screen.should_see("Æble Ørsted")                       # data as it is
    await screen.should_see("Århus 8000")
    grid = screen.find(ui.table).elements.pop()
    assert [(r["quantity"], r["wine"], r["vintage"], r["sales_price"], r["line_total"]) for r in grid.rows] == [
        ("2", "Rosso - Rød", "2010", "100.00", "200.00")]
    for text in ("Total quantity: 2", "Total incl. VAT", "200.00", "Of which VAT", "40.00", "160.00", "Firm address", "8 days"):
        await screen.should_see(text)


async def test_preview_with_hide_subtotals_leaves_out_prices_and_cancelled_lines(screen: User, db, pdf_folder):
    conn = connect(db)
    try:
        new = save_line(conn, 1, {"item_id": 11, "warehouse_id": 1, "quantity": 1, "sales_price": 50, "vat_rate": 0.25})
        old = conn.execute("SELECT MIN(sales_line_id) FROM invoice_lines WHERE invoice_id = 1").fetchone()[0]
        cancel_line(conn, 1, old)
        conn.execute("UPDATE invoice_header SET hide_subtotals = 1 WHERE invoice_id = 1")
        conn.commit()
    finally:
        conn.close()
    await screen.open("/invoice/1/preview")
    await screen.should_see("Hide subtotals is on")
    grid = screen.find(ui.table).elements.pop()
    assert [c["name"] for c in grid.columns] == ["producer", "quantity", "wine", "vintage"]
    assert [r["key"] for r in grid.rows] == [new]                 # the cancelled line is not shown
    await screen.should_see("Total quantity: 1")


async def test_create_pdf_saves_and_opens_it_and_asks_before_replacing(screen: User, pdf_folder, opened):
    await screen.open("/invoice/1/preview")
    screen.find("Create PDF").click()
    await screen.should_see("The PDF is saved")
    pdf = pdf_folder / f"F1_ÆØ7_{date.today():%d-%m-%Y}.pdf"        # Access name; no invoice date, so today
    assert pdf.read_bytes().startswith(b"%PDF") and opened == [pdf]

    pdf.write_bytes(b"old")
    screen.find("Create PDF").click()
    await screen.should_see("already exists")
    screen.find(marker="keep-pdf").click()
    await screen.should_see("The PDF is not replaced.")
    assert pdf.read_bytes() == b"old" and len(opened) == 1

    screen.find("Create PDF").click()
    await screen.should_see("already exists")
    screen.find(marker="confirm-replace").click()
    await screen.should_see("The PDF is saved")
    assert pdf.read_bytes().startswith(b"%PDF") and len(opened) == 2


async def test_create_pdf_without_a_pdf_folder_uses_the_data_folder(screen: User, db, tmp_path, monkeypatch, opened):
    monkeypatch.setenv("WINE_SETTINGS_PATH", str(tmp_path / "missing.json"))
    await screen.open("/invoice/1/preview")
    screen.find("Create PDF").click()
    await screen.should_see("The PDF is saved")
    [pdf] = opened
    assert pdf.parent == db.parent / "invoices"                                # all user data in the data folder


async def test_preview_of_an_unknown_invoice(screen: User, pdf_folder):
    await screen.open("/invoice/99/preview")
    await screen.should_see("Invoice 99 does not exist.")


# --- Master data and reopening an invoice (step 10) ---

def query(db, sql, *args):
    conn = connect(db)
    try:
        return [tuple(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def pick_row(user: User, marker: str, key: str, value):
    """What the browser sends when the user clicks a row of the list with this marker."""
    grid = user.find(marker=marker).elements.pop()
    row = next(r for r in grid.rows if r[key] == value)
    user.find(marker=marker).trigger("selection", {"rows": [row], "keys": [value], "added": True})


def main_list(user: User):
    return user.find(marker="list").elements.pop()


async def test_menu_master_data_buttons_open_the_screens(screen: User):
    for caption, title in (("Wine list", "Wines"), ("Maintain customers", "Customers"), ("Warehouses", "Warehouses"),
                           ("Reopen closed invoice", "Closed invoices"), ("Sales price list", "Sales prices")):
        await screen.open("/")
        assert element(screen, ui.button, caption).enabled
        screen.find(kind=ui.button, content=caption).click()
        await screen.should_see(title)


async def test_add_a_wine_then_its_prices(screen: User, db):
    await screen.open("/wines")
    await screen.should_see("New wine")
    await screen.should_see("Save the new wine first")
    element(screen, ui.input, "Wine code").value = "NEW_1"
    element(screen, ui.input, "Name").value = "Ancely"
    element(screen, ui.number, "Vintage").value = 2007
    element(screen, ui.input, "Type").value = "Rød"                        # a data value, as it is
    screen.find(marker="save").click()
    await screen.should_see("is saved.")
    [(item_id, name, vintage, kind)] = query(db, "SELECT item_id, name, vintage, item_type FROM items WHERE item_code = 'NEW_1'")
    assert (name, vintage, kind) == ("Ancely", 2007, "Rød")
    await screen.should_see(f"The prices of wine {item_id}.")              # the new wine stays on the screen
    element(screen, ui.number, "Price incl. VAT").value = 165
    assert element(screen, ui.number, "VAT %").value == 25                  # the default
    screen.find(kind=ui.button, content="Save sales price").click()
    await screen.should_see("The sales price is saved.")
    element(screen, ui.number, "Cost price").value = 80
    screen.find(kind=ui.button, content="Save cost price").click()
    await screen.should_see("The cost price is saved.")
    assert query(db, "SELECT sales_price, vat_rate FROM prices_sales WHERE item_id = ?", item_id) == [(165, 0.25)]
    assert query(db, "SELECT price_type, cost_price FROM prices_cost WHERE item_id = ?", item_id) == [("Standard", 80)]


async def test_wine_problems_are_marked_at_the_fields(screen: User, db):
    await screen.open("/wines")
    element(screen, ui.input, "Wine code").value = "ra_10"                  # the code of wine 10 (case ignored)
    screen.find(marker="save").click()
    await screen.should_see("The wine is not saved")
    assert element(screen, ui.input, "Wine code").props["error-message"] == "Another wine (id 10) has the code ra_10."
    assert element(screen, ui.input, "Name").props["error-message"] == "Enter the name."
    assert element(screen, ui.number, "Vintage").props["error-message"] == "Enter the vintage."


async def test_edit_and_delete_a_wine_as_access(screen: User, db):
    await screen.open("/wines")
    pick_row(screen, "list", "item_id", 11)
    await screen.should_see("Wine 11")
    element(screen, ui.input, "Country").value = "Italien"
    screen.find(marker="save").click()
    await screen.should_see("Wine 11 is saved.")
    assert query(db, "SELECT country FROM items WHERE item_id = 11") == [("Italien",)]
    screen.find(marker="flag").click()                                     # "Delete (discontinue)"
    await screen.should_see("It is marked discontinued")
    screen.find(marker="flag-yes").click()
    await screen.should_see("Wine 11 is discontinued.")
    assert query(db, "SELECT is_discontinued FROM items WHERE item_id = 11") == [(1,)]
    assert 11 not in {r["item_id"] for r in main_list(screen).rows}          # the list hides it, as Access
    screen.find(marker="flag").click()                                     # now "Restore", no question
    await screen.should_see("Wine 11 is restored.")
    assert query(db, "SELECT is_discontinued FROM items WHERE item_id = 11") == [(0,)]


async def test_delete_a_sales_price_really_deletes_it(screen: User, db):
    await screen.open("/wines")
    pick_row(screen, "list", "item_id", 10)
    await screen.should_see("The prices of wine 10.")
    pick_row(screen, "sales-price-list", "sales_price_id", 2)
    screen.find(kind=ui.button, content="Delete sales price").click()
    await screen.should_see("The row is removed")
    screen.find(marker="delete-sales-price-yes").click()
    await screen.should_see("The sales price is deleted.")
    assert query(db, "SELECT sales_price_id FROM prices_sales WHERE item_id = 10") == [(1,)]


async def test_customer_add_and_hide(screen: User, db):
    await screen.open("/customers")
    element(screen, ui.input, "Customer name").value = "New Shop"
    element(screen, ui.number, "Postal code").value = 8000
    element(screen, ui.input, "City").value = "Århus"
    screen.find(marker="save").click()
    await screen.should_see("is saved.")
    [(number, code, city)] = query(db, "SELECT customer_id, postal_code, city FROM customers WHERE customer_name = 'New Shop'")
    assert (code, city) == (8000, "Århus")
    screen.find(marker="flag").click()                                     # "Delete (hide)"
    await screen.should_see("The customer is hidden, as in Access")
    screen.find(marker="flag-yes").click()
    await screen.should_see(f"Customer {number} is hidden.")
    assert query(db, "SELECT is_hidden FROM customers WHERE customer_id = ?", number) == [(1,)]


async def test_warehouse_add_and_no_delete(screen: User, db):
    await screen.open("/warehouses")
    await screen.should_see("Warehouses cannot be deleted")
    await screen.should_not_see(marker="flag")                             # no delete button
    element(screen, ui.input, "Name").value = "Cellar"
    screen.find(marker="save").click()
    await screen.should_see("is saved.")
    assert query(db, "SELECT warehouse_name FROM warehouses ORDER BY warehouse_id DESC LIMIT 1") == [("Cellar",)]


async def test_reopen_a_closed_invoice_from_the_invoice_screen(screen: User, db):
    await screen.open("/invoices/closed")
    assert [r["invoice_id"] for r in main_list(screen).rows] == [2]
    pick_row(screen, "list", "invoice_id", 2)
    screen.find(kind=ui.button, content="Open invoice").click()
    await screen.should_see("This invoice is closed.")
    screen.find(kind=ui.button, content="Reopen invoice").click()
    await screen.should_see("Reopen invoice 2?")
    screen.find(marker="confirm-reopen").click()
    await screen.should_see("Invoice 2 is open again.")
    assert header_row(db, 2)["is_closed"] == 0


async def test_open_invoice_has_no_reopen_button(screen: User):
    await screen.open("/invoice/1")
    await screen.should_see("Close invoice")
    await screen.should_not_see(kind=ui.button, content="Reopen invoice")


async def test_menu_groups_in_order_with_the_buttons_in_them(screen: User):
    await screen.open("/")
    groups = ("Invoice", "Stock", "Prices", "Master data maintenance", "Reports")
    items = sorted(screen.find(ui.label).elements | screen.find(ui.button).elements, key=lambda e: e.id)  # creation order
    menu = [("group" if isinstance(e, ui.label) else "button", e.text) for e in items
            if isinstance(e, ui.button) or e.text in groups]
    headings = [i for i, (kind, _) in enumerate(menu) if kind == "group"]
    assert [menu[i][1] for i in headings] == list(groups)
    assert [menu[i + 1][1] for i in headings] == ["Invoice", "Stock change", "Sales price list", "Wine list",
                                                  "Customer list"]
