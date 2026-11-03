"""Read-only access to the content of the tables, for the table browser."""
import sqlite3


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [r[0] for r in rows]


def table_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    return [(n, conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]) for n in table_names(conn)]


def table_view(conn: sqlite3.Connection, name: str, limit: int = 5000) -> dict:
    """Columns, rows (as dicts), total row count and primary key column of one table.
    The name must be an existing table: it is checked before it is used in SQL."""
    if name not in table_names(conn):
        raise KeyError(name)
    info = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
    columns = [r["name"] for r in info]
    key = next((r["name"] for r in info if r["pk"] == 1), columns[0])
    total = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    rows = [dict(r) for r in conn.execute(f'SELECT * FROM "{name}" ORDER BY "{key}" LIMIT ?', (limit,))]
    return {"columns": columns, "rows": rows, "total": total, "key": key}
