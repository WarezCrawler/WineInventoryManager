"""Invoice data functions. The UI calls these functions and never queries the invoice tables itself."""
import sqlite3


def open_invoices(conn: sqlite3.Connection) -> list[dict]:
    """Return the open invoices for the main menu, newest first (design doc §6.1).

    An invoice is open when `is_closed` is not 1. Each row has `invoice_id`, `customer_id`,
    `customer_name` and `is_deleted`.

    The join to the customers is a left join (decision 2 in §10), so an invoice without a valid
    customer is in the list too; its `customer_name` is None. Access used an inner join and hid these
    invoices. Soft-deleted invoices are in the list, with `is_deleted = 1`, so that the user can find
    them and remove the flag.
    """
    rows = conn.execute(
        "SELECT h.invoice_id, h.customer_id, c.customer_name, COALESCE(h.is_deleted, 0) AS is_deleted"
        " FROM invoice_header AS h LEFT JOIN customers AS c ON c.customer_id = h.customer_id"
        " WHERE COALESCE(h.is_closed, 0) <> 1"
        " ORDER BY h.invoice_id DESC"
    )
    return [dict(r) for r in rows]
