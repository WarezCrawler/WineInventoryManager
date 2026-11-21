"""Mass registration of stock changes (design doc §6.2.1, replaces the Access button "Import vinlager
tilgange/afgange", which opened an empty grid for pasting rows).

The user pastes rows, usually from Excel: warehouse id, wine (id or code), quantity, comment. This module
reads and checks the text; stock.add_movements() writes the rows, all or nothing. No UI code here."""
import sqlite3

from winedb.masterdata import resolve_item

COLUMNS = ("warehouse", "wine", "quantity", "comment")


def _split(line: str) -> list[str]:
    """Excel pastes columns separated by tabs. A line without tabs may use semicolons."""
    cells = line.split("\t") if "\t" in line else line.split(";")
    return [c.strip() for c in cells]


def _is_whole(text: str) -> bool:
    return text.lstrip("+-").isdigit()


def parse(text: str) -> list[tuple[int, list[str]]]:
    """Split pasted text into (line number, cells). Empty lines are skipped. A first line whose warehouse
    and quantity are not numbers is a heading line and is skipped too."""
    rows = [(n, _split(line)) for n, line in enumerate((text or "").splitlines(), start=1) if line.strip()]
    if rows:
        cells = rows[0][1] + ["", "", ""]
        if not _is_whole(cells[0]) and not _is_whole(cells[2]):
            rows = rows[1:]
    return rows


def check(conn: sqlite3.Connection, text: str) -> tuple[list[dict], list[dict], list[str]]:
    """Read and check pasted rows. Return (rows to save, preview rows, problems).

    The rows to save are dicts for stock.add_movements(). The preview rows show what each line means.
    Each problem names its line number in the pasted text. Nothing is written."""
    to_save, preview, problems = [], [], []
    warehouses = {r[0]: r[1] for r in conn.execute("SELECT warehouse_id, warehouse_name FROM warehouses")}
    for line, cells in parse(text):
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
        })
        if not found:
            to_save.append({"warehouse_id": warehouse_id, "item_id": item["item_id"], "quantity": quantity,
                            "comment": comment})
    if not preview:
        problems.append("Paste at least one row.")
    return to_save, preview, problems
