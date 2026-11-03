"""Audit of a loaded database against its source: is what was imported the same as the source?
Nothing else is judged (no data quality, no business rules).

Independent of load_csv.py: it re-reads the CSVs with its own reader and compares in the opposite
direction (database value -> CSV text). Expected values come from the CSVs, never from typed-in numbers.

  cells      every cell of every row
  totals     row counts, sums of every numeric column (amounts, costs, quantities, ...), empty cells,
             total text length, per table
  settings   every value of settings.json against tSettings

PASS = identical to the source. FAIL = a difference (the loader or the mapping is wrong).
"""
import csv
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from migrate.column_map import COLUMN_MAP, SETTINGS_KEYS, SETTINGS_SOURCE, TABLE_MAP

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


def check_settings(csv_dir, settings_file) -> Result:
    """Every tSettings row against settings.json (read back from the file), and nothing extra in the file."""
    import json
    _, rows = _read(csv_dir, SETTINGS_SOURCE)
    try:
        actual = json.loads(Path(settings_file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return Result("settings.json", "FAIL", f"cannot read {settings_file}: {e}")
    problems = []
    expected = {SETTINGS_KEYS.get(r["Setting"], r["Setting"]): r["Value"] for r in rows}
    for key, value in expected.items():
        if key not in actual:
            problems.append(f"{key}: missing in settings.json")
        elif actual[key] != value:
            problems.append(f"{key}: differs from the Access value")
    for key in actual:
        if key not in expected:
            problems.append(f"{key}: not in Access tSettings")
    return Result("settings.json", "FAIL" if problems else "PASS",
                  f"{len(expected)} settings compared" if not problems else f"{len(problems)} differences", problems)


def _fmt(x: float) -> str:
    return str(int(x)) if x == int(x) else f"{x:.2f}"


def check_aggregates(conn, csv_dir) -> list[Result]:
    """Row counts and column totals, source vs imported. The detail line lists the sums."""
    out = []
    for access_table, mapping in COLUMN_MAP.items():
        table = TABLE_MAP[access_table]
        _, rows = _read(csv_dir, access_table)
        types = {r[1]: r[2].upper() for r in conn.execute(f'PRAGMA table_info("{table}")')}
        db_rows = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        diffs, sums = [], []
        if db_rows != len(rows):
            diffs.append(f"row count: source {len(rows)}, imported {db_rows}")
        for old, new in mapping.items():
            col = [r[old] for r in rows]
            nulls = sum(1 for v in col if v == "")
            db_nulls = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{new}" IS NULL').fetchone()[0]
            if nulls != db_nulls:
                diffs.append(f"{new}: empty cells source {nulls}, imported {db_nulls}")
            if types[new] == "TEXT":
                src = sum(len(v) for v in col)
                db = conn.execute(f'SELECT COALESCE(SUM(LENGTH("{new}")), 0) FROM "{table}"').fetchone()[0]
                if src != db:
                    diffs.append(f"{new}: total text length source {src}, imported {db}")
            else:
                src = sum(1.0 if v == "True" else 0.0 if v == "False" else float(v) for v in col if v != "")
                db = conn.execute(f'SELECT COALESCE(SUM("{new}"), 0) FROM "{table}"').fetchone()[0]
                if abs(src - db) > 1e-6 * max(1.0, abs(src)):
                    diffs.append(f"{new}: sum source {src!r}, imported {db!r}")
                elif types[new] == "REAL" or new == "quantity":  # all sums are checked; money and quantities are shown
                    sums.append(f"{new} {_fmt(src)}")
        detail = f"{len(rows)} rows" + (f"; sums: {', '.join(sums)}" if sums else "")
        out.append(Result(f"totals {table}", "FAIL" if diffs else "PASS",
                          detail if not diffs else f"{len(diffs)} differences", diffs))
    return out


def run_all(csv_dir, db_file, settings_file=None) -> list[Result]:
    conn = sqlite3.connect(db_file)
    try:
        results = [*check_cells(conn, csv_dir), *check_aggregates(conn, csv_dir)]
        if settings_file is not None:
            results.insert(0, check_settings(csv_dir, settings_file))
        return results
    finally:
        conn.close()


def render(results: list[Result], loaded: dict[str, int] | None = None, summary: bool = False) -> str:
    failed = sum(1 for r in results if r.status == "FAIL")
    lines = ["IMPORT CHECK AGAINST SOURCE" + (" (summary: no row-level data)" if summary else ""),
             f"{len(results) - failed} identical, {failed} different" + ("" if failed else ": the import matches the source")]
    if loaded:
        lines.append("loaded: " + ", ".join(f"{t} {n}" for t, n in loaded.items()))
    lines.append("")
    for status in ("FAIL", "PASS"):
        for r in (x for x in results if x.status == status):
            lines.append(f"[{r.status}] {r.name}: {r.detail}")
            if not summary:
                lines += [f"      {row}" for row in r.rows]
    return "\n".join(lines)
