"""Master data: wines, their sales and cost prices, customers and warehouses. The UI uses these functions and
never queries the tables itself.

Maintenance (design doc §6.6, decision 18; step 10) works as in the Access forms. "Delete" on a wine marks it
discontinued (Access "Udgaaet") and on a customer hides it (Access "Skjul kunde"); both can be undone and the
row stays. Warehouses cannot be deleted. Sales and cost price rows are really deleted, as the Access price
forms did: the one exception to the rule "rows are never deleted" (decision 19). Nothing points to a price
row, because each invoice line keeps its own copy of the price, the VAT rate and the price type."""
import sqlite3

from winedb.db import transaction
from winedb.validation import ValidationError

ITEM_COLUMNS = ("item_id", "item_code", "name", "vintage", "producer", "country", "bottle_size", "item_type",
                "is_discontinued", "is_private")


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


CUSTOMER_COLUMNS = ("customer_id", "customer_name", "address", "postal_code", "city", "phone", "is_hidden")


def list_customers(conn: sqlite3.Connection) -> list[dict]:
    """Return the customers for the customer picker: those that are not hidden, sorted by name, as the Access
    invoice form (fFaktura) listed them. Upper and lower case and Danish letters sort the same way."""
    rows = conn.execute(f"SELECT {', '.join(CUSTOMER_COLUMNS)} FROM customers WHERE COALESCE(is_hidden, 0) <> 1")
    return sorted((dict(r) for r in rows), key=lambda c: ((c["customer_name"] or "").casefold(), c["customer_id"]))


def get_customer(conn: sqlite3.Connection, customer_id) -> dict | None:
    """Return one customer (hidden or not), or None if no customer has this id."""
    row = conn.execute(f"SELECT {', '.join(CUSTOMER_COLUMNS)} FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
    return dict(row) if row else None


# --- Maintenance (step 10) ---
#
# A field spec is (kind, name for messages, required). Kinds: "text" (stripped, empty is NULL), "whole",
# "number", "flag" (0 or 1). Validate on write: a new row checks every field; a changed row checks only the
# fields whose value changed, so an old row from Access that breaks a rule can still be edited.

WINE_SPEC = {
    "item_code": ("text", "wine code", True), "name": ("text", "name", True), "vintage": ("whole", "vintage", True),
    "producer": ("text", "producer", False), "country": ("text", "country", False), "region": ("text", "region", False),
    "item_type": ("text", "type", False), "bottle_size": ("text", "bottle size", False),
    "drink_by_year": ("whole", "drink-by year", False), "mature_year": ("whole", "mature year", False),
    "is_discontinued": ("flag", "discontinued", False), "is_private": ("flag", "private", False),
    "comment": ("text", "comment", False),
}
CUSTOMER_SPEC = {
    "customer_name": ("text", "customer name", True), "first_name": ("text", "first name", False),
    "last_name": ("text", "last name", False), "address": ("text", "address", False),
    "postal_code": ("whole", "postal code", False), "city": ("text", "city", False), "phone": ("text", "phone", False),
    "email": ("text", "email", False), "on_mailing_list": ("flag", "mailing list", False),
    "is_hidden": ("flag", "hidden", False), "comment": ("text", "comment", False),
}
WAREHOUSE_SPEC = {"warehouse_name": ("text", "warehouse name", True), "comment": ("text", "comment", False)}
SALES_PRICE_SPEC = {"price_type": ("text", "price type", False), "sales_price": ("number", "sales price", True),
                    "vat_rate": ("number", "VAT rate", True)}
COST_PRICE_SPEC = {"price_type": ("text", "price type", False), "cost_price": ("number", "cost price", True)}

# The columns whose existing values the screens suggest while the user types (data values, never translated).
SUGGESTED = {("items", "producer"), ("items", "country"), ("items", "region"), ("items", "item_type"),
             ("items", "bottle_size"), ("prices_sales", "price_type"), ("prices_cost", "price_type")}


def _clean(kind: str, value, name: str, required: bool) -> tuple[object, str | None]:
    """(value to store, problem or None)."""
    if kind == "flag":
        return (1 if value else 0), None
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, (f"Enter the {name}." if required else None)
    if kind == "text":
        return str(value).strip(), None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"Enter the {name} as a number."
    if kind == "whole":
        if not number.is_integer():
            return None, f"Enter the {name} as a whole number."
        return int(number), None
    return number, None


def _same(kind: str, value, stored) -> bool:
    """True if the value from the screen equals the stored value (then the field is not checked or written)."""
    if value == stored:                  # also an old value that breaks a rule: unchanged, so never checked
        return True
    clean, problem = _clean(kind, value, "", False)
    if problem:
        return False
    if kind == "flag":
        return clean == (1 if stored else 0)
    if kind in ("whole", "number") and clean is not None and stored is not None:
        try:
            return float(clean) == float(stored)
        except (TypeError, ValueError):
            return False
    if kind == "text" and stored is not None:
        stored = str(stored).strip() or None
    return clean == stored


def _save(conn: sqlite3.Connection, table: str, key: str, spec: dict, values: dict, row_id=None,
          check=None, fixed: dict | None = None) -> int:
    """Insert (row_id None) or update one row of a master data table and return its id. `check(clean, fields)`
    adds rules that need the database; `fixed` are columns the program sets (for example the wine of a price)."""
    stored = None
    if row_id is not None:
        stored = conn.execute(f"SELECT * FROM {table} WHERE {key} = ?", (row_id,)).fetchone()
        if stored is None:
            raise ValidationError([f"Row {row_id} does not exist."])
    fields, clean = {}, {}
    for field, (kind, name, required) in spec.items():
        if field not in values:
            if stored is None and required:
                fields[field] = f"Enter the {name}."
            continue
        if stored is not None and _same(kind, values[field], stored[field]):
            continue
        clean[field], problem = _clean(kind, values[field], name, required)
        if problem:
            fields[field] = problem
    if check:
        check(clean, fields)
    if fields:
        raise ValidationError(list(fields.values()), fields)
    if stored is None:
        # An empty field is left out, so the column gets its default, as in Access (for example postal code 0).
        columns = {**{k: v for k, v in clean.items() if v is not None}, **(fixed or {})}
        with transaction(conn):
            cursor = conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                                  tuple(columns.values()))
        return cursor.lastrowid
    if clean:
        with transaction(conn):
            conn.execute(f"UPDATE {table} SET {', '.join(f'{c} = ?' for c in clean)} WHERE {key} = ?",
                         (*clean.values(), row_id))
    return row_id


