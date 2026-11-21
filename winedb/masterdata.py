"""Read functions for master data (wines and warehouses). The UI uses these and never queries the
tables itself."""
import sqlite3

ITEM_COLUMNS = ("item_id", "item_code", "name", "vintage", "producer", "country", "bottle_size", "item_type")


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
