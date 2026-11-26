"""Invoice header screen (design doc §5.4, §6.3; replaces the Access form fFaktura)."""
from datetime import date

from nicegui import ui

from winedb.db import connect
from winedb.invoices import close, create_header, get_header, reopen, set_deleted, update_header
from winedb.masterdata import get_customer, list_customers, list_warehouses
from winedb.ui.labels import label
from winedb.validation import ValidationError

# The Access warning when the delete flag is set (the macro on the check box "Delete" in fFaktura),
# in British English.
DELETE_WARNING = "Be aware that this invoice will be suppressed, and must have zero quantity and amounts!"
NO_CUSTOMER = "(no customer)"


def _customer_text(customer: dict) -> str:
    return f"{customer['customer_name']} ({customer['customer_id']})"


def _load(invoice_id: int | None) -> tuple[dict | None, list[dict], list[dict]]:
    conn = connect()
    try:
        header = get_header(conn, invoice_id) if invoice_id is not None else None
        customers = list_customers(conn)
        # The current customer stays selectable even if hidden (or missing): the screen shows what is stored.
        if header and header["customer_id"] not in {c["customer_id"] for c in customers}:
            current = get_customer(conn, header["customer_id"])
            customers = [current] + customers if current else customers
        return header, customers, list_warehouses(conn)
    finally:
        conn.close()


@ui.page("/invoice/new")
def new_invoice_page():
    _invoice_page(None)


@ui.page("/invoice/{invoice_id}")
def invoice_page(invoice_id: int):
    _invoice_page(invoice_id)


