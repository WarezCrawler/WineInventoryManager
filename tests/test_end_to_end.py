"""End-to-end test (design doc §8 step 11): the daily work from start to end through the screens, with the
simulated user, on one database. Every step uses the screen a user would use; the database is only read to
check the result.

New customer -> new wine with a sales and a cost price -> stock in -> new invoice -> two lines (one cancelled)
-> preview and PDF -> close -> reopen -> close again."""
import asyncio

from nicegui import ui
from nicegui.testing import User

from tests.test_ui import db, element, opened, pdf_folder, query, screen, select_line  # noqa: F401  (fixtures and helpers)
from winedb.db import connect
from winedb.stock import on_hand


async def wait_until(check, seconds: float = 3.0) -> None:
    """Wait for a write that the screen does after the click (a pop-up of an earlier step can still be shown)."""
    for _ in range(int(seconds / 0.05)):
        if check():
            return
        await asyncio.sleep(0.05)
    assert check()


async def test_daily_work_from_customer_to_closed_invoice(screen: User, db, pdf_folder, opened):
    # 1. A new customer
    await screen.open("/customers")
    element(screen, ui.input, "Customer name").value = "E2E Shop"
    element(screen, ui.input, "City").value = "Aarhus"
    screen.find(marker="save").click()
    await screen.should_see("is saved.")
    [(customer,)] = query(db, "SELECT customer_id FROM customers WHERE customer_name = 'E2E Shop'")

    # 2. A new wine, then its prices on the same screen
    await screen.open("/wines")
    element(screen, ui.input, "Wine code").value = "E2E_RA20"
    element(screen, ui.input, "Name").value = "Test Rosso"
    element(screen, ui.number, "Vintage").value = 2020
    element(screen, ui.input, "Type").value = "Rød"
    screen.find(marker="save").click()
    await screen.should_see("is saved.")
    [(wine,)] = query(db, "SELECT item_id FROM items WHERE item_code = 'E2E_RA20'")
    sales_type = min(screen.find(kind=ui.input, content="Price type").elements, key=lambda e: e.id)   # the sales price list
    sales_type.value = "Alm"
    element(screen, ui.number, "Price incl. VAT").value = 120
    screen.find(kind=ui.button, content="Save sales price").click()
    await screen.should_see("The sales price is saved.")
    element(screen, ui.number, "Cost price").value = 60                    # price type "Standard" by default
    screen.find(kind=ui.button, content="Save cost price").click()
    await screen.should_see("The cost price is saved.")
    [(price_id,)] = query(db, "SELECT sales_price_id FROM prices_sales WHERE item_id = ?", wine)

    # 3. Stock in
    await screen.open("/stock-change")
    element(screen, ui.select, "Wine").value = wine
    element(screen, ui.select, "Warehouse").value = 1
    element(screen, ui.number, "Quantity").value = 12
    element(screen, ui.input, "Comment").value = "Delivery"
    screen.find("Save").click()
    await screen.should_see("The stock change is saved.")
    await screen.should_see("On-hand stock: 12")

    # 4. A new invoice for the new customer
    await screen.open("/invoice/new")
    element(screen, ui.select, "Customer").value = customer
    element(screen, ui.select, "Default warehouse").value = 1
    element(screen, ui.input, "Invoice date").value = "2026-11-26"
    element(screen, ui.textarea, "Comment").value = "End-to-end"
    screen.find(kind=ui.button, content="Save").click()
    await screen.should_see("is saved.")
    [(invoice,)] = query(db, "SELECT MAX(invoice_id) FROM invoice_header")
    await screen.should_see(kind=ui.label, content=f"Invoice {invoice}")    # the screen moves to the saved invoice

    # 5. Two lines: the picked price with a discount, and a wrong line that is cancelled
    await screen.open(f"/invoice/{invoice}/lines")
    element(screen, ui.select, "Wine").value = wine
    assert element(screen, ui.number, "Unit cost price").value == 60        # the Standard cost
    element(screen, ui.select, "Pick a sales price").value = price_id
    element(screen, ui.number, "Quantity").value = 3
    element(screen, ui.number, "Discount").value = 10
    await screen.should_see("Line total incl. VAT: 350.00 · excl. VAT: 280.00 · cost: 180.00")
    screen.find("Save line").click()
    await screen.should_see("is saved.")
    element(screen, ui.select, "Wine").value = wine
    element(screen, ui.select, "Pick a sales price").value = price_id
    element(screen, ui.number, "Quantity").value = 5
    screen.find("Save line").click()
    await screen.should_see("is saved.")
    wrong = query(db, "SELECT MAX(sales_line_id) FROM invoice_lines WHERE invoice_id = ?", invoice)[0][0]
    select_line(screen, wrong)
    await screen.should_see(f"Line {wrong}")
    screen.find("Cancel line").click()
    await screen.should_see("Its quantity and amounts become 0")
    screen.find(marker="confirm-cancel").click()
    await screen.should_see(f"Line {wrong} is cancelled.")
    await screen.should_see("Invoice total excl. VAT: 280.00")

    # 6. Preview and PDF: the cancelled line is not on the printout
    await screen.open(f"/invoice/{invoice}/preview")
    await screen.should_see("Total quantity: 3")
    grid = screen.find(ui.table).elements.pop()
    assert [(r["quantity"], r["wine"]) for r in grid.rows] == [("3", "Test Rosso - Rød")]
    screen.find("Create PDF").click()
    await screen.should_see("The PDF is saved")
    assert opened == [pdf_folder / f"F{invoice}_ES{customer}_26-11-2026.pdf"]

    # 7. Close, reopen, close again
    for action, marker, closed in (("Close invoice", "confirm-close", 1), ("Reopen invoice", "confirm-reopen", 0),
                                   ("Close invoice", "confirm-close", 1)):
        await screen.open(f"/invoice/{invoice}")
        screen.find(kind=ui.button, content=action).click()
        await screen.should_see(f"{action.split()[0]} invoice {invoice}?")
        screen.find(marker=marker).click()
        await wait_until(lambda closed=closed: query(db, "SELECT is_closed FROM invoice_header WHERE invoice_id = ?", invoice) == [(closed,)])

    # The stored rows, as Access would store them (and the cancelled line, decision 16)
    assert query(db, "SELECT customer_id, is_closed, comment, warehouse_id, invoice_date, hide_subtotals, is_deleted"
                     " FROM invoice_header WHERE invoice_id = ?", invoice) == [
        (customer, 1, "End-to-end", 1, "2026-11-26 00:00:00", 0, 0)]
    lines = query(db, "SELECT item_id, quantity, sales_price, price_type, vat_rate, discount, cost_price, amount_incl_vat,"
                      " amount_ex_vat, amount_cost, is_deleted, warehouse_id FROM invoice_lines WHERE invoice_id = ?"
                      " ORDER BY sales_line_id", invoice)
    assert lines == [(wine, 3, 120, "Alm", 0.25, 10, 60, 350, 280, 180, 0, 1),
                     (wine, 0, 120, "Alm", 0.25, 0, 60, 0, 0, 0, 1, 1)]
    assert query(db, "SELECT quantity, comment FROM stock_transactions WHERE item_id = ?", wine) == [(12, "Delivery")]
    conn = connect(db)
    try:
        assert on_hand(conn, wine, 1) == 9                                  # 12 in, 3 sold; the cancelled line is left out
    finally:
        conn.close()
