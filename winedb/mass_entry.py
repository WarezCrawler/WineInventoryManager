"""Mass registration of stock changes (design doc §6.2.1, replaces the Access button "Import vinlager
tilgange/afgange", which opened an empty grid for pasting rows).

The user types or pastes rows into a grid, usually from Excel: warehouse id, wine (id or code), quantity,
comment. This module splits pasted text and checks the rows; stock.add_movements() writes them, all or
nothing. No UI code here."""
import sqlite3

from winedb.masterdata import resolve_item

COLUMNS = ("warehouse", "wine", "quantity", "comment")


def _split(line: str) -> list[str]:
    """Excel pastes columns separated by tabs. A line without tabs may use semicolons."""
    cells = line.split("\t") if "\t" in line else line.split(";")
    return [c.strip() for c in cells]


def _is_whole(text: str) -> bool:
    return text.lstrip("+-").isdigit()


def parse(text: str, skip_heading: bool = True) -> list[tuple[int, list[str]]]:
    """Split pasted text into (line number, cells). Empty lines are skipped. With `skip_heading`, a first
    line whose warehouse and quantity are not numbers is a heading line and is skipped too (use it only
    when the text starts with the warehouse column)."""
    rows = [(n, _split(line)) for n, line in enumerate((text or "").splitlines(), start=1) if line.strip()]
    if rows and skip_heading:
        cells = rows[0][1] + ["", "", ""]
        if not _is_whole(cells[0]) and not _is_whole(cells[2]):
            rows = rows[1:]
    return rows


def check(conn: sqlite3.Connection, text: str) -> tuple[list[dict], list[dict], list[str]]:
    """Read and check pasted text. See check_rows()."""
    return check_rows(conn, parse(text))


def check_rows(conn: sqlite3.Connection, rows: list[tuple[int, list[str]]]) -> tuple[list[dict], list[dict], list[str]]:
    """Check rows of (line number, cells). Return (rows to save, preview rows, problems).

    The rows to save are dicts for stock.add_movements(). Each preview row shows what its line means and
    has `problems`, a list of sentences (empty if the row is correct). The returned problems name their
    line number. Nothing is written."""
    to_save, preview, problems = [], [], []
    warehouses = {r[0]: r[1] for r in conn.execute("SELECT warehouse_id, warehouse_name FROM warehouses")}
    for line, cells in rows:
        cells = [("" if c is None else str(c)).strip() for c in cells]
        found = []
        cells = (cells + ["", "", "", ""])
        if len([c for c in cells[4:] if c]) > 0:
            found.append("too many columns (expected: warehouse, wine, quantity, comment).")
        warehouse_text, wine_text, quantity_text, comment = cells[:4]
        warehouse_id = int(warehouse_text) if warehouse_text.isdigit() else None
        if warehouse_id not in warehouses:
            found.append(f"no warehouse has the id '{warehouse_text}'.")
        item, problem = resolve_item(conn, wine_text)
        if problem:
            found.append(problem[0].lower() + problem[1:])
        quantity = int(quantity_text) if _is_whole(quantity_text) else None
        if quantity in (None, 0):
            found.append(f"the quantity '{quantity_text}' is not a whole number other than 0.")
        problems += [f"Line {line}: {p}" for p in found]
        preview.append({
            "line": line,
            "warehouse": warehouses.get(warehouse_id, warehouse_text),
            "wine": f"{item['item_code']} – {item['name']} {item['vintage']}" if item else wine_text,
            "quantity": quantity if quantity is not None else quantity_text,
            "comment": comment,
            "status": "Problem" if found else "OK",
            "problems": [p[0].upper() + p[1:] for p in found],
        })
        if not found:
            to_save.append({"warehouse_id": warehouse_id, "item_id": item["item_id"], "quantity": quantity,
                            "comment": comment})
    if not preview:
        problems.append("Paste at least one row.")
    return to_save, preview, problems


def blank_row(line: int) -> dict:
    """One empty grid row. `line` is the row number the user sees (1 = the first row)."""
    return {"line": line, **{c: "" for c in COLUMNS}}


def is_blank(row: dict) -> bool:
    return not any(str(row.get(c) or "").strip() for c in COLUMNS)


def paste_into(rows: list[dict], text: str, start_row: int, start_column: str) -> int:
    """Put pasted text (tabs between columns, one row per line, as Excel copies it) into the grid rows,
    starting at row index `start_row` and column `start_column`. The grid grows when the text needs more
    rows. A heading line is skipped only when the paste starts in the warehouse column.

    Changes `rows` in place and returns the number of cells that did not fit (columns after the comment)."""
    start = COLUMNS.index(start_column) if start_column in COLUMNS else 0
    pasted = [cells for _, cells in parse(text, skip_heading=start == 0)]
    start_row = max(0, min(start_row, len(rows)))
    ignored = 0
    for i, cells in enumerate(pasted):
        r = start_row + i
        while r >= len(rows):
            rows.append(blank_row(len(rows) + 1))
        for j, value in enumerate(cells):
            if start + j < len(COLUMNS):
                rows[r][COLUMNS[start + j]] = value
            elif value:
                ignored += 1
    return ignored


def grid_rows_to_check(rows: list[dict]) -> list[tuple[int, list[str]]]:
    """The rows that are not blank, as (line, cells) for check_rows(). Blank rows are not checked."""
    return [(row["line"], [str(row.get(c) or "") for c in COLUMNS]) for row in rows if not is_blank(row)]


def with_new_row(rows: list[dict]) -> list[dict]:
    """End the grid with exactly one empty row, the new row, as in an Access datasheet. Empty rows at the
    end are removed first, so the grid is as long as its content plus one. Changes `rows` in place."""
    while rows and is_blank(rows[-1]):
        rows.pop()
    rows.append(blank_row(len(rows) + 1))
    return rows
