"""Mass stock registration (design doc §6.2.1, replaces the Access button "Import vinlager tilgange/afgange")."""
from nicegui import ui

from winedb.db import connect
from winedb.mass_entry import check
from winedb.stock import add_movements
from winedb.ui.labels import label
from winedb.validation import ValidationError

PREVIEW_COLUMNS = ("line", "warehouse", "wine", "quantity", "comment", "status")
HELP = ("Paste rows from Excel, one stock change per row, with the columns: warehouse id, wine (id or code), "
        "quantity (negative to remove stock), comment. A heading row is skipped. All rows get today's date and time.")


@ui.page("/stock-mass")
def stock_mass_page():
    with ui.header().classes("items-center"):
        ui.label("Mass stock registration").classes("text-xl font-bold")
        ui.space()
        ui.link("Stock change", "/stock-change").classes("text-white")
        ui.link("Main menu", "/").classes("text-white")

    ui.label(HELP).classes("text-sm opacity-80")
    text = ui.textarea("Rows").props("outlined input-class=font-mono").classes("w-full")
    with ui.row():
        check_button = ui.button("Check").props("no-caps")
        save_button = ui.button("Save all").props("no-caps")
        ui.button("Cancel", on_click=lambda: ui.navigate.to("/")).props("no-caps flat")
    summary = ui.label("").classes("font-bold")
    problems = ui.column().classes("gap-0 text-negative")
    columns = [{"name": c, "label": label(c), "field": c, "align": "left"} for c in PREVIEW_COLUMNS]
    preview = ui.table(columns=columns, rows=[], row_key="line").props("dense").classes("w-full")

    checked = {"text": None}   # the text of the last check without problems; Save works only for that text
    save_button.disable()

    def show_problems(lines: list[str]) -> None:
        problems.clear()
        with problems:
            for line in lines:
                ui.label(line)

    def run_check() -> None:
        conn = connect()
        try:
            rows, shown, found = check(conn, text.value)
        finally:
            conn.close()
        preview.rows = shown
        show_problems(found)
        if found:
            checked["text"] = None
            save_button.disable()
            summary.text = f"{len(found)} problem(s). Correct the rows and check again. Nothing is saved."
        else:
            checked["text"] = text.value
            save_button.enable()
            summary.text = f"{len(rows)} row(s) are correct. Click Save all to save them."

    def text_changed() -> None:
        if checked["text"] is not None and text.value != checked["text"]:
            checked["text"] = None
            save_button.disable()
            summary.text = "The rows changed. Check them again."

    def save_all() -> None:
        conn = connect()
        try:
            rows, shown, found = check(conn, text.value)   # check again: the data can have changed
            if not found:
                add_movements(conn, rows)
        except ValidationError as e:
            found = e.problems
        finally:
            conn.close()
        if found:
            preview.rows = shown
            show_problems(found)
            save_button.disable()
            summary.text = "Nothing is saved. Correct the rows and check again."
            return
        ui.notify(f"{len(rows)} stock change(s) are saved.", type="positive")
        text.value, preview.rows, checked["text"] = "", [], None
        show_problems([])
        summary.text = f"Saved {len(rows)} stock change(s)."
        save_button.disable()

    check_button.on_click(run_check)
    save_button.on_click(save_all)
    text.on_value_change(lambda _: text_changed())
