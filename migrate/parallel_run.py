"""Parallel run check (design doc §8 step 11, docs/Parallel_Run.md): did Access and the new app store the same
thing for the same work?

The user takes two copies of the Access file: BEFORE (kept untouched) and AFTER (used in Access). The app works
on a database imported from BEFORE. The same scenario is entered in Access (in AFTER) and in the app. Then:

    python -m migrate.parallel_run BEFORE.accdb AFTER.accdb APP.db [--report FILE]

The check reads both Access files with the reader of the import (the files are only read), and works out, per
table, what each system changed since BEFORE: new rows, changed rows and removed rows. Then it compares the two
sets of changes field by field:
  - Changed and removed rows are matched by their key (they existed in BEFORE).
  - New rows are matched in the order they were created (the n-th new invoice in Access with the n-th new invoice
    in the app), because the two systems may give a new row a different number. Links between new rows (the
    invoice of a line, the wine of a price) are compared through this matching.
  - Times of entry (`created_at`) are compared by date only: the two entries are not made in the same second.
  - Expected differences are reported as notes, not as problems: a line cancelled in the app (decision 16) that
    was deleted in Access.

Result: PASS when both systems made the same changes; DIFF with the list of differences otherwise.
"""
import argparse
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from migrate.column_map import COLUMN_MAP, TABLE_MAP

# Parents before children, so that new parent rows are matched before the rows that point to them.
ORDER = ["warehouses", "customers", "items", "prices_sales", "prices_cost", "invoice_header", "invoice_lines",
         "stock_transactions"]
LINKS = {
    "prices_sales": {"item_id": "items"},
    "prices_cost": {"item_id": "items"},
    "invoice_header": {"customer_id": "customers", "warehouse_id": "warehouses"},
    "invoice_lines": {"invoice_id": "invoice_header", "item_id": "items", "warehouse_id": "warehouses"},
    "stock_transactions": {"item_id": "items", "warehouse_id": "warehouses"},
}
DATE_ONLY = {("invoice_lines", "created_at"), ("stock_transactions", "created_at")}
COLUMNS = {TABLE_MAP[a]: list(m.values()) for a, m in COLUMN_MAP.items()}


@dataclass
class TableResult:
    table: str
    access_changes: int = 0
    app_changes: int = 0
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "DIFF" if self.problems else "PASS"


@dataclass
class Changes:
    new: list = field(default_factory=list)       # keys, in the order they were created
    changed: list = field(default_factory=list)
    removed: list = field(default_factory=list)

    def count(self) -> int:
        return len(self.new) + len(self.changed) + len(self.removed)


def _rows(conn: sqlite3.Connection, table: str) -> dict:
    cols = COLUMNS[table]
    return {r[0]: dict(zip(cols, r)) for r in conn.execute(f'SELECT {", ".join(cols)} FROM "{table}"')}


def _changes(before: dict, after: dict) -> Changes:
    return Changes(new=sorted(k for k in after if k not in before),
                   changed=sorted(k for k in after if k in before and after[k] != before[k]),
                   removed=sorted(k for k in before if k not in after))


def _equal(table: str, column: str, a, b) -> bool:
    if (table, column) in DATE_ONLY:
        return (a or "")[:10] == (b or "")[:10]
    if isinstance(a, float) or isinstance(b, float):
        try:
            return round(float(a), 6) == round(float(b), 6)
        except (TypeError, ValueError):
            return a == b
    return a == b


def _differences(table: str, access_row: dict, app_row: dict, matched: dict, skip_key: bool) -> list[str]:
    """The columns that differ. A link from a new app row is translated to the matching Access row first."""
    out = []
    for column in COLUMNS[table][1 if skip_key else 0:]:
        a, b = access_row[column], app_row[column]
        parent = LINKS.get(table, {}).get(column)
        if parent and b in matched.get(parent, {}):
            b = matched[parent][b]
        if not _equal(table, column, a, b):
            out.append(f"{column}: Access {a!r}, app {b!r}")
    return out


def _cancelled_lines(app: sqlite3.Connection) -> set:
    cols = {r[1] for r in app.execute("PRAGMA table_info(invoice_lines)")}
    if "is_deleted" not in cols:
        return set()
    return {r[0] for r in app.execute("SELECT sales_line_id FROM invoice_lines WHERE is_deleted = 1")}


