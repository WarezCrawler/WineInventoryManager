"""Invoice lines screen (design doc §5.1, §5.2, §6.4; replaces the Access form fVinlager_Salg).

A grid of the invoice's lines with the totals, and below it the entry panel for one line (new or selected),
as the Access split form. The amounts are calculated with logic.line_amounts(), the formula that
invoices.save_line() stores."""
import logging

from nicegui import ui

from winedb.db import connect
from winedb.invoices import (cancel_line, close, cost_prices, get_header, lines, sales_prices, save_line, totals,
                             wines_for_sale)
from winedb.logic import default_cost, line_amounts
from winedb.masterdata import list_warehouses
from winedb.stock import on_hand
from winedb.ui.labels import label
from winedb.validation import ValidationError

log = logging.getLogger(__name__)

# The entry field that a problem from invoices.save_line() is about, found by the words of its message.
PROBLEM_FIELDS = (("wine", "wine"), ("warehouse", "warehouse"), ("quantity", "quantity"), ("sales price", "price"),
                  ("vat rate", "vat"), ("discount", "discount"), ("cost price", "cost"))

GRID_COLUMNS = ("sales_line_id", "wine", "warehouse_name", "quantity", "sales_price", "discount", "price_type",
                "vat_percent", "amount_ex_vat", "amount_incl_vat", "line_status")


def money(value) -> str:
    return f"{(value or 0):,.2f}"


def _wine_text(w: dict) -> str:
    flags = [t for t, on in (("discontinued", w.get("is_discontinued")), ("private", w.get("is_private"))) if on]
    extra = ", ".join(str(w[c]) for c in ("item_type", "bottle_size") if w.get(c))
    return (f"Code {w['item_code']} – {w['name']} {w['vintage']}" + (f" ({extra})" if extra else "")
            + (f" [{', '.join(flags)}]" if flags else ""))


def _grid_row(r: dict) -> dict:
    return {**r,
            "wine": f"{r['item_code'] or r['item_id']} – {r['name'] or ''} {r['vintage'] or ''}".strip(),
            "warehouse_name": r["warehouse_name"] or (f"({r['warehouse_id']})" if r["warehouse_id"] is not None else ""),
            "sales_price": money(r["sales_price"]), "discount": money(r["discount"]),
            "vat_percent": f"{(r['vat_rate'] or 0) * 100:g} %",
            "amount_ex_vat": money(r["amount_ex_vat"]), "amount_incl_vat": money(r["amount_incl_vat"]),
            "price_type": r["price_type"] or "",
            "line_status": "Cancelled" if r["is_deleted"] else ""}


