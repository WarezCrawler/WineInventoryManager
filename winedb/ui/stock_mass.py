"""Mass stock registration (design doc §6.2.1, replaces the Access button "Import vinlager tilgange/afgange",
which opened an editable grid). The user types into the grid or pastes a block of cells from Excel."""
import json

from nicegui import ui

from winedb.db import connect
from winedb.mass_entry import COLUMNS, blank_row, check_rows, grid_rows_to_check, is_blank, paste_into, with_new_row
from winedb.masterdata import list_warehouses
from winedb.stock import add_movements, wines_for_stock_change
from winedb.ui.labels import label
from winedb.validation import ValidationError

HELP = ("Click a cell and paste from Excel (Ctrl+V): the copied cells fill the grid from that cell down and to the "
        "right. As in Access, the last row is always a new, empty row: the grid grows by the rows you paste or type. "
        "Double-click a warehouse cell for a list. In a wine cell, type part of the code or the name for suggestions. "
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


def _pick_list(values: list[str]) -> str:
    """The cell editor for a column with a list: double-click, Enter or F2 open a dropdown list (AG Grid's
    free select editor); typing a character opens the normal text editor, so a code or id can be typed."""
    return ("(params) => (params.eventKey && params.eventKey.length === 1)"
            " ? {component: 'agTextCellEditor'}"
            f" : {{component: 'agSelectCellEditor', params: {{values: {json.dumps(values)}}}}}")


def _searchable_wine_editor(wines: list[dict]) -> str:
    """A cell editor (a JavaScript class) for the wine cell: a text box with suggestions while the user types.
    The suggestions are an HTML datalist, which the browser filters on any part of the code or the name.
    AG Grid's own searchable list is an Enterprise feature. The value is the typed or picked code."""
    choices = json.dumps([[w["item_code"], f"{w['item_code']} – {w['name']} {w['vintage']}"] for w in wines])
    return """class {
    init(params) {
        const listId = 'wine-choices';
        if (!document.getElementById(listId)) {
            const list = document.createElement('datalist');
            list.id = listId;
            for (const [value, text] of %s) {
                const option = document.createElement('option');
                option.value = value;
                option.label = text;
                list.appendChild(option);
            }
            document.body.appendChild(list);
        }
        this.input = document.createElement('input');
        this.input.setAttribute('list', listId);
        this.input.setAttribute('placeholder', 'Type part of the code or the name');
        this.input.className = 'ag-input-field-input ag-text-field-input';
        this.input.style.width = '100%%';
        this.input.style.height = '100%%';
        const typed = params.eventKey && params.eventKey.length === 1;
        this.input.value = typed ? params.eventKey : (params.value == null ? '' : String(params.value));
    }
    getGui() { return this.input; }
    afterGuiAttached() {
        this.input.focus();
        const end = this.input.value.length;
        this.input.setSelectionRange(end, end);
    }
    getValue() { return this.input.value.trim(); }
}""" % choices


def column_defs(warehouses: list[dict], wines: list[dict]) -> list[dict]:
    """The grid columns. Warehouse and wine have a dropdown list, and their cells show the name next to the
    id or code (AG Grid `refData`); the cell value itself stays the id or code that is checked and saved.
    The wine list is the list of the stock change screen (stock.wines_for_stock_change())."""
    warehouse_text = {str(w["warehouse_id"]): f"{w['warehouse_id']} – {w['warehouse_name'] or ''}" for w in warehouses}
    wine_text = {str(w["item_id"]): f"{w['item_id']} = {w['item_code']} – {w['name']} {w['vintage']}" for w in wines}
    wine_text.update({w["item_code"]: f"{w['item_code']} – {w['name']} {w['vintage']}" for w in wines})
    tip = "Double-click (or Enter) for a list. Type to enter a value."
    return [
        _column("line", label("line"), False, width=70),
        _column("warehouse", label("warehouse"), True, width=170, refData=warehouse_text, headerTooltip=tip,
                **{":cellEditorSelector": _pick_list(list(warehouse_text))}),
        _column("wine", "Wine (id or code)", True, flex=2, minWidth=240, refData=wine_text,
                headerTooltip="Type part of the code or the name for suggestions.",
                **{":cellEditor": _searchable_wine_editor(wines)}),
        _column("quantity", label("quantity"), True, width=110),
        _column("comment", label("comment"), True, flex=2, minWidth=160),
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

    conn = connect()
    try:
        columns = column_defs(list_warehouses(conn), wines_for_stock_change(conn))
    finally:
        conn.close()
    state = {"rows": with_new_row([]), "checked": False}
    grid = ui.aggrid({
        "columnDefs": columns,
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
        row.pop("status", None)

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