def compare(before: sqlite3.Connection, access: sqlite3.Connection, app: sqlite3.Connection) -> list[TableResult]:
    """Compare what Access (BEFORE -> access) and the app (BEFORE -> app) changed. All three are SQLite databases
    with the table and column names of the app (an Access file is loaded with the import first)."""
    matched: dict[str, dict] = {}          # table -> {app key: Access key} for new rows
    cancelled = _cancelled_lines(app)
    results = []
    for table in ORDER:
        key = COLUMNS[table][0]
        b, a, p = _rows(before, table), _rows(access, table), _rows(app, table)
        ca, cp = _changes(b, a), _changes(b, p)
        r = TableResult(table, ca.count(), cp.count())

        def expected_cancel(k) -> bool:
            return table == "invoice_lines" and k in cancelled

        for k in sorted(set(ca.removed) | set(cp.removed)):
            if k in ca.removed and k in cp.removed:
                continue
            if k in ca.removed and expected_cancel(k):
                r.notes.append(f"{key} {k}: deleted in Access, cancelled in the app (decision 16)")
                continue
            r.problems.append(f"{key} {k}: removed only in {'Access' if k in ca.removed else 'the app'}")
        for k in sorted((set(ca.changed) | set(cp.changed)) - set(ca.removed) - set(cp.removed)):
            diff = _differences(table, a[k], p[k], matched, skip_key=False)
            if diff:
                r.problems.append(f"{key} {k} (changed): " + "; ".join(diff))

        app_new = [k for k in cp.new if not expected_cancel(k)]
        for k in cp.new:
            if expected_cancel(k):
                r.notes.append(f"{key} {k}: a new line cancelled in the app (not in Access; decision 16)")
        if len(ca.new) != len(app_new):
            r.problems.append(f"new rows: {len(ca.new)} in Access, {len(app_new)} in the app")
        matched[table] = {}
        for n, (ka, kp) in enumerate(zip(ca.new, app_new), start=1):
            matched[table][kp] = ka
            diff = _differences(table, a[ka], p[kp], matched, skip_key=True)
            if diff:
                r.problems.append(f"new row {n} (Access {key} {ka}, app {key} {kp}): " + "; ".join(diff))
            elif ka != kp:
                r.notes.append(f"new row {n}: the same, but numbered {ka} in Access and {kp} in the app")
        results.append(r)
    return results


def render(results: list[TableResult]) -> str:
    ok = all(r.status == "PASS" for r in results)
    lines = ["Parallel run check: " + ("PASS - Access and the app made the same changes" if ok else "DIFF - see below"), ""]
    lines.append(f"{'table':<20}{'status':<8}{'changes in Access':>18}{'changes in the app':>20}")
    for r in results:
        lines.append(f"{r.table:<20}{r.status:<8}{r.access_changes:>18}{r.app_changes:>20}")
    for r in results:
        if r.problems or r.notes:
            lines += ["", f"{r.table}:"]
            lines += [f"  DIFF  {p}" for p in r.problems]
            lines += [f"  note  {n}" for n in r.notes]
    if not any(r.access_changes or r.app_changes for r in results):
        lines += ["", "Note: neither system changed anything since BEFORE."]
    return "\n".join(lines) + "\n"


def load_accdb(accdb: Path | str, folder: Path) -> sqlite3.Connection:
    """Read an Access file (only read) into a new SQLite database in `folder`, with the import's reader and loader."""
    from migrate.load_csv import load
    from migrate.read_accdb import export_csv
    folder.mkdir(parents=True, exist_ok=True)
    export_csv(accdb, folder / "csv")
    load(folder / "csv", folder / "data.db")
    return sqlite3.connect(folder / "data.db")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m migrate.parallel_run", description=__doc__.split("\n\n")[0])
    parser.add_argument("before", help="the Access file before the scenario (BEFORE.accdb, a copy)")
    parser.add_argument("after", help="the Access file after the scenario was entered in Access (AFTER.accdb)")
    parser.add_argument("app_db", help="the app database after the same scenario was entered in the app")
    parser.add_argument("--report", help="also write the report to this file")
    args = parser.parse_args(argv)
    if not Path(args.app_db).is_file():
        parser.error(f"no such file: {args.app_db}")
    with tempfile.TemporaryDirectory(prefix="wine-parallel-") as tmp:   # holds business data: always removed
        before = load_accdb(args.before, Path(tmp) / "before")
        access = load_accdb(args.after, Path(tmp) / "after")
        app = sqlite3.connect(f"file:{Path(args.app_db).as_posix()}?mode=ro", uri=True)
        try:
            results = compare(before, access, app)
        finally:
            for c in (before, access, app):
                c.close()
    text = render(results)
    print(text)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    return 0 if all(r.status == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
