"""Master data screens (design doc §6.6, decision 18; step 10): wines with their sales and cost prices,
customers and warehouses. They replace the Access forms fVinliste_Vedligehold, fPrisliste_Salg,
fPrisliste_Cost, fKunder and fLagre.

"Delete" works as in Access: a wine is marked discontinued and a customer is hidden (both can be undone);
a warehouse cannot be deleted; a price row is really deleted (decision 19)."""
from nicegui import ui

from winedb.db import connect
from winedb.invoices import cost_prices, sales_prices
from winedb.masterdata import (delete_cost_price, delete_sales_price, get_customer_record, get_wine, list_customer_records,
                               list_warehouse_records, list_wines, save_cost_price, save_customer, save_sales_price,
                               save_warehouse, save_wine, set_customer_hidden, set_wine_discontinued, suggestions)
from winedb.ui.forms import Field, Flag, Screen, confirm, make_input, master_screen, run_write, shown_value, watch_marks


def _suggest(table: str, column: str):
    return lambda conn: suggestions(conn, table, column)


def money(value) -> str:
    return "" if value is None else f"{value:,.2f}"


# --- Wines and their prices ---

def _price_list(*, title: str, noun: str, key: str, columns: dict, fields: list[Field], load, save, delete,
                to_form, from_form, note: str = ""):
    """One price list of the selected wine: a list, an entry row and the buttons. Returns show(item_id)."""
    state = {"item": None, "id": None, "rows": {}}
    conn = connect()
    try:
        hints = {f.name: f.suggest(conn) if f.suggest else [] for f in fields}
    finally:
        conn.close()
    with ui.column().classes("grow basis-0"):
        ui.label(title).classes("text-lg font-bold")
        if note:
            ui.label(note).classes("text-sm opacity-70")
        grid = ui.table(columns=[{"name": c, "label": caption, "field": c, "align": "left"} for c, caption in columns.items()],
                        rows=[], row_key=key, selection="single").props("dense").classes("w-full").mark(f"{noun.replace(' ', '-')}-list")
        inputs = {}
        with ui.row().classes("w-full no-wrap"):
            for f in fields:
                inputs[f.name] = make_input(f, hints[f.name])
        problems = ui.label("").classes("text-negative")
        with ui.row():
            save_button = ui.button(f"Save {noun}").props("no-caps")
            ui.button(f"New {noun}", on_click=lambda: new()).props("no-caps flat")
            delete_button = ui.button(f"Delete {noun}").props("no-caps flat color=negative")
    watch_marks(inputs)

    def refresh() -> None:
        conn = connect()
        try:
            rows = load(conn, state["item"]) if state["item"] is not None else []
        finally:
            conn.close()
        state["rows"] = {r[key]: r for r in rows}
        grid.rows = [{**r, **{c: money(r[c]) for c in ("sales_price", "cost_price") if c in r},
                      **({"vat_percent": f"{(r['vat_rate'] or 0) * 100:g} %"} if "vat_rate" in r else {})} for r in rows]

    def fill(form: dict) -> None:
        for f in fields:
            inputs[f.name].value = shown_value(f, form.get(f.name, f.default))
        problems.text = ""

    def new() -> None:
        state["id"] = None
        grid.selected = []
        fill({})
        delete_button.disable()
        for element in (*inputs.values(), save_button):
            element.set_enabled(state["item"] is not None)

    def pick(e) -> None:
        if not e.selection:
            return
        state["id"] = e.selection[0][key]
        fill(to_form(state["rows"][state["id"]]))
        delete_button.enable()

    def on_save() -> None:
        form = {f.name: inputs[f.name].value for f in fields}
        if run_write(lambda conn: save(conn, state["item"], from_form(form), state["id"]), inputs, problems,
                     f"The {noun} is not saved") is None:
            return
        ui.notify(f"The {noun} is saved.", type="positive")
        refresh()
        new()

    async def on_delete() -> None:
        if not await confirm(f"Delete this {noun}? The row is removed (as in Access). Invoice lines keep their own "
                             "copy of the price.", f"Delete {noun}", f"delete-{noun.replace(' ', '-')}"):
            return
        if run_write(lambda conn: delete(conn, state["item"], state["id"]) or True, inputs, problems,
                     f"The {noun} is not deleted") is None:
            return
        ui.notify(f"The {noun} is deleted.", type="positive")
        refresh()
        new()

    save_button.on_click(on_save)
    delete_button.on_click(on_delete)
    grid.on_select(pick)

    def show(item_id) -> None:
        state["item"] = item_id
        refresh()
        new()
    return show