@ui.page("/invoice/{invoice_id}/lines")
def invoice_lines_page(invoice_id: int):
    conn = connect()
    try:
        header = get_header(conn, invoice_id)
        wines = wines_for_sale(conn) if header else []
        warehouses = list_warehouses(conn)
    finally:
        conn.close()

    with ui.header().classes("items-center"):
        ui.label(f"Invoice {invoice_id} – lines").classes("text-xl font-bold")
        ui.space()
        ui.link("Invoice", f"/invoice/{invoice_id}").classes("text-white")
        ui.link("Invoice preview", f"/invoice/{invoice_id}/preview").classes("text-white")
        ui.link("Main menu", "/").classes("text-white")
    if header is None:
        ui.label(f"Invoice {invoice_id} does not exist.").classes("text-negative")
        return

    closed = header["is_closed"] == 1
    customer = header["customer_name"] or "(no customer)"
    date = (header["invoice_date"] or "")[:10] or "no date"
    ui.label(f"Customer: {customer} · {label('invoice_date')}: {date}").classes("text-sm")
    if closed:
        ui.label("This invoice is closed. Its lines are read-only.").classes("font-bold text-warning")
    elif header["is_deleted"] == 1:
        ui.label("This invoice has the delete flag.").classes("font-bold text-warning")

    columns = [{"name": c, "label": label(c), "field": c, "align": "left"} for c in GRID_COLUMNS]
    grid = ui.table(columns=columns, rows=[], row_key="sales_line_id", selection="single").props("dense").classes("w-full")
    total_label = ui.label("").classes("font-bold")

    wine_by_id = {w["item_id"]: w for w in wines}
    state = {"line_id": None, "setting": False, "price_rows": [], "cost_rows": []}

    with ui.card().classes("w-full"):
        panel_title = ui.label("").classes("text-lg font-bold")
        with ui.row().classes("w-full no-wrap gap-6 items-start"):
            with ui.column().classes("w-[30rem]"):
                wine = ui.select({w["item_id"]: _wine_text(w) for w in wines}, label="Wine (type the code or the name)",
                                 with_input=True).classes("w-full")
                warehouse = ui.select({w["warehouse_id"]: w["warehouse_name"] or f"Warehouse {w['warehouse_id']}" for w in warehouses},
                                      label=label("warehouse_id")).classes("w-full")
                stock_label = ui.label("").classes("text-sm opacity-80")
                quantity = ui.number(label="Quantity (negative for a return)", step=1, precision=0).classes("w-full")
                comment = ui.input(label("comment")).classes("w-full")
            with ui.column().classes("w-[26rem]"):
                price_pick = ui.select({}, label="Pick a sales price").classes("w-full")
                price = ui.number(label="Unit price incl. VAT (type to set your own)", format="%.2f").classes("w-full")
                price_type_label = ui.label("").classes("text-sm opacity-80")
                vat = ui.number(label="VAT %", format="%g").classes("w-full")
                discount = ui.number(label="Discount incl. VAT (amount off the line)", format="%.2f").classes("w-full")
                cost_pick = ui.select({}, label="Pick a cost price").classes("w-full")
                cost = ui.number(label="Unit cost price", format="%.2f").classes("w-full")
        amounts_label = ui.label("").classes("font-bold")
        problems = ui.label("").classes("text-negative")
        with ui.row():
            save = ui.button("Save line").props("no-caps")
            new = ui.button("New line").props("no-caps flat")
            undo = ui.button("Undo").props("no-caps flat")
            cancel_button = ui.button("Cancel line").props("no-caps flat color=negative")
            close_button = ui.button("Close invoice").props("no-caps outline")

    fields = (wine, warehouse, quantity, comment, price_pick, price, vat, discount, cost_pick, cost)
    inputs = {"wine": wine, "warehouse": warehouse, "quantity": quantity, "price": price, "vat": vat,
              "discount": discount, "cost": cost}

    def clear_field(element) -> None:
        element.props.pop("error", None)
        element.props.pop("error-message", None)

    def clear_problems() -> None:
        problems.text = ""
        for element in inputs.values():
            clear_field(element)

    def show_problems(messages: list[str], what: str = "The line is not saved") -> None:
        """Show why an action failed: in red above the buttons, in red at each field concerned, and in a pop-up,
        because the panel can be below the visible part of the window."""
        clear_problems()
        for message in messages:
            name = next((n for word, n in PROBLEM_FIELDS if word in message.lower()), None)
            if name:
                inputs[name].props["error"] = True
                inputs[name].props["error-message"] = message
        problems.text = " ".join(messages)
        ui.notify(f"{what}: {problems.text}", type="negative", multi_line=True)
    if closed:
        for element in (*fields, save, new, undo, cancel_button, close_button):
            element.disable()

    def refresh_grid() -> None:
        conn = connect()
        try:
            rows, sums = lines(conn, invoice_id), totals(conn, invoice_id)
        finally:
            conn.close()
        grid.rows = [_grid_row(r) for r in rows]
        total_label.text = (f"Invoice total excl. VAT: {money(sums['amount_ex_vat'])} · "
                            f"incl. VAT: {money(sums['amount_incl_vat'])} (cancelled lines are left out)")

    def load_price_lists(item_id) -> None:
        conn = connect()
        try:
            state["price_rows"] = sales_prices(conn, item_id) if item_id else []
            state["cost_rows"] = cost_prices(conn, item_id) if item_id else []
        finally:
            conn.close()
        price_pick.options = {p["sales_price_id"]: f"{p['price_type'] or '-'}: {money(p['sales_price'])} ({(p['vat_rate'] or 0) * 100:g} % VAT)"
                              for p in state["price_rows"]}
        cost_pick.options = {c["cost_price_id"]: f"{c['price_type'] or '-'}: {money(c['cost_price'])}" for c in state["cost_rows"]}
        price_pick.value = cost_pick.value = None
        price_pick.update()
        cost_pick.update()

    def show_live() -> None:
        """The stock of the wine in the warehouse, and the amounts of the line as they will be saved."""
        if wine.value is not None and warehouse.value is not None:
            conn = connect()
            try:
                stock_label.text = f"On-hand stock in this warehouse: {on_hand(conn, wine.value, warehouse.value)}"
            finally:
                conn.close()
        else:
            stock_label.text = ""
        a = line_amounts(price.value, quantity.value, discount.value, (vat.value or 0) / 100, cost.value)
        amounts_label.text = (f"Line total incl. VAT: {money(a.amount_incl_vat)} · excl. VAT: {money(a.amount_ex_vat)}"
                              f" · cost: {money(a.amount_cost)}")

    def set_values(values: dict) -> None:
        state["setting"] = True
        try:
            for element, key in ((wine, "item_id"), (warehouse, "warehouse_id"), (quantity, "quantity"),
                                 (comment, "comment"), (price, "sales_price"), (discount, "discount"),
                                 (cost, "cost_price")):
                element.value = values.get(key)
            vat.value = None if values.get("vat_rate") is None else round(values["vat_rate"] * 100, 6)
            state["price_type"] = values.get("price_type") or ""
            price_type_label.text = f"Price type: {state['price_type']}" if state["price_type"] else "Price typed by hand"
        finally:
            state["setting"] = False
        show_live()

    def new_line() -> None:
        state["line_id"] = None
        grid.selected = []
        panel_title.text = "New line"
        load_price_lists(None)
        set_values({"warehouse_id": header["warehouse_id"], "discount": 0})
        clear_problems()
        cancel_button.disable()

    def load_line(line_id: int) -> None:
        row = next((r for r in grid.rows if r["sales_line_id"] == line_id), None)
        if row is None:
            return
        conn = connect()
        try:
            stored = next(r for r in lines(conn, invoice_id) if r["sales_line_id"] == line_id)
        finally:
            conn.close()
        state["line_id"] = line_id
        panel_title.text = f"Line {line_id}" + (" (cancelled, read-only)" if stored["is_deleted"] else "")
        load_price_lists(stored["item_id"])
        set_values(stored)
        clear_problems()
        if not closed:
            for element in (*fields, save, cancel_button):
                element.set_enabled(not stored["is_deleted"])

    def on_wine(_) -> None:
        if state["setting"]:
            return
        load_price_lists(wine.value)
        cost.value = default_cost(state["cost_rows"])        # Access: GetStandardCostPris when the wine is picked
        show_live()

    def on_price_pick(_) -> None:
        if state["setting"] or price_pick.value is None:
            return
        p = next(r for r in state["price_rows"] if r["sales_price_id"] == price_pick.value)
        state["setting"] = True
        try:
            price.value, vat.value = p["sales_price"], round((p["vat_rate"] or 0) * 100, 6)
        finally:
            state["setting"] = False
        state["price_type"] = p["price_type"] or ""
        price_type_label.text = f"Price type: {state['price_type']}"
        show_live()

    def on_price_typed(_) -> None:
        if state["setting"]:
            return
        state["price_type"] = ""                              # Access: a typed price clears the price list choice
        price_pick.value = None
        price_type_label.text = "Price typed by hand"
        show_live()

    def on_cost_pick(_) -> None:
        if state["setting"] or cost_pick.value is None:
            return
        cost.value = next(r for r in state["cost_rows"] if r["cost_price_id"] == cost_pick.value)["cost_price"]
        show_live()

    def values() -> dict:
        return {"item_id": wine.value, "warehouse_id": warehouse.value, "quantity": quantity.value,
                "sales_price": price.value, "price_type": state.get("price_type", ""),
                "vat_rate": None if vat.value is None else vat.value / 100, "discount": discount.value,
                "cost_price": cost.value, "comment": comment.value}

    def on_save() -> None:
        conn = connect()
        try:
            line_id = save_line(conn, invoice_id, values(), state["line_id"])
        except ValidationError as e:
            show_problems(e.problems)
            return
        except Exception as e:  # noqa: BLE001  (never fail without a message)
            log.exception("Saving a line of invoice %s failed", invoice_id)
            show_problems([f"Unexpected error: {e}"])
            return
        finally:
            conn.close()
        ui.notify(f"Line {line_id} is saved.", type="positive")
        refresh_grid()
        new_line()

    async def on_cancel() -> None:
        line_id = state["line_id"]
        with ui.dialog() as dialog, ui.card():
            ui.label(f"Cancel line {line_id}? Its quantity and amounts become 0, and it is not printed. The line stays.")
            with ui.row():
                ui.button("Cancel line", on_click=lambda: dialog.submit(True)).props("no-caps color=negative").mark("confirm-cancel")
                ui.button("Keep the line", on_click=lambda: dialog.submit(False)).props("no-caps flat").mark("keep-line")
        if not await dialog:
            return
        conn = connect()
        try:
            cancel_line(conn, invoice_id, line_id)
        except ValidationError as e:
            show_problems(e.problems, "The line is not cancelled")
            return
        finally:
            conn.close()
        ui.notify(f"Line {line_id} is cancelled.", type="positive")
        refresh_grid()
        new_line()

    async def on_close() -> None:
        with ui.dialog() as dialog, ui.card():
            ui.label(f"Close invoice {invoice_id}? A closed invoice cannot be changed.")
            with ui.row():
                ui.button("Close invoice", on_click=lambda: dialog.submit(True)).props("no-caps").mark("confirm-close")
                ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("no-caps flat").mark("cancel-close")
        if not await dialog:
            return
        conn = connect()
        try:
            close(conn, invoice_id)
        except ValidationError as e:
            show_problems(e.problems, "The invoice is not closed")
            return
        finally:
            conn.close()
        ui.notify(f"Invoice {invoice_id} is closed.", type="positive")
        ui.navigate.to(f"/invoice/{invoice_id}/lines")

    def on_select(e) -> None:
        if e.selection:
            load_line(e.selection[0]["sales_line_id"])

    wine.on_value_change(on_wine)
    for element in (warehouse, quantity, vat, discount, cost):
        element.on_value_change(lambda _: None if state["setting"] else show_live())
    for element in inputs.values():                      # a changed field loses its red mark
        element.on_value_change(lambda _, element=element: clear_field(element))
    price_pick.on_value_change(on_price_pick)
    price.on_value_change(on_price_typed)
    cost_pick.on_value_change(on_cost_pick)
    grid.on_select(on_select)
    save.on_click(on_save)
    new.on_click(new_line)
    undo.on_click(lambda: load_line(state["line_id"]) if state["line_id"] else new_line())
    cancel_button.on_click(on_cancel)
    close_button.on_click(on_close)

    refresh_grid()
    if closed:
        panel_title.text = "Read-only"
    else:
        new_line()
