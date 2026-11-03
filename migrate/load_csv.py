"""One-time load of the Access CSV export into a new SQLite database (schema version 1).

    python -m migrate.load_csv <csv_dir> <new_database_file> [--summary] [--report FILE]

Principles (design doc section 8, step 3):
- Faithful, not clean: rows are inserted as they are. Nothing is repaired, defaulted or dropped.
- Strict: a CSV whose header differs from COLUMN_MAP, or a value that cannot be converted, stops the
  load and nothing is written (one transaction).
- Only the documented conversions: True/False -> 1/0, empty cell -> NULL, numbers parsed.
- Original ids are kept; AUTOINCREMENT continues after the max id.
- The target must be a new/empty database at schema version 1 (this tool is not kept compatible with
  later migrations: the Access import happens once).
"""
import argparse
import csv
import sys
from pathlib import Path

from migrate.column_map import COLUMN_MAP, TABLE_MAP
from winedb.db import connect

SCHEMA_VERSION = 1


class LoadError(RuntimeError):
    pass


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    """Header and rows exactly as in the file (UTF-8, BOM allowed, quoted newlines kept)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise LoadError(f"{path.name}: empty file")
        rows = list(reader)
    for n, row in enumerate(rows, start=2):
        if len(row) != len(header):
            raise LoadError(f"{path.name} line {n}: {len(row)} cells, header has {len(header)}")
    return header, rows


def convert(value: str, sql_type: str, where: str):
    """The only conversions: empty -> NULL, True/False -> 1/0, INTEGER/REAL parsed, TEXT unchanged."""
    if value == "":
        return None
    if sql_type == "TEXT":
        return value
    if value in ("True", "False"):
        if sql_type != "INTEGER":
            raise LoadError(f"{where}: boolean {value!r} in a {sql_type} column")
        return 1 if value == "True" else 0
    try:
        return int(value) if sql_type == "INTEGER" else float(value)
    except ValueError:
        raise LoadError(f"{where}: {value!r} is not a valid {sql_type}")


def column_types(conn, table: str) -> dict[str, str]:
    return {r["name"]: r["type"].upper() for r in conn.execute(f'PRAGMA table_info("{table}")')}


def load(csv_dir: Path | str, db_file: Path | str) -> dict[str, int]:
    """Create db_file (must not hold data yet) and load all tables. Returns rows loaded per table."""
    csv_dir, db_file = Path(csv_dir), Path(db_file)
    # Read and validate everything before touching the database.
    data = {}
    for access_table, mapping in COLUMN_MAP.items():
        path = csv_dir / f"{access_table}.csv"
        if not path.exists():
            raise LoadError(f"Missing {path}")
        header, rows = read_csv(path)
        if header != list(mapping):
            raise LoadError(
                f"{path.name}: header differs from COLUMN_MAP. "
                f"Unknown in CSV: {sorted(set(header) - set(mapping))}; missing in CSV: {sorted(set(mapping) - set(header))}; "
                f"same columns in a different order: {set(header) == set(mapping)}"
            )
        data[access_table] = rows

    conn = connect(db_file)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise LoadError(f"{db_file} is at schema version {version}; this tool only loads into version {SCHEMA_VERSION}")
        for table in TABLE_MAP.values():
            if conn.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone():
                raise LoadError(f"{db_file} already has rows in {table}; load into a new file")

        loaded = {}
        conn.execute("BEGIN")
        try:
            for access_table, rows in data.items():
                table = TABLE_MAP[access_table]
                columns = list(COLUMN_MAP[access_table].values())
                types = column_types(conn, table)
                sql = f'INSERT INTO "{table}" ({", ".join(columns)}) VALUES ({", ".join("?" * len(columns))})'
                for n, row in enumerate(rows, start=2):
                    values = [convert(v, types[c], f"{access_table}.csv line {n} column {c}") for v, c in zip(row, columns)]
                    conn.execute(sql, values)
                loaded[table] = len(rows)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return loaded


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="One-time load of the Access CSV export into a new database")
    p.add_argument("csv_dir")
    p.add_argument("database", help="new database file; must not exist or must be empty")
    p.add_argument("--summary", action="store_true", help="report without row-level data (safe to share)")
    p.add_argument("--report", help="also write the report to this file")
    args = p.parse_args(argv)

    from migrate.verify import run_all, render  # imported late: verify is independent of the loader

    try:
        loaded = load(args.csv_dir, args.database)
    except LoadError as e:
        print(f"LOAD FAILED, nothing written: {e}", file=sys.stderr)
        return 2
    results = run_all(args.csv_dir, args.database)
    text = render(results, loaded, summary=args.summary)
    print(text)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
