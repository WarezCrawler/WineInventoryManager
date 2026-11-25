"""Closed invoices (step 10; replaces the list of the Access form fFaktura_genaaben). The user picks a closed
invoice and opens its Invoice screen, which has the button "Reopen invoice"."""
from nicegui import ui

from winedb.db import connect
from winedb.invoices import closed_invoices
from winedb.ui.labels import label

NO_CUSTOMER = "(no customer)"


@ui.page("/invoices/closed")
def closed_invoices_page():
    conn = connect()
    try:
        rows = closed_invoices(conn)
    finally:
        conn.close()

    with ui.header().classes("items-center"):
        ui.label("Closed invoices").classes("text-xl font-bold")
        ui.space()
        ui.link("Main menu", "/").classes("text-white")

    ui.label("Pick an invoice and open it. Its Invoice screen has the button \"Reopen invoice\".").classes("text-sm")
    search = ui.input("Filter the list").props("clearable dense").classes("w-80")
    columns = [{"name": c, "label": label(c), "field": c, "align": "left", "sortable": True}
               for c in ("invoice_id", "customer_id", "customer_name", "invoice_date", "is_deleted")]
    table = ui.table(columns=columns, row_key="invoice_id", selection="single", pagination=15,
                     rows=[{**r, "customer_name": r["customer_name"] or NO_CUSTOMER, "invoice_date": (r["invoice_date"] or "")[:10],
                            "is_deleted": "Yes" if r["is_deleted"] else ""} for r in rows])
    table.classes("w-full max-w-4xl").props("dense").mark("list").bind_filter_from(search, "value")
    open_button = ui.button("Open invoice", on_click=lambda: ui.navigate.to(f"/invoice/{table.selected[0]['invoice_id']}"))
    open_button.props("no-caps").disable()
    table.on_select(lambda e: open_button.set_enabled(bool(e.selection)))
