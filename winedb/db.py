"""Opening the database. A missing file is created and brought to the latest schema;
an older file is upgraded by the numbered scripts in migrations/ (version = PRAGMA user_version)."""
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from winedb.config import db_path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class SchemaTooNewError(RuntimeError):
    """The database was written by a newer version of the program."""


def _load_migrations(directory: Path) -> list[tuple[int, str]]:
    found = []
    for f in sorted(directory.glob("*.sql")):
        m = re.fullmatch(r"(\d{3})_.+\.sql", f.name)
        if not m:
            raise ValueError(f"Migration file name must be NNN_name.sql: {f.name}")
        found.append((int(m.group(1)), f.read_text(encoding="utf-8")))
    if [n for n, _ in found] != list(range(1, len(found) + 1)):
        raise ValueError(f"Migrations in {directory} must be numbered 001, 002, ... without gaps")
    return found


def latest_version(migrations_dir: Path = MIGRATIONS_DIR) -> int:
    return len(_load_migrations(migrations_dir))


def _backup(conn: sqlite3.Connection, path: Path) -> Path:
    target = path.with_name(f"{path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
    dst = sqlite3.connect(target)
    try:
        conn.backup(dst)
    finally:
        dst.close()
    return target


def connect(path: Path | str | None = None, migrations_dir: Path | str = MIGRATIONS_DIR) -> sqlite3.Connection:
    path = Path(path) if path is not None else db_path()
    migrations = _load_migrations(Path(migrations_dir))
    latest = len(migrations)

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)  # transactions are explicit below
    conn.row_factory = sqlite3.Row
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        if current > latest:
            raise SchemaTooNewError(
                f"{path} has schema version {current}, but this program only knows version {latest}. "
                "Update the program; the database was not changed."
            )
        if current < latest:
            if current > 0:  # an existing database: keep a copy before changing it
                _backup(conn, path)
            for number, sql in migrations[current:]:
                try:
                    conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
                except Exception:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise
    except Exception:
        conn.close()
        raise
    return conn
