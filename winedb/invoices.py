"""Invoice data functions. The UI calls these functions and never queries the invoice tables itself."""
import sqlite3
from datetime import date

from winedb.db import transaction
from winedb.logic import line_amounts
from winedb.validation import ValidationError, now_text


def open_invoices(conn: sqlite3.Connection) -> list[dict]:
    """Return the open invoices for the main menu, newest first (design doc §6.1).

    An invoice is open when `is_closed` is not 1. Each row has `invoice_id`, `customer_id`,
    `customer_name` and `is_deleted`, and an overview of its lines: `total_quantity` (the sum of the
    quantities; a return counts as minus), `wine_count` (the number of different wines) and
    `amount_ex_vat` (the invoice total without VAT). Cancelled lines are left out, as in totals().

    The join to the customers is a left join (decision 2 in §10), so an invoice without a valid
    customer is in the list too; its `customer_name` is None. Access used an inner join and hid these
    invoices. Soft-deleted invoices are in the list, with `is_deleted = 1`, so that the user can find
    them and remove the flag.
    """
    rows = conn.execute(
        "SELECT h.invoice_id, h.customer_id, c.customer_name, COALESCE(h.is_deleted, 0) AS is_deleted,"
        " COALESCE(l.total_quantity, 0) AS total_quantity, COALESCE(l.wine_count, 0) AS wine_count,"
        " COALESCE(l.amount_ex_vat, 0) AS amount_ex_vat"
        " FROM invoice_header AS h LEFT JOIN customers AS c ON c.customer_id = h.customer_id"
        " LEFT JOIN (SELECT invoice_id, SUM(COALESCE(quantity, 0)) AS total_quantity,"
        "            COUNT(DISTINCT item_id) AS wine_count, SUM(COALESCE(amount_ex_vat, 0)) AS amount_ex_vat"
        "            FROM invoice_lines WHERE COALESCE(is_deleted, 0) = 0 GROUP BY invoice_id) AS l"
        "   ON l.invoice_id = h.invoice_id"
        " WHERE COALESCE(h.is_closed, 0) <> 1"
        " ORDER BY h.invoice_id DESC"
    )
    return [{**dict(r), "amount_ex_vat": round(r["amount_ex_vat"], 2)} for r in rows]


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



def reopen(conn: sqlite3.Connection, invoice_id: int) -> None:
    """Reopen a closed invoice: `is_closed = 0`, the reverse of close() and nothing else (the Access form
    fFaktura_genaaben did the same with its check box "Luk Faktura"). Step 10."""
    header = get_header(conn, invoice_id)
    if header is None:
        raise ValidationError([f"Invoice {invoice_id} does not exist."])
    if header["is_closed"] != 1:
        raise ValidationError([f"Invoice {invoice_id} is not closed."])
    with transaction(conn):
        conn.execute("UPDATE invoice_header SET is_closed = 0 WHERE invoice_id = ?", (invoice_id,))


def closed_invoices(conn: sqlite3.Connection) -> list[dict]:
    """The closed invoices, newest first, with the customer name and the invoice date (the list of the Access
    form fFaktura_genaaben; a left join, so an invoice without a valid customer is listed too)."""
    rows = conn.execute(
        "SELECT h.invoice_id, h.customer_id, c.customer_name, h.invoice_date, COALESCE(h.is_deleted, 0) AS is_deleted"
        " FROM invoice_header AS h LEFT JOIN customers AS c ON c.customer_id = h.customer_id"
        " WHERE h.is_closed = 1 ORDER BY h.invoice_id DESC")
    return [dict(r) for r in rows]

# --- Invoice lines (design doc §5.1, §5.2, §6.4; step 8) ---

LINE_FIELDS = ("item_id", "warehouse_id", "quantity", "sales_price", "price_type", "vat_rate", "discount",
               "cost_price", "comment")


