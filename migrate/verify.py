"""Independent audit of a loaded database against its source CSV files.

Deliberately shares no code with load_csv.py: it re-reads the CSVs with its own reader and compares in
the opposite direction (database value -> CSV text). Expected values are computed from the CSVs, never
typed in, so the same audit is valid for any export.

Status meanings:
  PASS    the check holds
  FAIL    the migration is wrong (loader/mapping error): must be fixed before use
  REVIEW  the Access data itself has this property (already there before the import): the app tolerates
          it by design (validation is on write only); listed so it can be looked at, never blocked
  INFO    facts for the reader (e.g. which coded values occur)
"""
import csv
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from migrate.column_map import COLUMN_MAP, TABLE_MAP

MAX_ROWS_SHOWN = 25


@dataclass
class Result:
    name: str
    status: str
    detail: str = ""
    rows: list[str] = field(default_factory=list)  # row-level data: left out of a --summary report


def _read(csv_dir: Path, access_table: str):
    with open(Path(csv_dir) / f"{access_table}.csv", newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def _same(text: str, value) -> bool:
    """Does the database value represent this CSV cell?"""
    if text == "":
        return value is None
    if value is None:
        return False
    if text in ("True", "False"):
        return isinstance(value, int) and value == (1 if text == "True" else 0)
    if isinstance(value, int):
        try:
            return int(text) == value
        except ValueError:
            return False
    if isinstance(value, float):
        try:
            return float(text) == value
        except ValueError:
            return False
    return isinstance(value, str) and value == text


def check_cells(conn, csv_dir) -> list[Result]:
    """Every cell of every row: CSV text vs database value."""
    out = []
    for access_table, mapping in COLUMN_MAP.items():
        table = TABLE_MAP[access_table]
        old_cols, new_cols = list(mapping), list(mapping.values())
        _, csv_rows = _read(csv_dir, access_table)
        db_rows = [tuple(r) for r in conn.execute(f'SELECT {", ".join(new_cols)} FROM "{table}" ORDER BY rowid')]
        problems = []
        if len(csv_rows) != len(db_rows):
            problems.append(f"row count: CSV {len(csv_rows)}, database {len(db_rows)}")
        # Rows are matched by position (the load keeps file order via rowid) and by key.
        for n, (c, d) in enumerate(zip(csv_rows, db_rows), start=2):
            if not _same(c[old_cols[0]], d[0]):
                problems.append(f"line {n}: key differs (CSV {c[old_cols[0]]!r}, database {d[0]!r})")
                continue
            for old, new, value in zip(old_cols, new_cols, d):
                if not _same(c[old], value):
                    problems.append(f"line {n} key {c[old_cols[0]]!r} column {new}: CSV {c[old]!r}, database {value!r}")
        status = "FAIL" if problems else "PASS"
        out.append(Result(f"cells {table}", status,
                          f"{len(csv_rows)} rows x {len(old_cols)} columns compared" if not problems else f"{len(problems)} differences",
                          problems[:MAX_ROWS_SHOWN]))
    return out


def check_aggregates(conn, csv_dir) -> list[Result]:
    """Independent fingerprints: nulls, numeric sums, text lengths, max keys."""
    out = []
    for access_table, mapping in COLUMN_MAP.items():
        table = TABLE_MAP[access_table]
        _, rows = _read(csv_dir, access_table)
        types = {r[1]: r[2].upper() for r in conn.execute(f'PRAGMA table_info("{table}")')}
        diffs = []
        for old, new in mapping.items():
            col = [r[old] for r in rows]
            nulls = sum(1 for v in col if v == "")
            db_nulls = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{new}" IS NULL').fetchone()[0]
            if nulls != db_nulls:
                diffs.append(f"{new}: empty cells {nulls}, NULLs {db_nulls}")
            t = types[new]
            if t == "TEXT":
                src = sum(len(v) for v in col)
                db = conn.execute(f'SELECT COALESCE(SUM(LENGTH("{new}")), 0) FROM "{table}"').fetchone()[0]
                if src != db:
                    diffs.append(f"{new}: total text length {src} vs {db}")
            else:
                src = sum(1.0 if v == "True" else 0.0 if v == "False" else float(v) for v in col if v != "")
                db = conn.execute(f'SELECT COALESCE(SUM("{new}"), 0) FROM "{table}"').fetchone()[0]
                if abs(src - db) > 1e-6 * max(1.0, abs(src)):
                    diffs.append(f"{new}: sum {src!r} vs {db!r}")
        out.append(Result(f"aggregates {table}", "FAIL" if diffs else "PASS",
                          f"{len(rows)} rows, nulls/sums/text lengths per column" if not diffs else f"{len(diffs)} differences", diffs))
    return out


def check_autoincrement(db_file) -> Result:
    """On a throw-away copy: the next insert gets max(id)+1 in every AUTOINCREMENT table."""
    src = sqlite3.connect(db_file)
    mem = sqlite3.connect(":memory:")
    src.backup(mem)
    src.close()
    bad = []
    for table in TABLE_MAP.values():
        pk = next((r[1] for r in mem.execute(f'PRAGMA table_info("{table}")') if r[5] == 1 and r[2].upper() == "INTEGER"), None)
        if pk is None:
            continue  # app_settings: text key
        top = mem.execute(f'SELECT COALESCE(MAX("{pk}"), 0) FROM "{table}"').fetchone()[0]
        try:
            cols = [r[1] for r in mem.execute(f'PRAGMA table_info("{table}")') if r[3] and r[1] != pk]
            mem.execute(f'INSERT INTO "{table}" ({", ".join(cols)}) VALUES ({", ".join(["1"] * len(cols))})' if cols
                        else f'INSERT INTO "{table}" DEFAULT VALUES')
            new = mem.execute("SELECT last_insert_rowid()").fetchone()[0]
        except sqlite3.Error as e:
            bad.append(f"{table}: test insert failed ({e})")
            continue
        if new != top + 1:
            bad.append(f"{table}: next id {new}, expected {top + 1}")
    mem.close()
    return Result("autoincrement continues after max id", "FAIL" if bad else "PASS", "tested on a throw-away copy", bad)


def _review(name, conn, sql, what, show) -> Result:
    rows = [tuple(r) for r in conn.execute(sql)]
    if not rows:
        return Result(name, "PASS", "none")
    return Result(name, "REVIEW", f"{len(rows)} {what}", [show(r) for r in rows[:MAX_ROWS_SHOWN]])


def check_data_quality(conn) -> list[Result]:
    """Properties of the Access data itself. Reported, never blocking."""
    q = lambda sql: [tuple(r) for r in conn.execute(sql)]
    out = [
        _review("invoices with a customer not in customers", conn,
                "SELECT invoice_id, customer_id FROM invoice_header WHERE customer_id NOT IN (SELECT customer_id FROM customers) ORDER BY 1",
                "invoice_header", lambda r: f"invoice {r[0]}: customer_id {r[1]}"),
        _review("invoices without warehouse", conn,
                "SELECT invoice_id FROM invoice_header WHERE warehouse_id IS NULL ORDER BY 1", "invoice_header", lambda r: f"invoice {r[0]}"),
        _review("invoices without date", conn,
                "SELECT invoice_id FROM invoice_header WHERE invoice_date IS NULL ORDER BY 1", "invoice_header", lambda r: f"invoice {r[0]}"),
        _review("invoices without lines", conn,
                "SELECT invoice_id FROM invoice_header WHERE invoice_id NOT IN (SELECT invoice_id FROM invoice_lines) ORDER BY 1",
                "invoice_header", lambda r: f"invoice {r[0]}"),
        _review("invoice lines without invoice", conn,
                "SELECT sales_line_id FROM invoice_lines WHERE invoice_id NOT IN (SELECT invoice_id FROM invoice_header) ORDER BY 1",
                "lines", lambda r: f"line {r[0]}"),
        _review("invoice lines without item", conn,
                "SELECT sales_line_id FROM invoice_lines WHERE item_id NOT IN (SELECT item_id FROM items) ORDER BY 1",
                "lines", lambda r: f"line {r[0]}"),
        _review("stock movements without item", conn,
                "SELECT stock_line_id FROM stock_transactions WHERE item_id NOT IN (SELECT item_id FROM items) ORDER BY 1",
                "rows", lambda r: f"row {r[0]}"),
        _review("rows with a warehouse not in warehouses", conn,
                """SELECT 'invoice_lines', sales_line_id FROM invoice_lines WHERE warehouse_id NOT IN (SELECT warehouse_id FROM warehouses)
                   UNION ALL SELECT 'stock_transactions', stock_line_id FROM stock_transactions WHERE warehouse_id NOT IN (SELECT warehouse_id FROM warehouses)
                   UNION ALL SELECT 'invoice_header', invoice_id FROM invoice_header WHERE warehouse_id IS NOT NULL AND warehouse_id NOT IN (SELECT warehouse_id FROM warehouses)""",
                "rows", lambda r: f"{r[0]} {r[1]}"),
        _review("price rows without item", conn,
                """SELECT 'prices_cost', cost_price_id FROM prices_cost WHERE item_id NOT IN (SELECT item_id FROM items)
                   UNION ALL SELECT 'prices_sales', sales_price_id FROM prices_sales WHERE item_id NOT IN (SELECT item_id FROM items)""",
                "rows", lambda r: f"{r[0]} {r[1]}"),
        _review("invoice lines with quantity empty or <= 0", conn,
                "SELECT sales_line_id, quantity FROM invoice_lines WHERE quantity IS NULL OR quantity <= 0 ORDER BY 1", "lines", lambda r: f"line {r[0]}: quantity {r[1]}"),
        _review("items without sales price", conn,
                "SELECT item_id FROM items WHERE item_id NOT IN (SELECT item_id FROM prices_sales) ORDER BY 1", "items", lambda r: f"item {r[0]}"),
        _review("items without cost price", conn,
                "SELECT item_id FROM items WHERE item_id NOT IN (SELECT item_id FROM prices_cost) ORDER BY 1", "items", lambda r: f"item {r[0]}"),
        _review("negative stock (item x warehouse; stock entries probably missing)", conn,
                """SELECT item_id, warehouse_id, SUM(q) FROM (
                     SELECT item_id, warehouse_id, quantity AS q FROM stock_transactions
                     UNION ALL SELECT item_id, warehouse_id, -quantity FROM invoice_lines)
                   GROUP BY item_id, warehouse_id HAVING SUM(q) < 0 ORDER BY 1, 2""",
                "combinations", lambda r: f"item {r[0]} warehouse {r[1]}: {r[2]}"),
        _review("invoices marked deleted", conn,
                "SELECT invoice_id, is_closed FROM invoice_header WHERE is_deleted = 1 ORDER BY 1", "invoice_header",
                lambda r: f"invoice {r[0]} (closed={r[1]})"),
    ]
    totals = q("SELECT (SELECT COUNT(*) FROM invoice_header WHERE is_closed = 1), (SELECT COUNT(*) FROM invoice_header WHERE is_closed = 0), "
               "(SELECT COUNT(*) FROM stock_transactions WHERE quantity < 0)")[0]
    out.append(Result("facts", "INFO", f"closed invoices {totals[0]}, open invoices {totals[1]}, negative stock movements {totals[2]}"))
    for label, sql in [
        ("item_type", "SELECT item_type, COUNT(*) FROM items GROUP BY 1 ORDER BY 1"),
        ("bottle_size", "SELECT bottle_size, COUNT(*) FROM items GROUP BY 1 ORDER BY 1"),
        ("price_type (prices_sales)", "SELECT price_type, COUNT(*) FROM prices_sales GROUP BY 1 ORDER BY 1"),
        ("price_type (prices_cost)", "SELECT price_type, COUNT(*) FROM prices_cost GROUP BY 1 ORDER BY 1"),
        ("price_type (invoice_lines)", "SELECT price_type, COUNT(*) FROM invoice_lines GROUP BY 1 ORDER BY 1"),
        ("vat_rate (invoice_lines)", "SELECT vat_rate, COUNT(*) FROM invoice_lines GROUP BY 1 ORDER BY 1"),
        ("vat_rate (prices_sales)", "SELECT vat_rate, COUNT(*) FROM prices_sales GROUP BY 1 ORDER BY 1"),
        ("country", "SELECT country, COUNT(*) FROM items GROUP BY 1 ORDER BY 1"),
    ]:
        out.append(Result(f"values of {label}", "INFO", "; ".join(f"{v!r}: {n}" for v, n in q(sql))))
    return out


def run_all(csv_dir, db_file) -> list[Result]:
    conn = sqlite3.connect(db_file)
    try:
        return [*check_cells(conn, csv_dir), *check_aggregates(conn, csv_dir),
                check_autoincrement(db_file), *check_data_quality(conn)]
    finally:
        conn.close()


def render(results: list[Result], loaded: dict[str, int] | None = None, summary: bool = False) -> str:
    counts = {s: sum(1 for r in results if r.status == s) for s in ("PASS", "FAIL", "REVIEW", "INFO")}
    lines = ["MIGRATION REPORT" + (" (summary: no row-level data)" if summary else ""),
             f"PASS {counts['PASS']}   FAIL {counts['FAIL']}   REVIEW {counts['REVIEW']}   INFO {counts['INFO']}"]
    if loaded:
        lines.append("loaded: " + ", ".join(f"{t} {n}" for t, n in loaded.items()))
    lines.append("")
    for status in ("FAIL", "REVIEW", "PASS", "INFO"):
        for r in (x for x in results if x.status == status):
            lines.append(f"[{r.status}] {r.name}: {r.detail}")
            if not summary:
                lines += [f"      {row}" for row in r.rows]
    return "\n".join(lines)
