"""Read the tables of an Access .accdb file without Access or ODBC (pure Python, access-parser) and
write them as CSV files in exactly the format of the Access export (UTF-8 with BOM, True/False,
empty cell for NULL), so load_csv.py and the audit run on them unchanged.

The .accdb is only read, never changed. Run it on a copy anyway.
"""
import csv
import struct
from pathlib import Path

from migrate.column_map import COLUMN_MAP, SETTINGS_COLUMNS, SETTINGS_SOURCE, SINGLE_COLUMNS


class AccdbError(RuntimeError):
    pass


def _f32(v: float) -> float:
    return struct.unpack("f", struct.pack("f", v))[0]


def _shortest_single(v: float) -> float:
    """Shortest decimal that is the same 4-byte float (what Access shows for a Single)."""
    for digits in range(1, 10):
        candidate = float(f"{v:.{digits}g}")
        if _f32(candidate) == v:
            return candidate
    return v


def cell_text(value, single: bool) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        value = _shortest_single(value) if single else value
        return str(int(value)) if value == int(value) and abs(value) < 1e15 else repr(value)  # Access writes 125, not 125.0
    return str(value)


def export_csv(accdb: Path | str, out_dir: Path | str) -> dict[str, int]:
    """Write one <table>.csv per table in COLUMN_MAP. Returns rows written per table."""
    try:
        from access_parser import AccessParser
    except ImportError as e:
        raise AccdbError("The access-parser package is not installed") from e
    accdb, out_dir = Path(accdb), Path(out_dir)
    if not accdb.is_file():
        raise AccdbError(f"No such file: {accdb}")
    try:
        db = AccessParser(str(accdb))
    except Exception as e:
        raise AccdbError(f"{accdb.name} could not be read as an Access database: {e}") from e
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    tables = {**{t: list(m) for t, m in COLUMN_MAP.items()}, SETTINGS_SOURCE: SETTINGS_COLUMNS}
    for table, columns in tables.items():
        if table not in db.catalog:
            raise AccdbError(f"{accdb.name} has no table {table}: this is not the Vinlager database")
        data = db.parse_table(table)
        missing = [c for c in columns if c not in data]
        if missing:
            raise AccdbError(f"Table {table} lacks columns {missing}")
        n = len(data[columns[0]])
        with open(out_dir / f"{table}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(columns)
            for i in range(n):
                w.writerow([cell_text(data[c][i], (table, c) in SINGLE_COLUMNS) for c in columns])
        written[table] = n
    return written