def suggestions(conn: sqlite3.Connection, table: str, column: str) -> list[str]:
    """The different values of a text column, sorted without case, for the "type or choose" fields."""
    if (table, column) not in SUGGESTED:
        raise ValueError(f"No suggestions for {table}.{column}")
    values = {r[0] for r in conn.execute(f"SELECT DISTINCT {column} FROM {table} WHERE TRIM(COALESCE({column}, '')) <> ''")}
    return sorted(values, key=lambda v: (v.casefold(), v))


# Wines

def list_wines(conn: sqlite3.Connection, include_discontinued: bool = False) -> list[dict]:
    """The wine list for maintenance, sorted by name and vintage. Discontinued wines only when asked for (the
    Access form fVinliste_Vedligehold filtered them out)."""
    where = "" if include_discontinued else " WHERE COALESCE(is_discontinued, 0) <> 1"
    rows = conn.execute(f"SELECT item_id, {', '.join(WINE_SPEC)} FROM items{where}")
    return sorted((dict(r) for r in rows), key=lambda w: ((w["name"] or "").casefold(), w["vintage"] or 0, w["item_id"]))


def get_wine(conn: sqlite3.Connection, item_id) -> dict | None:
    """One wine with all its fields, or None."""
    row = conn.execute(f"SELECT item_id, {', '.join(WINE_SPEC)} FROM items WHERE item_id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def save_wine(conn: sqlite3.Connection, values: dict, item_id=None) -> int:
    """Add a wine (item_id None) or change one; return its id. The wine code must be unique (upper and lower
    case are the same, as the Access index)."""
    def check(clean, fields):
        code = clean.get("item_code")
        if code:
            other = conn.execute("SELECT item_id FROM items WHERE item_code = ? COLLATE NOCASE AND item_id IS NOT ?",
                                 (code, item_id)).fetchone()
            if other:
                fields["item_code"] = f"Another wine (id {other[0]}) has the code {code}."
    return _save(conn, "items", "item_id", WINE_SPEC, values, item_id, check)


def set_wine_discontinued(conn: sqlite3.Connection, item_id, discontinued: bool) -> None:
    """"Delete" a wine as Access did: mark it discontinued. False undoes it. The row and its history stay."""
    _save(conn, "items", "item_id", WINE_SPEC, {"is_discontinued": discontinued}, item_id)


# Sales and cost prices of a wine (read with invoices.sales_prices() and invoices.cost_prices())

def _wine_must_exist(conn: sqlite3.Connection, item_id) -> None:
    if item_id in (None, "") or not conn.execute("SELECT 1 FROM items WHERE item_id = ?", (item_id,)).fetchone():
        raise ValidationError(["Choose a wine first."])


def _price_of_wine(conn: sqlite3.Connection, table: str, key: str, price_id, item_id) -> None:
    row = conn.execute(f"SELECT item_id FROM {table} WHERE {key} = ?", (price_id,)).fetchone()
    if row is None or row[0] != item_id:
        raise ValidationError([f"Price {price_id} is not a price of wine {item_id}."])


def save_sales_price(conn: sqlite3.Connection, item_id, values: dict, sales_price_id=None) -> int:
    """Add or change a row of the wine's sales price list. The price includes VAT; the VAT rate is a fraction
    (0.25 = 25 %)."""
    _wine_must_exist(conn, item_id)
    if sales_price_id is not None:
        _price_of_wine(conn, "prices_sales", "sales_price_id", sales_price_id, item_id)

    def check(clean, fields):
        vat = clean.get("vat_rate")
        if vat is not None and not 0 <= vat < 1:
            fields["vat_rate"] = "Enter the VAT rate from 0 % to under 100 %."
    return _save(conn, "prices_sales", "sales_price_id", SALES_PRICE_SPEC, values, sales_price_id, check,
                 {"item_id": item_id})


def save_cost_price(conn: sqlite3.Connection, item_id, values: dict, cost_price_id=None) -> int:
    """Add or change a row of the wine's cost price list. The row of type "Standard" with the lowest id is the
    default cost of a new invoice line (logic.default_cost)."""
    _wine_must_exist(conn, item_id)
    if cost_price_id is not None:
        _price_of_wine(conn, "prices_cost", "cost_price_id", cost_price_id, item_id)
    return _save(conn, "prices_cost", "cost_price_id", COST_PRICE_SPEC, values, cost_price_id, fixed={"item_id": item_id})


def delete_sales_price(conn: sqlite3.Connection, item_id, sales_price_id) -> None:
    """Really delete a sales price row, as Access did (decision 19)."""
    _price_of_wine(conn, "prices_sales", "sales_price_id", sales_price_id, item_id)
    with transaction(conn):
        conn.execute("DELETE FROM prices_sales WHERE sales_price_id = ?", (sales_price_id,))


def delete_cost_price(conn: sqlite3.Connection, item_id, cost_price_id) -> None:
    """Really delete a cost price row, as Access did (decision 19)."""
    _price_of_wine(conn, "prices_cost", "cost_price_id", cost_price_id, item_id)
    with transaction(conn):
        conn.execute("DELETE FROM prices_cost WHERE cost_price_id = ?", (cost_price_id,))


# Customers

def list_customer_records(conn: sqlite3.Connection, include_hidden: bool = False) -> list[dict]:
    """The customers for maintenance, sorted by name. Hidden customers only when asked for (the Access form
    fKunder filtered them out)."""
    where = "" if include_hidden else " WHERE COALESCE(is_hidden, 0) <> 1"
    rows = conn.execute(f"SELECT customer_id, {', '.join(CUSTOMER_SPEC)} FROM customers{where}")
    return sorted((dict(r) for r in rows), key=lambda c: ((c["customer_name"] or "").casefold(), c["customer_id"]))


def get_customer_record(conn: sqlite3.Connection, customer_id) -> dict | None:
    """One customer with all its fields, or None."""
    row = conn.execute(f"SELECT customer_id, {', '.join(CUSTOMER_SPEC)} FROM customers WHERE customer_id = ?",
                       (customer_id,)).fetchone()
    return dict(row) if row else None


def save_customer(conn: sqlite3.Connection, values: dict, customer_id=None) -> int:
    """Add a customer (customer_id None) or change one; return the customer number."""
    return _save(conn, "customers", "customer_id", CUSTOMER_SPEC, values, customer_id)


def set_customer_hidden(conn: sqlite3.Connection, customer_id, hidden: bool) -> None:
    """"Delete" a customer as Access did: hide it. False shows it again. Old invoices keep the customer."""
    _save(conn, "customers", "customer_id", CUSTOMER_SPEC, {"is_hidden": hidden}, customer_id)


# Warehouses (no delete: Access did not allow it)

def list_warehouse_records(conn: sqlite3.Connection) -> list[dict]:
    """The warehouses with their comment, sorted by id."""
    return [dict(r) for r in conn.execute("SELECT warehouse_id, warehouse_name, comment FROM warehouses ORDER BY warehouse_id")]


def save_warehouse(conn: sqlite3.Connection, values: dict, warehouse_id=None) -> int:
    """Add a warehouse (warehouse_id None) or change one; return its id."""
    return _save(conn, "warehouses", "warehouse_id", WAREHOUSE_SPEC, values, warehouse_id)
