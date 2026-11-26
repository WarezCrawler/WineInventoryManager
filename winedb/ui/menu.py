"""Main menu (design doc §6.1, replaces the Access form fNavigation). All text is British English."""
from nicegui import app, ui

from winedb.db import connect
from winedb.invoices import open_invoices
from winedb.settings import load_settings, logo_path
from winedb.ui.labels import label

NO_CUSTOMER = "(no customer)"

# The menu, in groups (owner, 2026-11-26). (caption, page); a page of None is a button that needs a selected
# invoice and is set up in menu_page(). The price lists are part of the wine screen (step 10).
STOCK_BUTTONS = [("Stock change", "/stock-change"), ("Mass stock registration", "/stock-mass")]
PRICE_BUTTONS = [("Sales price list", "/wines"), ("Cost price list", "/wines")]
MASTER_DATA_BUTTONS = [("Wine list", "/wines"), ("Maintain customers", "/customers"), ("Warehouses", "/warehouses")]
# The Access functions that come after v1 (design doc §9). They are shown, but disabled.
LATER_BUTTONS = ["Customer list", "Stock report", "Export mailing list", "Advanced settings"]


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
        ui.link("Tables", "/tables")

    def group(title: str) -> None:
        ui.label(title).classes("text-xs font-bold uppercase opacity-60 mt-3")

    def go(caption: str, path: str, style: str = "no-caps dense"):
        return ui.button(caption, on_click=lambda: ui.navigate.to(path)).props(style).classes("w-full")

    # Layout (owner): the menu on the left, in groups; the list of open invoices on the right.
    with ui.row().classes("w-full no-wrap items-start gap-8"):
        menu = ui.column().classes("w-72 gap-1")
        with ui.column().classes("grow"):
            ui.label("Open invoices").classes("text-lg font-bold")
            columns = [{"name": c, "label": label(c), "field": c, "align": "left", "sortable": True}
                       for c in ("invoice_id", "customer_id", "customer_name", "is_deleted")]
            # The overview of the lines (cancelled lines left out). The numbers stay numbers, so they sort.
            columns[3:3] = [
                {"name": "total_quantity", "label": label("total_quantity"), "field": "total_quantity", "align": "right",
                 "sortable": True},
                {"name": "wine_count", "label": label("wine_count"), "field": "wine_count", "align": "right", "sortable": True},
                {"name": "amount_ex_vat", "label": label("invoice_total_ex_vat"), "field": "amount_ex_vat", "align": "right",
                 "sortable": True,
                 ":format": "value => value.toLocaleString('en-GB', {minimumFractionDigits: 2, maximumFractionDigits: 2})"},
            ]
            table = ui.table(columns=columns, rows=_rows(), row_key="invoice_id", selection="single", pagination=20)
            table.classes("w-full").props("dense")

        with menu:
            def selected() -> dict | None:
                return table.selected[0] if table.selected else None

            def open_lines() -> None:
                ui.navigate.to(f"/invoice/{selected()['invoice_id']}/lines")

            def open_header() -> None:
                inv = selected()
                ui.navigate.to(f"/invoice/{inv['invoice_id']}" if inv else "/invoice/new")

            group("Invoice")
            ui.button("Invoice", on_click=open_header).props("no-caps dense").classes("w-full").mark("invoice").tooltip(
                "The details of the selected invoice. With no invoice selected: a new invoice.")
            lines_button = ui.button("Open invoice lines", on_click=open_lines).props("no-caps dense").classes("w-full")
            invoice_button = ui.button("Generate invoice", on_click=lambda: ui.navigate.to(
                f"/invoice/{selected()['invoice_id']}/preview")).props("no-caps dense").classes("w-full").tooltip(
                "Preview the selected invoice and create its PDF")
            go("Reopen closed invoice", "/invoices/closed", "no-caps dense flat")
            for button in (lines_button, invoice_button):
                button.disable()
            table.on_select(lambda e: [b.set_enabled(bool(e.selection)) for b in (lines_button, invoice_button)])

            group("Stock")
            for caption, path in STOCK_BUTTONS:
                go(caption, path)
            group("Prices")
            for caption, path in PRICE_BUTTONS:
                go(caption, path, "no-caps dense flat")
            group("Master data maintenance")
            for caption, path in MASTER_DATA_BUTTONS:
                go(caption, path, "no-caps dense flat")
            group("Reports")
            for caption in LATER_BUTTONS:
                ui.button(caption).props("no-caps dense flat disable").classes("w-full").tooltip("Comes after v1")
            ui.separator().classes("mt-3")
            ui.button("Quit", on_click=app.shutdown).props("no-caps dense outline").classes("w-full")
