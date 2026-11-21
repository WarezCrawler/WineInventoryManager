"""Stock data functions. The UI calls these functions and never queries the stock tables itself."""
import sqlite3


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