def lines(conn: sqlite3.Connection, invoice_id: int) -> list[dict]:
    """Return the lines of an invoice in the order they were entered, with the wine's code, name, vintage,
    producer and type and the warehouse name. Cancelled lines are included, with `is_deleted = 1`."""
    rows = conn.execute(
        "SELECT l.sales_line_id, l.item_id, i.item_code, i.name, i.vintage, i.producer, i.item_type,"
        " l.warehouse_id, w.warehouse_name,"
        " l.created_at, l.quantity, l.sales_price, l.price_type, l.vat_rate, l.discount, l.cost_price,"
        " l.amount_ex_vat, l.amount_incl_vat, l.amount_cost, l.comment, COALESCE(l.is_deleted, 0) AS is_deleted"
        " FROM invoice_lines AS l"
        " LEFT JOIN items AS i ON i.item_id = l.item_id"
        " LEFT JOIN warehouses AS w ON w.warehouse_id = l.warehouse_id"
        " WHERE l.invoice_id = ? ORDER BY l.sales_line_id", (invoice_id,))
    return [dict(r) for r in rows]


def totals(conn: sqlite3.Connection, invoice_id: int) -> dict:
    """The invoice totals without VAT, with VAT and of the cost. Cancelled lines are left out."""
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_ex_vat), 0), COALESCE(SUM(amount_incl_vat), 0), COALESCE(SUM(amount_cost), 0)"
        " FROM invoice_lines WHERE invoice_id = ? AND COALESCE(is_deleted, 0) = 0", (invoice_id,)).fetchone()
    return {"amount_ex_vat": round(row[0], 2), "amount_incl_vat": round(row[1], 2), "amount_cost": round(row[2], 2)}


def sales_prices(conn: sqlite3.Connection, item_id) -> list[dict]:
    """The wine's rows of the sales price list (the Access sales price picker)."""
    return [dict(r) for r in conn.execute(
        "SELECT sales_price_id, price_type, sales_price, vat_rate FROM prices_sales WHERE item_id = ? ORDER BY sales_price_id",
        (item_id,))]


def cost_prices(conn: sqlite3.Connection, item_id) -> list[dict]:
    """The wine's rows of the cost price list (the Access cost price picker)."""
    return [dict(r) for r in conn.execute(
        "SELECT cost_price_id, price_type, cost_price FROM prices_cost WHERE item_id = ? ORDER BY cost_price_id",
        (item_id,))]


def _number(value, name: str, problems: list[str], whole: bool = False):
    if isinstance(value, bool) or value is None or value == "":
        problems.append(f"Enter the {name}.")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        problems.append(f"Enter the {name} as a number.")
        return None
    if whole:
        if not number.is_integer():
            problems.append(f"Enter the {name} as a whole number.")
            return None
        return int(number)
    return number


def _line_values(conn: sqlite3.Connection, values: dict) -> tuple[list[str], dict]:
    """Check all fields of a line (they all feed the amounts). Return (problems, cleaned values)."""
    problems, clean = [], {}
    item = values.get("item_id")
    if item in (None, "") or not conn.execute("SELECT 1 FROM items WHERE item_id = ?", (item,)).fetchone():
        problems.append("Choose a wine.")
    clean["item_id"] = item
    warehouse = values.get("warehouse_id")
    if warehouse in (None, "") or not conn.execute("SELECT 1 FROM warehouses WHERE warehouse_id = ?", (warehouse,)).fetchone():
        problems.append("Choose a warehouse.")
    clean["warehouse_id"] = warehouse
    quantity = _number(values.get("quantity"), "quantity", problems, whole=True)
    if quantity == 0:
        problems.append("Enter a quantity other than 0 (negative for a return). To remove a line, cancel it.")
    clean["quantity"] = quantity
    clean["sales_price"] = _number(values.get("sales_price"), "sales price", problems)
    vat = _number(values.get("vat_rate"), "VAT rate", problems)
    if vat is not None and not 0 <= vat < 1:
        problems.append("Enter the VAT rate from 0 % to under 100 %.")
    clean["vat_rate"] = vat
    discount = values.get("discount")
    clean["discount"] = 0.0 if discount in (None, "") else _number(discount, "discount", problems)
    cost = values.get("cost_price")
    clean["cost_price"] = 0.0 if cost in (None, "") else _number(cost, "cost price", problems)
    clean["price_type"] = (values.get("price_type") or "").strip() or None
    clean["comment"] = (values.get("comment") or "").strip() or None
    return problems, clean


