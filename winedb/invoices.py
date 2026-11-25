"""Invoice data functions. The UI calls these functions and never queries the invoice tables itself."""
import sqlite3
from datetime import date

from winedb.db import transaction
from winedb.validation import ValidationError


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


# --- Invoice header (design doc §5.4, §6.3; step 7) ---


HEADER_FIELDS = ("customer_id", "warehouse_id", "invoice_date", "comment", "hide_subtotals")


class InvoiceClosedError(ValidationError):
    """The invoice is closed: it cannot be changed (reopening is a later function, design doc §9)."""


def date_text(value) -> str | None:
    """An invoice date as Access stored it: 'YYYY-MM-DD 00:00:00'. Accepts a date or 'YYYY-MM-DD'."""
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d 00:00:00")
    return date.fromisoformat(str(value).strip()[:10]).strftime("%Y-%m-%d 00:00:00")


def get_header(conn: sqlite3.Connection, invoice_id: int) -> dict | None:
    """Return the invoice header with the customer's name and address and the warehouse name (read-only, as
    the Access form showed them), or None if no invoice has this id."""
    row = conn.execute(
        "SELECT h.invoice_id, h.customer_id, h.is_closed, h.comment, h.warehouse_id, h.invoice_date,"
        " h.hide_subtotals, h.is_deleted, c.customer_name, c.address, c.postal_code, c.city, c.phone,"
        " w.warehouse_name"
        " FROM invoice_header AS h"
        " LEFT JOIN customers AS c ON c.customer_id = h.customer_id"
        " LEFT JOIN warehouses AS w ON w.warehouse_id = h.warehouse_id"
        " WHERE h.invoice_id = ?", (invoice_id,)).fetchone()
    return dict(row) if row else None


def _field_problems(conn: sqlite3.Connection, values: dict) -> tuple[list[str], dict]:
    """Check the given header fields only (validate on write). Return (problems, cleaned values)."""
    problems, clean = [], {}
    for field, value in values.items():
        if field == "customer_id":
            if value in (None, "", 0) or not conn.execute("SELECT 1 FROM customers WHERE customer_id = ?", (value,)).fetchone():
                problems.append("Choose a customer.")
            clean[field] = value
        elif field == "warehouse_id":
            if value in ("", None):
                clean[field] = None          # optional, as in Access
            elif not conn.execute("SELECT 1 FROM warehouses WHERE warehouse_id = ?", (value,)).fetchone():
                problems.append("Choose a warehouse from the list.")
            else:
                clean[field] = value
        elif field == "invoice_date":
            try:
                clean[field] = date_text(value)
            except ValueError:
                problems.append("Enter the invoice date in the form YYYY-MM-DD.")
        elif field == "comment":
            clean[field] = (value or "").strip() or None
        elif field == "hide_subtotals":
            clean[field] = 1 if value else 0
        else:
            raise ValueError(f"Unknown invoice header field: {field}")
    return problems, clean


def create_header(conn: sqlite3.Connection, customer_id, warehouse_id=None, invoice_date="today", comment=None,
                  hide_subtotals=False) -> int:
    """Create an open invoice and return its number (`invoice_id`, read from the insert, not with DMax).

    A new invoice must have a customer (design doc §6.3; Access allowed customer 0). The invoice date is
    today unless given (decision 3). The warehouse is optional, as in Access. The other columns get the
    Access defaults: not closed, not deleted."""
    values = {"customer_id": customer_id, "warehouse_id": warehouse_id,
              "invoice_date": date.today() if invoice_date == "today" else invoice_date,
              "comment": comment, "hide_subtotals": hide_subtotals}
    problems, clean = _field_problems(conn, values)
    if problems:
        raise ValidationError(problems)
    with transaction(conn):
        cursor = conn.execute(
            "INSERT INTO invoice_header (customer_id, is_closed, comment, warehouse_id, invoice_date, hide_subtotals, is_deleted)"
            " VALUES (?, 0, ?, ?, ?, ?, 0)",
            (clean["customer_id"], clean["comment"], clean["warehouse_id"], clean["invoice_date"], clean["hide_subtotals"]))
    return cursor.lastrowid


def _open_invoice(conn: sqlite3.Connection, invoice_id: int) -> dict:
    header = get_header(conn, invoice_id)
    if header is None:
        raise ValidationError([f"Invoice {invoice_id} does not exist."])
    if header["is_closed"] == 1:
        raise InvoiceClosedError([f"Invoice {invoice_id} is closed and cannot be changed."])
    return header


def update_header(conn: sqlite3.Connection, invoice_id: int, changes: dict) -> None:
    """Change fields of an open invoice header. Only the changed fields are checked, so an old invoice with
    customer 0 can still get, for example, a new comment. Fields: see HEADER_FIELDS."""
    _open_invoice(conn, invoice_id)
    problems, clean = _field_problems(conn, changes)
    if problems:
        raise ValidationError(problems)
    if clean:
        with transaction(conn):
            conn.execute(f"UPDATE invoice_header SET {', '.join(f'{k} = ?' for k in clean)} WHERE invoice_id = ?",
                         (*clean.values(), invoice_id))


def set_deleted(conn: sqlite3.Connection, invoice_id: int, deleted: bool) -> None:
    """Set or remove the delete flag (soft delete: the row stays). One of the two functions that change the
    status of an invoice (Design_Evaluation.md §4)."""
    _open_invoice(conn, invoice_id)
    with transaction(conn):
        conn.execute("UPDATE invoice_header SET is_deleted = ? WHERE invoice_id = ?", (1 if deleted else 0, invoice_id))


def close(conn: sqlite3.Connection, invoice_id: int) -> None:
    """Close an invoice: `is_closed = 1`, as the Access check box "Luk Faktura" did, with no other change
    (decision 8). A closed invoice is read-only. The other function that changes the status of an invoice."""
    _open_invoice(conn, invoice_id)
    with transaction(conn):
        conn.execute("UPDATE invoice_header SET is_closed = 1 WHERE invoice_id = ?", (invoice_id,))
