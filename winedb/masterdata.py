"""Read functions for master data (wines and warehouses). The UI uses these and never queries the
tables itself."""
import sqlite3

ITEM_COLUMNS = ("item_id", "item_code", "name", "vintage", "producer", "country", "bottle_size", "item_type",
                "is_discontinued")


def list_items(conn: sqlite3.Connection) -> list[dict]:
    """Return all wines, sorted by code. The stock change screen offers all of them, as in Access."""
    rows = conn.execute(f"SELECT {', '.join(ITEM_COLUMNS)} FROM items ORDER BY item_code, item_id")
    return [dict(r) for r in rows]


def get_item(conn: sqlite3.Connection, item_id: int) -> dict | None:
    """Return one wine, or None if no wine has this id."""
    row = conn.execute(f"SELECT {', '.join(ITEM_COLUMNS)} FROM items WHERE item_id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def list_warehouses(conn: sqlite3.Connection) -> list[dict]:
    """Return all warehouses, sorted by id."""
    return [dict(r) for r in conn.execute("SELECT warehouse_id, warehouse_name FROM warehouses ORDER BY warehouse_id")]


def find_item_by_code(conn: sqlite3.Connection, code: str) -> dict | None:
    """Return the wine with this code (`item_code`, Access `Vin_UID`), or None. Upper and lower case are the
    same, as in Access. This is the one function that finds a wine from a typed code (design doc §9.1)."""
    row = conn.execute(f"SELECT {', '.join(ITEM_COLUMNS)} FROM items WHERE item_code = ? COLLATE NOCASE",
                       ((code or "").strip(),)).fetchone()
    return dict(row) if row else None


def resolve_item(conn: sqlite3.Connection, key: str) -> tuple[dict | None, str | None]:
    """Find a wine from a typed id or code. Return (wine, None), or (None, problem).

    A whole number that is a wine id gives that wine, as in Access. Any other text is looked up as a code.
    If a number is the id of one wine and the code of another wine, the key is ambiguous and refused."""
    key = (key or "").strip()
    if not key:
        return None, "Enter a wine id or code."
    by_code = find_item_by_code(conn, key)
    by_id = get_item(conn, int(key)) if key.isdigit() else None
    if by_id and by_code and by_id["item_id"] != by_code["item_id"]:
        return None, (f"'{key}' is the id of wine {by_id['item_code']} and the code of another wine "
                      f"(id {by_code['item_id']}). Use the code.")
    item = by_id or by_code
    return (item, None) if item else (None, f"No wine has the id or code '{key}'.")