def _line_of(conn: sqlite3.Connection, invoice_id: int, line_id: int):
    row = conn.execute("SELECT invoice_id, COALESCE(is_deleted, 0), quantity, comment FROM invoice_lines"
                       " WHERE sales_line_id = ?", (line_id,)).fetchone()
    if row is None or row[0] != invoice_id:
        raise ValidationError([f"Line {line_id} is not a line of invoice {invoice_id}."])
    if row[1] == 1:
        raise ValidationError(["This line is cancelled and cannot be changed."])
    return row


def save_line(conn: sqlite3.Connection, invoice_id: int, values: dict, line_id: int | None = None) -> int:
    """Write one invoice line, new (`line_id` None) or changed, and return its `sales_line_id`.

    The only place that writes a line (Design_Evaluation.md §4). The amounts are always calculated with
    logic.line_amounts() (§5.1), as the Access form did on each change; the line keeps a copy of the
    price, VAT rate and cost (§5.2). A new line gets `created_at` = now. `price_type` is the price list
    type of a picked sales price, or empty for a price typed by hand (stored as NULL)."""
    _open_invoice(conn, invoice_id)
    if line_id is not None:
        _line_of(conn, invoice_id, line_id)
    problems, v = _line_values(conn, {f: values.get(f) for f in LINE_FIELDS})
    if problems:
        raise ValidationError(problems)
    amounts = line_amounts(v["sales_price"], v["quantity"], v["discount"], v["vat_rate"], v["cost_price"])
    columns = {**v, "amount_incl_vat": amounts.amount_incl_vat, "amount_ex_vat": amounts.amount_ex_vat,
               "amount_cost": amounts.amount_cost}
    with transaction(conn):
        if line_id is None:
            columns.update(invoice_id=invoice_id, created_at=now_text())
            cursor = conn.execute(f"INSERT INTO invoice_lines ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                                  tuple(columns.values()))
            return cursor.lastrowid
        conn.execute(f"UPDATE invoice_lines SET {', '.join(f'{k} = ?' for k in columns)} WHERE sales_line_id = ?",
                     (*columns.values(), line_id))
    return line_id


def cancel_line(conn: sqlite3.Connection, invoice_id: int, line_id: int) -> None:
    """Cancel a wrong line (owner decision 16): quantity, discount and amounts become 0, the flag
    `is_deleted` becomes 1, and the comment records the old quantity. The row stays; a cancelled line is
    never printed and does not count in stock or totals."""
    _open_invoice(conn, invoice_id)
    row = _line_of(conn, invoice_id, line_id)
    note = f"Cancelled {now_text()[:10]}: quantity was {row[2]}." + (f" {row[3]}" if row[3] else "")
    with transaction(conn):
        conn.execute("UPDATE invoice_lines SET quantity = 0, discount = 0, amount_ex_vat = 0, amount_incl_vat = 0,"
                     " amount_cost = 0, is_deleted = 1, comment = ? WHERE sales_line_id = ?", (note, line_id))


def wines_for_sale(conn: sqlite3.Connection) -> list[dict]:
    """The wines for the wine picker on an invoice line. First the wines that are not discontinued and not
    private, sorted by name and vintage (the Access picker listed only these). Then the others, marked by
    their flags, because the Access code search ("Find Vin") also found them."""
    from winedb.masterdata import list_items
    items = list_items(conn)
    usual = [i for i in items if not i["is_discontinued"] and not i["is_private"]]
    others = [i for i in items if i["is_discontinued"] or i["is_private"]]
    key = lambda i: ((i["name"] or "").casefold(), i["vintage"] or 0, i["item_id"])  # noqa: E731
    return sorted(usual, key=key) + sorted(others, key=key)
