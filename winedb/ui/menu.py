"""Main menu (design doc §6.1, replaces the Access form fNavigation). All text is British English."""
from nicegui import app, ui

from winedb.db import connect
from winedb.invoices import open_invoices
from winedb.settings import load_settings, logo_path
from winedb.ui.labels import label

NO_CUSTOMER = "(no customer)"

# The Access buttons that come after v1 (design doc §9). They are shown, but disabled.
LATER_BUTTONS = ["Customer list", "Stock report", "Advanced settings", "Export mailing list"]

# Master data and closed invoices (step 10). The two price lists are part of the wine screen.
MASTER_DATA_BUTTONS = [("Maintain customers", "/customers"), ("Reopen closed invoice", "/invoices/closed"),
                       ("Wine list", "/wines"), ("Sales price list", "/wines"), ("Cost price list", "/wines"),
                       ("Warehouses", "/warehouses")]


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
        try:
            logo = logo_path(load_settings())     # optional and not in git: the setting logo_file (.png or .svg)
        except ValueError:
            logo = None                           # a broken settings.json must not stop the main menu
        if logo:
            ui.image(logo).props("fit=contain").classes("h-10 w-56 bg-white rounded")
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

            lines_button = ui.button("Open invoice lines", on_click=open_lines).props("no-caps").classes("w-full")
            ui.button("Invoice", on_click=open_header).props("no-caps").classes("w-full").mark("invoice").tooltip(
                "The details of the selected invoice. With no invoice selected: a new invoice.")
            invoice_button = ui.button("Generate invoice", on_click=lambda: ui.navigate.to(
                f"/invoice/{selected()['invoice_id']}/preview")).props("no-caps").classes("w-full").tooltip(
                "Preview the selected invoice and create its PDF")
            ui.button("Stock change", on_click=lambda: ui.navigate.to("/stock-change")).props("no-caps").classes("w-full")
            ui.button("Mass stock registration", on_click=lambda: ui.navigate.to("/stock-mass")).props("no-caps").classes("w-full")
            for button in (lines_button, invoice_button):
                button.disable()
            table.on_select(lambda e: [b.set_enabled(bool(e.selection)) for b in (lines_button, invoice_button)])

            ui.separator()
            for caption, path in MASTER_DATA_BUTTONS:
                ui.button(caption, on_click=lambda path=path: ui.navigate.to(path)).props("no-caps flat").classes("w-full")
            ui.separator()
            for caption in LATER_BUTTONS:
                ui.button(caption).props("no-caps flat disable").classes("w-full").tooltip("Comes after v1")
            ui.separator()
            ui.button("Quit", on_click=app.shutdown).props("no-caps outline").classes("w-full")
