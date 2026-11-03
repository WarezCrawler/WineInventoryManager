"""One-time import from an Access file into the app's database (used by the import button).

Steps: read the .accdb into temporary CSV files -> load them into a temporary new database -> run the
independent audit -> only if there is no FAIL, copy the result into the target database and settings.json. The target is
untouched on any failure, and the temporary files (they hold business data) are always removed.
"""
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from migrate.load_csv import LoadError, load
from migrate.read_accdb import AccdbError, export_csv
from migrate.verify import render, run_all
from winedb.config import db_path
from winedb.db import connect
from winedb.settings import has_values, settings_path


@dataclass
class ImportOutcome:
    ok: bool
    message: str   # one line for the user
    report: str    # the audit report (empty if the import stopped before it)


def target_has_data(db_file: Path | str) -> bool:
    conn = connect(db_file)  # creates/upgrades the file if needed
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return any(conn.execute(f'SELECT 1 FROM "{n}" LIMIT 1').fetchone() for n in names)
    finally:
        conn.close()


def import_accdb(accdb: Path | str, target: Path | str | None = None, settings_target: Path | str | None = None) -> ImportOutcome:
    target = Path(target) if target is not None else db_path()
    settings_target = Path(settings_target) if settings_target is not None else settings_path()
    accdb = Path(accdb)
    if target_has_data(target):
        return ImportOutcome(False, "The database already contains data. The import only works into an empty database.", "")
    if has_values(settings_target):
        return ImportOutcome(False, f"{settings_target.name} already has settings. The import only works into empty settings: "
                                    "move or empty that file first.", "")
    with tempfile.TemporaryDirectory(prefix="wine-import-") as tmp:
        tmp = Path(tmp)
        try:
            export_csv(accdb, tmp / "csv")
            loaded = load(tmp / "csv", tmp / "staging.db", tmp / "settings.json")
        except (AccdbError, LoadError) as e:
            return ImportOutcome(False, f"Import stopped, nothing was changed: {e}", "")
        results = run_all(tmp / "csv", tmp / "staging.db", tmp / "settings.json")
        report = render(results, loaded)
        failed = [r for r in results if r.status == "FAIL"]
        if failed:
            return ImportOutcome(False, f"The audit found {len(failed)} FAIL: nothing was imported. See the report.", report)
        src = sqlite3.connect(tmp / "staging.db")
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)  # the target was verified empty above
        finally:
            src.close()
            dst.close()
        settings_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tmp / "settings.json", settings_target)
    tables = {k: v for k, v in loaded.items() if k != "settings.json"}
    return ImportOutcome(True, f"Imported {sum(tables.values())} rows in {len(tables)} tables and {loaded.get('settings.json', 0)} settings. "
                               "The import matches the source.", report)
