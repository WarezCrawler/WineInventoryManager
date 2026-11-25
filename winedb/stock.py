"""Stock data functions. The UI calls these functions and never queries the stock tables itself."""
import sqlite3

from winedb.db import transaction
from winedb.masterdata import list_items
from winedb.validation import ValidationError, is_timestamp, now_text


# The on-hand formula (design doc §5.3), in one place: stock movements count with their sign, invoice
# lines count negative. Lines of soft-deleted invoices and cancelled lines (quantity 0) are left out.
_ON_HAND = """
    SELECT item_id, warehouse_id, SUM(quantity) AS on_hand FROM (
        SELECT item_id, warehouse_id, COALESCE(quantity, 0) AS quantity FROM stock_transactions
        UNION ALL
        SELECT l.item_id, l.warehouse_id, -COALESCE(l.quantity, 0) FROM invoice_lines AS l
            LEFT JOIN invoice_header AS h ON h.invoice_id = l.invoice_id
            WHERE COALESCE(h.is_deleted, 0) = 0 AND COALESCE(l.is_deleted, 0) = 0
    ) {where} GROUP BY item_id, warehouse_id"""


def on_hand_table(conn: sqlite3.Connection, item_id: int | None = None) -> dict[tuple[int, int], int]:
    """Return the on-hand stock of every (wine, warehouse) pair that has rows, or only of one wine.

    On-hand stock = the sum of all stock movements − the sum of all invoice line quantities. This
    function is the only place that knows the formula; on_hand() and on_hand_by_item() use it.

    Lines of soft-deleted invoices (`is_deleted = 1`) are left out. Access counted them
    (`TotalVinQ` uses `uVinlager`); the difference is deliberate, because calculations must leave
    out flagged invoices. Lines whose invoice row does not exist still count, as in Access.
    A NULL quantity counts as 0. The result can be negative: the app shows that and never blocks it.
    """
    where, params = ("WHERE item_id = ?", (item_id,)) if item_id is not None else ("", ())
    return {(r[0], r[1]): r[2] for r in conn.execute(_ON_HAND.format(where=where), params)}


def on_hand(conn: sqlite3.Connection, item_id: int, warehouse_id: int) -> int:
    """Return the on-hand stock of one wine in one warehouse (design doc §5.3); 0 if it has no rows."""
    return on_hand_table(conn, item_id).get((item_id, warehouse_id), 0)


def on_hand_by_item(conn: sqlite3.Connection) -> dict[int, int]:
    """Return the on-hand stock of each wine over all warehouses. Wines without rows are not in it."""
    totals: dict[int, int] = {}
    for (item_id, _), quantity in on_hand_table(conn).items():
        totals[item_id] = totals.get(item_id, 0) + quantity
    return totals


def wines_for_stock_change(conn: sqlite3.Connection) -> list[dict]:
    """Return the wines that the stock change screen offers (owner decision, 2026-11-21).

    All wines, as in Access, except discontinued wines whose stock over all warehouses is 0: they are
    hidden. A discontinued wine with stock (also negative stock) stays, so that it can be corrected.
    Active wines come first, then the discontinued ones; each group is sorted by code. Each wine has
    `on_hand_total`. Mass registration does not use this list: it accepts every wine by id or code."""
    totals = on_hand_by_item(conn)
    wines = [{**item, "on_hand_total": totals.get(item["item_id"], 0)} for item in list_items(conn)]
    shown = [w for w in wines if not (w["is_discontinued"] and w["on_hand_total"] == 0)]
    return sorted(shown, key=lambda w: (bool(w["is_discontinued"]), (w["item_code"] or "").casefold()))


def _check(conn: sqlite3.Connection, item_id, warehouse_id, quantity, comment, created_at):
    """Check one stock movement. Return (problems, cleaned values) without writing anything."""
    problems = []
    if item_id is None or not conn.execute("SELECT 1 FROM items WHERE item_id = ?", (item_id,)).fetchone():
        problems.append("Choose a wine.")
    if warehouse_id is None or not conn.execute(
            "SELECT 1 FROM warehouses WHERE warehouse_id = ?", (warehouse_id,)).fetchone():
        problems.append("Choose a warehouse.")
    if isinstance(quantity, float) and quantity.is_integer():
        quantity = int(quantity)
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity == 0:
        problems.append("Enter a whole number other than 0 as the quantity (negative to remove stock).")
    comment = (comment or "").strip() or None
    created_at = now_text() if created_at is None or created_at == "" else created_at
    if not is_timestamp(created_at):
        problems.append("Enter the date in the form YYYY-MM-DD HH:MM:SS.")
    return problems, (created_at, item_id, quantity, comment, warehouse_id)


_INSERT = "INSERT INTO stock_transactions (created_at, item_id, quantity, comment, warehouse_id) VALUES (?, ?, ?, ?, ?)"


def add_movement(conn: sqlite3.Connection, item_id, warehouse_id, quantity, comment=None, created_at=None) -> int:
    """Write one stock movement (design doc §5.5) and return its `stock_line_id`.

    `quantity` is signed: a positive value adds stock, a negative value removes it. `created_at` is the
    date of the change; it is now if not given. The fields are those of the Access form
    (fVinlager_Change); version 1 adds no columns.

    Raises ValidationError, with every problem found, if a rule is broken:
    - the wine and the warehouse must exist;
    - the quantity must be a whole number other than 0;
    - the date must have the form YYYY-MM-DD HH:MM:SS.
    Negative on-hand stock is allowed (design doc §10, decision 5).
    """
    problems, values = _check(conn, item_id, warehouse_id, quantity, comment, created_at)
    if problems:
        raise ValidationError(problems)
    with transaction(conn):
        cursor = conn.execute(_INSERT, values)
    return cursor.lastrowid


def add_movements(conn: sqlite3.Connection, rows: list[dict]) -> list[int]:
    """Write many stock movements at once (mass registration, design doc §6.2.1) and return their ids.

    Each row is a dict with `item_id`, `warehouse_id`, `quantity` and optionally `comment`. All rows get
    the same date: now, as in Access, where the table default `Now()` set it. The rules are those of
    add_movement(). All or nothing: if any row breaks a rule, nothing is written, and the
    ValidationError lists each problem with its row number (1 = the first row).
    """
    created_at = now_text()
    problems, values = [], []
    for n, row in enumerate(rows, start=1):
        found, cleaned = _check(conn, row.get("item_id"), row.get("warehouse_id"), row.get("quantity"),
                                row.get("comment"), created_at)
        problems += [f"Row {n}: {p}" for p in found]
        values.append(cleaned)
    if not rows:
        problems.append("There are no rows to save.")
    if problems:
        raise ValidationError(problems)
    with transaction(conn):
        return [conn.execute(_INSERT, v).lastrowid for v in values]


def recent_movements(conn: sqlite3.Connection, item_id: int, warehouse_id: int, limit: int = 20) -> list[dict]:
    """Return the latest stock movements of one wine in one warehouse, newest first. Rows without a date
    come last."""
    rows = conn.execute(
        "SELECT stock_line_id, created_at, quantity, comment FROM stock_transactions"
        " WHERE item_id = ? AND warehouse_id = ?"
        " ORDER BY created_at IS NULL, created_at DESC, stock_line_id DESC LIMIT ?",
        (item_id, warehouse_id, limit),
    )
    return [dict(r) for r in rows]
