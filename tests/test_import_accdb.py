"""Import flow (read -> load -> audit -> copy into the target). The .accdb reader is replaced by synthetic
CSVs here; set WINE_ACCDB (and WINE_CSV_DIR) to also test the real reader against a real export."""
import json
import os
import sqlite3
from pathlib import Path

import pytest

import migrate.import_accdb as ia
from migrate.import_accdb import import_accdb, target_has_data
from migrate.read_accdb import AccdbError, cell_text
from tests.test_load_csv import write_csvs


@pytest.fixture
def fake_reader(monkeypatch):
    def _install(overrides=None, error=None):
        def fake(accdb, out_dir):
            if error:
                raise AccdbError(error)
            write_csvs(Path(out_dir), overrides)
        monkeypatch.setattr(ia, "export_csv", fake)
    return _install


def rows(db, table):
    c = sqlite3.connect(db)
    try:
        return c.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    finally:
        c.close()


def test_success_copies_the_verified_data_into_the_target(tmp_path, fake_reader):
    fake_reader()
    target = tmp_path / "wine.db"
    out = import_accdb("x.accdb", target, target.parent / "settings.json")
    assert out.ok and "Imported 8 rows in 8 tables and 4 settings" in out.message
    assert rows(target, "customers") == 1 and rows(target, "invoice_lines") == 1
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["invoice_bank_details"] == "Konto 1234"
    assert sqlite3.connect(target).execute("PRAGMA user_version").fetchone()[0] == 1
    assert not target_has_data(tmp_path / "other.db")


def test_refuses_a_target_that_has_data(tmp_path, fake_reader):
    fake_reader()
    target = tmp_path / "wine.db"
    assert import_accdb("x.accdb", target, target.parent / "settings.json").ok
    again = import_accdb("x.accdb", target, target.parent / "settings.json")
    assert not again.ok and "already contains data" in again.message
    assert rows(target, "customers") == 1  # unchanged


def test_refuses_settings_that_already_have_values(tmp_path, fake_reader):
    fake_reader()
    (tmp_path / "settings.json").write_text(json.dumps({"invoice_pdf_folder": "D:/mine"}), encoding="utf-8")
    out = import_accdb("x.accdb", tmp_path / "wine.db", tmp_path / "settings.json")
    assert not out.ok and "already has settings" in out.message
    assert not target_has_data(tmp_path / "wine.db")
    assert "D:/mine" in (tmp_path / "settings.json").read_text(encoding="utf-8")  # untouched


def test_unreadable_file_leaves_the_target_empty(tmp_path, fake_reader):
    fake_reader(error="not an Access database")
    target = tmp_path / "wine.db"
    out = import_accdb("x.accdb", target, target.parent / "settings.json")
    assert not out.ok and "nothing was changed" in out.message
    assert not target_has_data(target)


def test_audit_failure_imports_nothing(tmp_path, fake_reader, monkeypatch):
    fake_reader()
    real = ia.run_all
    def broken(*args):
        results = real(*args)
        results[0].status = "FAIL"
        return results
    monkeypatch.setattr(ia, "run_all", broken)
    target = tmp_path / "wine.db"
    out = import_accdb("x.accdb", target, target.parent / "settings.json")
    assert not out.ok and "nothing was imported" in out.message and out.report
    assert not target_has_data(target)
    assert not (tmp_path / "settings.json").exists()  # settings are only written after a clean audit


def test_temporary_files_are_removed(tmp_path, fake_reader, monkeypatch):
    fake_reader()
    seen = []
    real = ia.tempfile.TemporaryDirectory
    monkeypatch.setattr(ia.tempfile, "TemporaryDirectory", lambda **kw: seen.append(real(**kw)) or seen[-1])
    import_accdb("x.accdb", tmp_path / "wine.db", tmp_path / "settings.json")
    assert seen and not Path(seen[0].name).exists()


def test_cell_text_matches_the_access_export_format():
    assert cell_text(None, False) == "" and cell_text(True, False) == "True" and cell_text(False, False) == "False"
    assert cell_text(125.0, False) == "125" and cell_text(0.25, False) == "0.25"
    assert cell_text(120.75749969482422, True) == "120.7575"            # Single column: shortest 4-byte form
    assert cell_text(120.75749969482422, False) == "120.75749969482422"  # Double column: as stored
    assert cell_text("Rød", False) == "Rød" and cell_text(7, False) == "7"


@pytest.mark.skipif(not (os.environ.get("WINE_ACCDB") and os.environ.get("WINE_CSV_DIR")),
                    reason="set WINE_ACCDB and WINE_CSV_DIR to test the reader against a real Access export")
def test_real_accdb_reads_identically_to_the_access_export(tmp_path):
    from migrate.read_accdb import export_csv
    export_csv(os.environ["WINE_ACCDB"], tmp_path)
    for f in Path(os.environ["WINE_CSV_DIR"]).glob("t*.csv"):
        assert (tmp_path / f.name).read_bytes().replace(b"\r\n", b"\n") == f.read_bytes().replace(b"\r\n", b"\n"), f.name
