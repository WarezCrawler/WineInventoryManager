"""Invoice preview and PDF (design doc §6.5, decision 12; replaces the Access report rFaktura and its
"Create PDF" button).

The preview shows the same document as the PDF (invoice_print.invoice_document), so the amounts are always
the same. The preview is in English, like the rest of the program; the PDF keeps the Danish labels of the
Access report (owner decision 17)."""
import os
import sys

from nicegui import ui

from winedb.config import app_dir
from winedb.db import connect
from winedb.invoice_print import invoice_document, padded, pdf_path, short_date, whole, write_pdf
from winedb.settings import load_settings, settings_path
from winedb.ui.labels import label
from winedb.validation import ValidationError


def money(value) -> str:
    return f"{(value or 0):,.2f}"


def open_file(path) -> None:
    """Open the PDF in the default viewer, as Access did after it saved the PDF."""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606  (a file the program has just written)


def _document(invoice_id: int) -> tuple[dict | None, dict, str]:
    """(document, settings, problem). The settings are read each time, so a changed settings.json counts."""
    try:
        settings = load_settings()
    except ValueError as e:
        return None, {}, str(e)
    conn = connect()
    try:
        return invoice_document(conn, invoice_id, settings), settings, ""
    except ValidationError as e:
        return None, settings, " ".join(e.problems)
    finally:
        conn.close()


def _rows(doc: dict) -> list[dict]:
    rows = []
    for group in doc["groups"]:
        for n, line in enumerate(group["lines"]):
            rows.append({"key": line["sales_line_id"], "producer": group["house"] if n == 0 else "",
                         "quantity": whole(line["quantity"]), "wine": line["text"], "vintage": whole(line["vintage"]),
                         "sales_price": "" if line["unit_price"] is None else money(line["unit_price"]),
                         "line_total": money(line["line_total"])})
    return rows


@ui.page("/invoice/{invoice_id}/preview")
def invoice_preview_page(invoice_id: int):
    doc, _, problem = _document(invoice_id)

    with ui.header().classes("items-center"):
        ui.label(f"Invoice {invoice_id} – preview").classes("text-xl font-bold")
        ui.space()
        ui.link("Invoice lines", f"/invoice/{invoice_id}/lines").classes("text-white")
        ui.link("Main menu", "/").classes("text-white")
    if doc is None:
        ui.label(problem).classes("text-negative")
        return

    if doc["is_deleted"]:
        ui.label("This invoice is deleted.").classes("text-negative font-bold")
    if doc["hide_subtotals"]:
        ui.label("Hide subtotals is on: the PDF shows no unit prices and no line totals, only the invoice totals.") \
            .classes("text-orange")

    with ui.row():                           # layout (owner): the buttons above the document
        create_button = ui.button("Create PDF").props("no-caps")
        ui.button("Invoice lines", on_click=lambda: ui.navigate.to(f"/invoice/{invoice_id}/lines")).props("no-caps flat")
    status = ui.label("")

    with ui.card().classes("w-full max-w-5xl"):
        with ui.row().classes("w-full justify-between"):
            with ui.column().classes("gap-0"):
                ui.label(f"{label('invoice_id')} {padded(doc['invoice_id'], 5)}").classes("text-lg font-bold")
                ui.label(f"{label('invoice_date')}: {short_date(doc['invoice_date']) or '(none)'}")
            with ui.column().classes("gap-0 items-end"):
                ui.label(f"{label('customer_id')} {padded(doc['customer_id'], 4)}")
                for text in (doc["customer_name"], f"{doc['city'] or ''} {whole(doc['postal_code'])}".strip(),
                             doc["address"]):
                    if text:
                        ui.label(text)

        names = ["producer", "quantity", "wine", "vintage"] + ([] if doc["hide_subtotals"] else ["sales_price", "line_total"])
        headings = {"line_total": "Line total incl. VAT", "sales_price": "Unit price incl. VAT"}
        columns = [{"name": c, "label": headings.get(c, label(c)), "field": c,
                    "align": "right" if c in ("quantity", "vintage", "sales_price", "line_total") else "left"}
                   for c in names]
        rows = _rows(doc)
        ui.table(columns=columns, rows=rows, row_key="key", pagination=0).classes("w-full").props("dense flat hide-bottom")
        if not rows:
            ui.label("This invoice has no lines.").classes("opacity-70")

        with ui.row().classes("w-full justify-between items-start"):
            with ui.column().classes("gap-1"):
                ui.label(f"Total quantity: {whole(doc['total_quantity'])}")
                if doc["comment"]:
                    ui.label(doc["comment"]).classes("whitespace-pre-wrap max-w-md")
            with ui.grid(columns=2).classes("gap-x-8 gap-y-0"):
                if doc["adjustment"]:
                    ui.label("Adjustment (discounts)")
                    ui.label(money(doc["adjustment"])).classes("text-right")
                ui.label("Total incl. VAT").classes("font-bold")
                ui.label(money(doc["total_incl_vat"])).classes("text-right font-bold")
                ui.label("Of which VAT")
                ui.label(money(doc["vat"])).classes("text-right")
                ui.label("Total excl. VAT")
                ui.label(money(doc["total_ex_vat"])).classes("text-right")

        ui.separator()
        for text in doc["texts"]:
            ui.label(text).classes("w-full text-center text-sm opacity-70")

    async def create_pdf() -> None:
        current, current_settings, why = _document(invoice_id)   # the data as it is now
        if current is None:
            status.text = why
            return
        try:
            target = pdf_path(current, current_settings["invoice_pdf_folder"])
        except ValidationError as e:
            status.text = " ".join(e.problems) + f" (settings file: {settings_path()})"
            return
        if target.exists():
            with ui.dialog() as dialog, ui.card():
                ui.label(f"A PDF for invoice {invoice_id} already exists: {target}")
                ui.label("Replace it?")
                with ui.row():
                    ui.button("Replace", on_click=lambda: dialog.submit(True)).props("no-caps").mark("confirm-replace")
                    ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("no-caps flat").mark("keep-pdf")
            replace = await dialog
            dialog.delete()
            if not replace:
                status.text = "The PDF is not replaced."
                return
        logo = app_dir() / "logo.png"
        try:
            write_pdf(current, target, logo if logo.exists() else None)
        except OSError as e:
            status.text = f"Could not save the PDF: {e}. If the PDF is open in a viewer, close it and try again."
            return
        status.text = f"The PDF is saved: {target}"
        open_file(target)

    create_button.on_click(create_pdf)
