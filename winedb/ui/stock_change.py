"""Stock change screen (design doc §6.2, replaces the Access form fVinlager_Change)."""
from nicegui import ui

from winedb.db import connect
from winedb.masterdata import get_item, list_warehouses
from winedb.stock import add_movement, on_hand, recent_movements, wines_for_stock_change
from winedb.ui.labels import label
from winedb.validation import ValidationError, now_text

DETAIL_COLUMNS = ("name", "vintage", "producer", "country", "bottle_size", "item_type")
HISTORY_COLUMNS = ("created_at", "quantity", "comment")


def _item_text(item: dict) -> str:
    """The text of a wine in the wine picker: code, name and vintage, then type and size, then a
    marker if the wine is discontinued."""
    extra = ", ".join(str(item[c]) for c in ("item_type", "bottle_size") if item[c])
    text = f"Code {item['item_code']} – {item['name']} {item['vintage']}" + (f" ({extra})" if extra else "")
    return text + (" (discontinued)" if item.get("is_discontinued") else "")


def _whole_number(value) -> int | float | None:
    return int(value) if isinstance(value, float) and value.is_integer() else value


@ui.page("/stock-change")
def stock_change_page():
    conn = connect()
    try:
        items = wines_for_stock_change(conn)
        warehouses = list_warehouses(conn)
    finally:
        conn.close()

    with ui.header().classes("items-center"):
        ui.label("Stock change").classes("text-xl font-bold")
        ui.space()
        ui.link("Mass stock registration", "/stock-mass").classes("text-white")
        ui.link("Main menu", "/").classes("text-white")

    with ui.row().classes("w-full no-wrap items-start gap-8"):
        with ui.column().classes("w-[34rem]"):
            wine = ui.select({i["item_id"]: _item_text(i) for i in items}, label="Wine (type the code or the name)",
                             with_input=True, clearable=True).classes("w-full")
            details = ui.label("").classes("text-sm opacity-80")
            warehouse = ui.select({w["warehouse_id"]: w["warehouse_name"] or f"Warehouse {w['warehouse_id']}" for w in warehouses},
                                  label=label("warehouse_id"),
                                  value=warehouses[0]["warehouse_id"] if len(warehouses) == 1 else None).classes("w-full")
            quantity = ui.number(label="Quantity (negative to remove stock)", step=1, precision=0).classes("w-full")
            comment = ui.input(label("comment")).classes("w-full")
            date = ui.input(f"{label('created_at')} (YYYY-MM-DD HH:MM:SS)", value=now_text()).classes("w-full")
            stock_now = ui.label("").classes("font-bold")
            problems = ui.label("").classes("text-negative")
            with ui.row():
                save = ui.button("Save").props("no-caps")
                ui.button("Cancel", on_click=lambda: ui.navigate.to("/")).props("no-caps flat")

        with ui.column().classes("grow"):
            ui.label("Latest 20 movements of this wine in this warehouse").classes("text-lg font-bold")
            columns = [{"name": c, "label": label(c), "field": c, "align": "left"} for c in HISTORY_COLUMNS]
            history = ui.table(columns=columns, rows=[], row_key="stock_line_id").props("dense").classes("w-full")

    def refresh() -> None:
        """Show the wine details, the stock now and after the change, and the latest movements."""
        conn = connect()
        try:
            item = get_item(conn, wine.value) if wine.value is not None else None
            details.text = " · ".join(f"{label(c)}: {item[c]}" for c in DETAIL_COLUMNS if item[c] is not None) if item else ""
            if item is None or warehouse.value is None:
                stock_now.text, history.rows = "", []
                return
            current = on_hand(conn, wine.value, warehouse.value)
            rows = recent_movements(conn, wine.value, warehouse.value)
        finally:
            conn.close()
        change = _whole_number(quantity.value)
        after = f"; after this change: {current + change}" if isinstance(change, int) else ""
        stock_now.text = f"On-hand stock: {current}{after}"
        history.rows = rows

    def save_change() -> None:
        conn = connect()
        try:
            add_movement(conn, wine.value, warehouse.value, _whole_number(quantity.value), comment.value,
                         (date.value or "").strip())
        except ValidationError as e:
            problems.text = " ".join(e.problems)
            return
        finally:
            conn.close()
        problems.text = ""
        ui.notify("The stock change is saved.", type="positive")
        quantity.value, comment.value, date.value = None, "", now_text()
        refresh()

    for field in (wine, warehouse, quantity):
        field.on_value_change(lambda _: refresh())
    save.on_click(save_change)
