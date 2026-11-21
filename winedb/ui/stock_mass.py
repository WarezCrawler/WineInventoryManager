"""Mass stock registration (design doc §6.2.1, replaces the Access button "Import vinlager tilgange/afgange",
which opened an editable grid). The user types into the grid or pastes a block of cells from Excel."""
from nicegui import ui

from winedb.db import connect
from winedb.mass_entry import COLUMNS, blank_row, check_rows, grid_rows_to_check, is_blank, paste_into, with_new_row
from winedb.stock import add_movements
from winedb.ui.labels import label
from winedb.validation import ValidationError

HELP = ("Click a cell and paste from Excel (Ctrl+V): the copied cells fill the grid from that cell down and to the "
        "right. As in Access, the last row is always a new, empty row: the grid grows by the rows you paste or type. "
        "Columns: warehouse id, wine (id or code), quantity (negative to remove stock), comment. Empty rows are "
        "ignored. All rows get today's date and time.")

# The grid gets the paste from the browser: AG Grid's own paste of many cells is an Enterprise feature.
# Text with a tab or a line break (anything copied from Excel) is sent to the server with the row and the
# column of the cell where the user pasted; other text is left to the browser (paste into an open cell).
PASTE_JS = """(e) => {
    const text = e.clipboardData ? e.clipboardData.getData('text/plain') : '';
    if (!/[\\t\\n]/.test(text)) return;
    e.preventDefault();
    e.stopPropagation();
    const row = e.target.closest('[row-index]');
    const cell = e.target.closest('[col-id]');
    emit({text: text, row: row ? Number(row.getAttribute('row-index')) : 0, col: cell ? cell.getAttribute('col-id') : ''});
}"""


def _column(field: str, header: str, editable: bool, **extra) -> dict:
    return {"field": field, "headerName": header, "editable": editable, "resizable": True,
            "cellClass": "" if editable else "bg-gray-100", **extra}


COLUMN_DEFS = [
    _column("line", label("line"), False, width=70),
    _column("warehouse", "Warehouse id", True, width=120),
    _column("wine", "Wine (id or code)", True, width=170),
    _column("quantity", label("quantity"), True, width=110),
    _column("comment", label("comment"), True, flex=2, minWidth=160),
    _column("warehouse_name", label("warehouse"), False, width=140),
    _column("wine_name", label("wine"), False, flex=2, minWidth=180),
    _column("status", label("status"), False, flex=3, minWidth=200),
]


@ui.page("/stock-mass")
def stock_mass_page():
    with ui.header().classes("items-center"):
        ui.label("Mass stock registration").classes("text-xl font-bold")
        ui.space()
        ui.link("Stock change", "/stock-change").classes("text-white")
        ui.link("Main menu", "/").classes("text-white")

    ui.label(HELP).classes("text-sm opacity-80")
    with ui.row():
        check_button = ui.button("Check").props("no-caps")
        save_button = ui.button("Save all").props("no-caps")
        clear_button = ui.button("Clear").props("no-caps flat")
        ui.button("Cancel", on_click=lambda: ui.navigate.to("/")).props("no-caps flat")
    summary = ui.label("").classes("font-bold")

    state = {"rows": with_new_row([]), "checked": False}
    grid = ui.aggrid({
        "columnDefs": COLUMN_DEFS,
        "rowData": state["rows"],
        "stopEditingWhenCellsLoseFocus": True,
        "enterNavigatesVertically": True,
        "enterNavigatesVerticallyAfterEdit": True,
        "singleClickEdit": False,
    }).classes("w-full").style("height: 60vh")
    save_button.disable()

    def show() -> None:
        grid.options["rowData"] = state["rows"]
        grid.update()

    def not_checked(message: str = "") -> None:
        state["checked"] = False
        save_button.disable()
        summary.text = message

    def clear_results(row: dict) -> None:
        for key in ("warehouse_name", "wine_name", "status"):
            row.pop(key, None)

    def on_paste(e) -> None:
        args = e.args or {}
        ignored = paste_into(state["rows"], args.get("text", ""), int(args.get("row") or 0), args.get("col") or "")
        with_new_row(state["rows"])
        for row in state["rows"]:
            clear_results(row)
        show()
        not_checked("The rows changed. Check them before you save.")
        if ignored:
            ui.notify(f"{ignored} pasted cell(s) after the comment column were left out.", type="warning")

    def on_edit(e) -> None:
        args = e.args or {}
        field, line = args.get("colId"), (args.get("data") or {}).get("line")
        if field not in COLUMNS or not line:
            return
        row = state["rows"][line - 1]
        row[field] = "" if args.get("newValue") is None else str(args.get("newValue"))
        clear_results(row)
        if line == len(state["rows"]) and not is_blank(row):
            # The user typed into the new row: add the next new row without redrawing the grid.
            new = blank_row(line + 1)
            state["rows"].append(new)
            grid.options["rowData"] = state["rows"]
            grid.run_grid_method("applyTransaction", {"add": [new]})
        not_checked("The rows changed. Check them before you save.")

    def run_check() -> bool:
        conn = connect()
        try:
            to_save, preview, problems = check_rows(conn, grid_rows_to_check(state["rows"]))
        finally:
            conn.close()
        by_line = {p["line"]: p for p in preview}
        for row in state["rows"]:
            clear_results(row)
            p = by_line.get(row["line"])
            if p:
                row["warehouse_name"] = p["warehouse"] if not p["problems"] else ""
                row["wine_name"] = p["wine"] if " – " in str(p["wine"]) else ""
                row["status"] = "OK" if not p["problems"] else " ".join(p["problems"])
        show()
        if not preview:
            not_checked("The grid is empty. Paste or type at least one row.")
            return False
        if problems:
            not_checked(f"{len([p for p in preview if p['problems']])} row(s) have problems: see the column "
                        f"{label('status')}. Correct them and check again. Nothing is saved.")
            return False
        state["checked"] = True
        save_button.enable()
        summary.text = f"{len(to_save)} row(s) are correct. Click Save all to save them."
        return True

    def save_all() -> None:
        conn = connect()
        try:
            to_save, _, problems = check_rows(conn, grid_rows_to_check(state["rows"]))   # the data can have changed
            if problems:
                raise ValidationError(problems)
            add_movements(conn, to_save)
        except ValidationError:
            conn.close()
            run_check()
            summary.text = "Nothing is saved. " + summary.text
            return
        conn.close()
        ui.notify(f"{len(to_save)} stock change(s) are saved.", type="positive")
        state["rows"] = with_new_row([])
        show()
        not_checked(f"Saved {len(to_save)} stock change(s).")

    def clear_all() -> None:
        state["rows"] = with_new_row([])
        show()
        not_checked("")

    grid.on("paste", on_paste, js_handler=PASTE_JS)
    grid.on("cellValueChanged", on_edit)
    check_button.on_click(run_check)
    save_button.on_click(save_all)
    clear_button.on_click(clear_all)