def _wine_prices():
    with ui.card().classes("w-full"):
        hint = ui.label("").classes("text-sm opacity-70")
        with ui.row().classes("w-full no-wrap gap-8 items-start"):
            show_sales = _price_list(
                title="Sales prices", noun="sales price", key="sales_price_id",
                columns={"price_type": "Price type", "sales_price": "Price incl. VAT", "vat_percent": "VAT"},
                fields=[Field("price_type", "Price type", "suggest", _suggest("prices_sales", "price_type")),
                        Field("sales_price", "Price incl. VAT", "number"),
                        Field("vat_rate", "VAT %", "number", default=25)],
                load=sales_prices, save=save_sales_price, delete=delete_sales_price,
                to_form=lambda r: {**r, "vat_rate": None if r["vat_rate"] is None else round(r["vat_rate"] * 100, 6)},
                from_form=lambda f: {**f, "vat_rate": None if f["vat_rate"] is None else f["vat_rate"] / 100})
            show_cost = _price_list(
                title="Cost prices", noun="cost price", key="cost_price_id",
                columns={"price_type": "Price type", "cost_price": "Cost price"},
                fields=[Field("price_type", "Price type", "suggest", _suggest("prices_cost", "price_type"), default="Standard"),
                        Field("cost_price", "Cost price", "number")],
                load=cost_prices, save=save_cost_price, delete=delete_cost_price,
                to_form=lambda r: r, from_form=lambda f: f,
                note='The first price of type "Standard" is the default cost on a new invoice line.')

    def show(item_id) -> None:
        hint.text = (f"The prices of wine {item_id}." if item_id is not None
                     else "Save the new wine first; then add its prices here.")
        show_sales(item_id)
        show_cost(item_id)
    return show


WINES = Screen(
    title="Wines", noun="wine", key="item_id",
    columns=["item_id", "item_code", "name", "vintage", "producer", "country", "item_type", "bottle_size",
             "is_private", "is_discontinued"],
    fields=[Field("item_code"), Field("name"), Field("vintage", kind="whole"),
            Field("producer", kind="suggest", suggest=_suggest("items", "producer")),
            Field("country", kind="suggest", suggest=_suggest("items", "country")),
            Field("region", kind="suggest", suggest=_suggest("items", "region")),
            Field("item_type", kind="suggest", suggest=_suggest("items", "item_type")),
            Field("bottle_size", kind="suggest", suggest=_suggest("items", "bottle_size")),
            Field("drink_by_year", kind="whole"), Field("mature_year", kind="whole"),
            Field("is_private", kind="flag"), Field("comment", kind="textarea")],
    load=lambda conn, flagged: list_wines(conn, include_discontinued=flagged),
    get=get_wine, save=lambda conn, values, row_id: save_wine(conn, values, row_id),
    flag=Flag("is_discontinued", "Show discontinued wines", "Delete (discontinue)", "Restore",
              "This wine is discontinued (deleted). Restore it to use it again.",
              "Delete wine {id}? It is marked discontinued, as in Access: it leaves the lists and pickers, and its "
              "history stays. You can restore it.",
              "Wine {id} is discontinued.", "Wine {id} is restored.", set_wine_discontinued),
    extra=_wine_prices)

CUSTOMERS = Screen(
    title="Customers", noun="customer", key="customer_id",
    columns=["customer_id", "customer_name", "address", "postal_code", "city", "phone", "email", "on_mailing_list",
             "is_hidden"],
    fields=[Field("customer_name"), Field("first_name"), Field("last_name"), Field("address"),
            Field("postal_code", kind="whole"), Field("city"), Field("phone"), Field("email"),
            Field("on_mailing_list", kind="flag"), Field("comment", kind="textarea")],
    load=lambda conn, flagged: list_customer_records(conn, include_hidden=flagged),
    get=get_customer_record, save=lambda conn, values, row_id: save_customer(conn, values, row_id),
    flag=Flag("is_hidden", "Show hidden customers", "Delete (hide)", "Show again",
              "This customer is hidden (deleted). Show it again to use it on new invoices.",
              "Delete customer {id}? The customer is hidden, as in Access: it leaves the lists and the invoice "
              "picker, and old invoices keep it. You can show it again.",
              "Customer {id} is hidden.", "Customer {id} is shown again.", set_customer_hidden))

WAREHOUSES = Screen(
    title="Warehouses", noun="warehouse", key="warehouse_id",
    columns=["warehouse_id", "warehouse_name", "comment"],
    fields=[Field("warehouse_name", "Name"), Field("comment", kind="textarea")],
    load=lambda conn, flagged: list_warehouse_records(conn),
    get=lambda conn, row_id: next((w for w in list_warehouse_records(conn) if w["warehouse_id"] == row_id), None),
    save=lambda conn, values, row_id: save_warehouse(conn, values, row_id),
    no_delete_text="Warehouses cannot be deleted (as in Access).")


@ui.page("/wines")
def wines_page():
    master_screen(WINES)


@ui.page("/customers")
def customers_page():
    master_screen(CUSTOMERS)


@ui.page("/warehouses")
def warehouses_page():
    master_screen(WAREHOUSES)