def _invoice_page(invoice_id: int | None) -> None:
    header, customers, warehouses = _load(invoice_id)
    title = "New invoice" if invoice_id is None else f"Invoice {invoice_id}"
    with ui.header().classes("items-center"):
        ui.label(title).classes("text-xl font-bold")
        ui.space()
        ui.link("Main menu", "/")
    if invoice_id is not None and header is None:
        ui.label(f"Invoice {invoice_id} does not exist.").classes("text-negative")
        return

    closed = bool(header and header["is_closed"] == 1)
    stored = {
        "customer_id": header["customer_id"] if header else None,
        "warehouse_id": header["warehouse_id"] if header else (warehouses[0]["warehouse_id"] if len(warehouses) == 1 else None),
        "invoice_date": (header["invoice_date"] or "")[:10] if header else date.today().isoformat(),
        "comment": (header["comment"] or "") if header else "",
        "hide_subtotals": bool(header["hide_subtotals"]) if header else False,
        "is_deleted": bool(header["is_deleted"]) if header else False,
    }
    by_id = {c["customer_id"]: c for c in customers}

    with ui.column().classes("w-[36rem] max-w-full"):
        if closed:
            ui.label("This invoice is closed. It cannot be changed.").classes("font-bold text-warning")
        elif header and header["is_deleted"] == 1:
            ui.label("This invoice has the delete flag.").classes("font-bold text-warning")
        with ui.row():                       # layout (owner): the buttons above the form
            save = ui.button("Save").props("no-caps")
            close_button = ui.button("Close invoice").props("no-caps outline")
            lines = ui.button("Open lines").props("no-caps flat")
            reopen_button = ui.button("Reopen invoice").props("no-caps outline")
            reopen_button.set_visibility(closed)
            ui.button("Back", on_click=lambda: ui.navigate.to("/")).props("no-caps flat")
        problems = ui.label("").classes("text-negative")
        customer = ui.select({c["customer_id"]: _customer_text(c) for c in customers}, label="Customer (type to search)",
                             with_input=True, value=stored["customer_id"] if stored["customer_id"] in by_id else None
                             ).classes("w-full")
        if header and stored["customer_id"] not in by_id:
            ui.label(f"Stored customer: {NO_CUSTOMER} (customer no. {stored['customer_id']})").classes("text-sm text-warning")
        details = ui.label("").classes("text-sm opacity-80 whitespace-pre-line")
        warehouse = ui.select({w["warehouse_id"]: w["warehouse_name"] or f"Warehouse {w['warehouse_id']}" for w in warehouses},
                              label="Default warehouse", value=stored["warehouse_id"], clearable=True).classes("w-full")
        with ui.input(f"{label('invoice_date')} (YYYY-MM-DD)", value=stored["invoice_date"]).classes("w-full") as invoice_date:
            with ui.menu().props("no-parent-event") as calendar:
                ui.date(mask="YYYY-MM-DD").bind_value(invoice_date)
            with invoice_date.add_slot("append"):
                ui.icon("edit_calendar").on("click", calendar.open).classes("cursor-pointer")
        comment = ui.textarea(label("comment"), value=stored["comment"]).classes("w-full")
        hide_subtotals = ui.checkbox(label("hide_subtotals"), value=stored["hide_subtotals"])
        deleted = ui.checkbox("Delete (the invoice is suppressed; the row stays)", value=stored["is_deleted"])

    fields = (customer, warehouse, invoice_date, comment, hide_subtotals, deleted)
    if closed:
        for field in (*fields, save, close_button):
            field.disable()
    if invoice_id is None:
        close_button.disable()
        lines.disable()

    def show_customer() -> None:
        c = by_id.get(customer.value)
        if not c:
            details.text = ""
            return
        place = " ".join(str(v) for v in (c["postal_code"], c["city"]) if v)
        details.text = "\n".join(v for v in (c["address"], place, f"{label('phone')}: {c['phone']}" if c["phone"] else "") if v)

    def changed() -> dict:
        now = {"customer_id": customer.value, "warehouse_id": warehouse.value,
               "invoice_date": (invoice_date.value or "").strip(), "comment": comment.value or "",
               "hide_subtotals": bool(hide_subtotals.value)}
        # The picker starts empty when the stored customer is not in the list (an old draft with customer 0).
        # Then the customer counts as changed only when the user picks one.
        shown = {**stored, "customer_id": stored["customer_id"] if stored["customer_id"] in by_id else None}
        return {k: v for k, v in now.items() if v != shown[k]}

    def save_changes() -> int | None:
        """Save; return the invoice number, or None if a problem was shown."""
        conn = connect()
        try:
            if invoice_id is None:
                number = create_header(conn, customer.value, warehouse.value, (invoice_date.value or "").strip(),
                                       comment.value, bool(hide_subtotals.value))
                if deleted.value:
                    set_deleted(conn, number, True)
            else:
                number = invoice_id
                update_header(conn, number, changed())
                if bool(deleted.value) != stored["is_deleted"]:
                    set_deleted(conn, number, bool(deleted.value))
        except ValidationError as e:
            problems.text = " ".join(e.problems)
            return None
        finally:
            conn.close()
        problems.text = ""
        return number

    def on_save() -> None:
        number = save_changes()
        if number is not None:
            ui.notify(f"Invoice {number} is saved.", type="positive")
            ui.navigate.to(f"/invoice/{number}")

    def on_deleted_change(e) -> None:
        if e.value and not stored["is_deleted"]:
            ui.notify(DELETE_WARNING, type="warning", close_button="OK", timeout=0)

    async def on_close() -> None:
        with ui.dialog() as dialog, ui.card():
            ui.label(f"Close invoice {invoice_id}? A closed invoice cannot be changed.")
            with ui.row():
                ui.button("Close invoice", on_click=lambda: dialog.submit(True)).props("no-caps").mark("confirm-close")
                ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("no-caps flat").mark("cancel-close")
        if not await dialog:
            return
        if save_changes() is None:
            return
        conn = connect()
        try:
            close(conn, invoice_id)
        except ValidationError as e:
            problems.text = " ".join(e.problems)
            return
        finally:
            conn.close()
        ui.notify(f"Invoice {invoice_id} is closed.", type="positive")
        ui.navigate.to(f"/invoice/{invoice_id}")

    async def on_reopen() -> None:
        with ui.dialog() as dialog, ui.card():
            ui.label(f"Reopen invoice {invoice_id}? Its header and lines can then be changed again.")
            with ui.row():
                ui.button("Reopen invoice", on_click=lambda: dialog.submit(True)).props("no-caps").mark("confirm-reopen")
                ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("no-caps flat").mark("cancel-reopen")
        answer = await dialog
        dialog.delete()
        if not answer:
            return
        conn = connect()
        try:
            reopen(conn, invoice_id)
        except ValidationError as e:
            problems.text = " ".join(e.problems)
            return
        finally:
            conn.close()
        ui.notify(f"Invoice {invoice_id} is open again.", type="positive")
        ui.navigate.to(f"/invoice/{invoice_id}")

    reopen_button.on_click(on_reopen)
    customer.on_value_change(lambda _: show_customer())
    deleted.on_value_change(on_deleted_change)
    save.on_click(on_save)
    close_button.on_click(on_close)
    lines.on_click(lambda: ui.navigate.to(f"/invoice/{invoice_id}/lines"))
    show_customer()

