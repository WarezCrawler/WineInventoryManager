"""Main menu (design doc §6.1, replaces the Access form fNavigation). All text is British English."""
from nicegui import app, ui

from winedb.config import app_dir
from winedb.db import connect
from winedb.invoices import open_invoices
from winedb.ui.labels import label

NO_CUSTOMER = "(no customer)"

# The Access buttons that come after v1 (design doc §9). They are shown, but disabled.
LATER_BUTTONS = [
    "Maintain customers", "Customer list", "Reopen closed invoice", "Generate invoice", "Wine list",
    "Sales price list", "Cost price list", "Warehouses", "Stock report", "Advanced settings",
    "Export mailing list",
]


def _rows() -> list[dict]:
    conn = connect()
    try:
        invoices = open_invoices(conn)
    finally:
        conn.close()
    return [{**r, "customer_name": r["customer_name"] or NO_CUSTOMER, "is_deleted": "Yes" if r["is_deleted"] else ""}
            for r in invoices]


@ui.page("/")
def menu_page():
    with ui.header().classes("items-center"):
        logo = app_dir() / "logo.png"  # optional and not in git: the company logo, next to the program
        if logo.exists():
            ui.image(str(logo)).classes("w-12")
        ui.label("Wine Inventory Manager").classes("text-xl font-bold")
        ui.space()
        ui.link("Tables", "/tables").classes("text-white")

    with ui.row().classes("w-full no-wrap items-start gap-8"):
        with ui.column().classes("grow"):
            ui.label("Open invoices").classes("text-lg font-bold")
            columns = [{"name": c, "label": label(c), "field": c, "align": "left", "sortable": True}
                       for c in ("invoice_id", "customer_id", "customer_name", "is_deleted")]
            table = ui.table(columns=columns, rows=_rows(), row_key="invoice_id", selection="single", pagination=20)
            table.classes("w-full").props("dense")

        with ui.column().classes("w-80"):
            def selected() -> dict | None:
                return table.selected[0] if table.selected else None

            def open_lines() -> None:
                ui.navigate.to(f"/invoice/{selected()['invoice_id']}/lines")

            def open_header() -> None:
                inv = selected()
                ui.navigate.to(f"/invoice/{inv['invoice_id']}" if inv else "/invoice/new")

            lines_button = ui.button("Open invoice", on_click=open_lines).props("no-caps").classes("w-full")
            ui.button("Invoice details", on_click=open_header).props("no-caps").classes("w-full").tooltip(
                "The details of the selected invoice. With no invoice selected: a new invoice.")
            ui.button("Stock change", on_click=lambda: ui.navigate.to("/stock-change")).props("no-caps").classes("w-full")
            ui.button("Mass stock registration", on_click=lambda: ui.navigate.to("/stock-mass")).props("no-caps").classes("w-full")
            lines_button.disable()
            table.on_select(lambda e: lines_button.set_enabled(bool(e.selection)))

            ui.separator()
            for caption in LATER_BUTTONS:
                ui.button(caption).props("no-caps flat disable").classes("w-full").tooltip("Comes after v1")
            ui.separator()
            ui.button("Quit", on_click=app.shutdown).props("no-caps outline").classes("w-full")
