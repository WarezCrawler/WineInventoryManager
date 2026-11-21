"""Stock data functions. The UI calls these functions and never queries the stock tables itself."""
import sqlite3

from winedb.db import transaction
from winedb.validation import ValidationError, is_timestamp, now_text


def on_hand(conn: sqlite3.Connection, item_id: int, warehouse_id: int) -> int:
    """Return the on-hand stock of one wine in one warehouse (design doc §5.3).

    On-hand stock = the sum of all stock movements − the sum of all invoice line quantities, for
    this wine and warehouse. This function is the only place that knows the formula.

    Lines of soft-deleted invoices (`is_deleted = 1`) are left out. Access counted them
    (`TotalVinQ` uses `uVinlager`); the difference is deliberate, because calculations must leave
    out flagged invoices. Lines whose invoice row does not exist still count, as in Access.
    A NULL quantity counts as 0. The result can be negative: the app shows that and never blocks it.
    """
    moved = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM stock_transactions WHERE item_id = ? AND warehouse_id = ?",
        (item_id, warehouse_id),
    ).fetchone()[0]
    sold = conn.execute(
        "SELECT COALESCE(SUM(l.quantity), 0) FROM invoice_lines AS l"
        " LEFT JOIN invoice_header AS h ON h.invoice_id = l.invoice_id"
        " WHERE l.item_id = ? AND l.warehouse_id = ? AND COALESCE(h.is_deleted, 0) = 0",
        (item_id, warehouse_id),
    ).fetchone()[0]
    return moved - sold


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
    if problems:
        raise ValidationError(problems)

    with transaction(conn):
        cursor = conn.execute(
            "INSERT INTO stock_transactions (created_at, item_id, quantity, comment, warehouse_id) VALUES (?, ?, ?, ?, ?)",
            (created_at, item_id, quantity, comment, warehouse_id),
        )
    return cursor.lastrowid


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
