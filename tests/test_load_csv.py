"""Loader and verifier tests on synthetic CSVs (no real data). The real-data audit is the report
produced by `python -m migrate.load_csv`; set WINE_CSV_DIR to also run it from pytest."""
import csv
import json
import os
import sqlite3
from pathlib import Path

import pytest

from migrate.column_map import COLUMN_MAP, SETTINGS_COLUMNS, TABLE_MAP
from migrate.load_csv import LoadError, load, main
from migrate.verify import run_all


SETTINGS_ROWS = [
    ["<fakt_adr>", "Gade 1\nÅrhus", "d"], ["<fakt_bank_opl>", "Konto 1234", "d"],
    ["<fakt_betaling_bet>", "", "d"], ["<fakt_savelocation>", "C:\\Faktura\\", "d"],
]


def write_csvs(directory: Path, overrides: dict | None = None, header_overrides: dict | None = None, settings_rows=None):
    """One valid row per table (keys 1), with æøå, a quoted newline and a boolean."""
    directory.mkdir(parents=True, exist_ok=True)
    rows = {
        "tLagre": ["1", "Main", ""],
        "tKunder": ["1", "Æble Ørsted", "Æble", "Ørsted", "Århus", "8000", 'Vej 1\nnæste "linje"', "", "False", "a@b.dk", "True", ""],
        "tVinliste": ["1", "ABC_1", "Vin Å", "2010", "DK", "Hus", "Område", "Rød", "Alm", "2030", "2020", "False", "True", ""],
        "tFaktura": ["1", "1", "True", "", "1", "2013-06-19 00:00:00", "False", "False"],
        "tVinlager": ["1", "2013-06-21 00:00:05", "1", "-6", "x", "1"],
        "tVinlager_Salg": ["1", "1", "2013-06-21 00:00:05", "3", "", "1", "120.7575", "300.5", "375.625", "Alm", "80", "240", "0.25", "1", "0"],
        "tPrisliste_Cost": ["1", "1", "Standard", "80", ""],
        "tPrisliste_Salg": ["1", "1", "Alm", "120.7575", "0.25"],
    }
    rows.update(overrides or {})
    for table, mapping in COLUMN_MAP.items():
        header = (header_overrides or {}).get(table, list(mapping))
        with open(directory / f"{table}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerow(rows[table])
    with open(directory / "tSettings.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(SETTINGS_COLUMNS)
        w.writerows((settings_rows if settings_rows is not None else SETTINGS_ROWS))


def test_load_is_faithful_and_audit_passes(tmp_path):
    write_csvs(tmp_path / "csv")
    loaded = load(tmp_path / "csv", tmp_path / "w.db", tmp_path / "settings.json")
    assert loaded == {**{t: 1 for t in TABLE_MAP.values()}, "settings.json": 4}
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8")) == {
        "invoice_address": "Gade 1\nÅrhus", "invoice_bank_details": "Konto 1234",
        "invoice_payment_terms": "", "invoice_pdf_folder": "C:\\Faktura\\"}
    assert "app_settings" not in {r[0] for r in sqlite3.connect(tmp_path / "w.db").execute("SELECT name FROM sqlite_master")}
    conn = sqlite3.connect(tmp_path / "w.db")
    assert conn.execute("SELECT address FROM customers").fetchone()[0] == 'Vej 1\nnæste "linje"'
    assert conn.execute("SELECT is_hidden, on_mailing_list FROM customers").fetchone() == (0, 1)
    assert conn.execute("SELECT sales_price FROM invoice_lines").fetchone()[0] == 120.7575
    assert conn.execute("SELECT comment FROM warehouses").fetchone()[0] is None  # empty cell -> NULL
    assert not [r for r in run_all(tmp_path / "csv", tmp_path / "w.db", tmp_path / "settings.json") if r.status == "FAIL"]


def test_data_that_breaks_rules_is_loaded_unchanged_and_reported(tmp_path):
    bad_line = ["1", "99", "2013-06-21 00:00:05", "", "", "77", "0", "0", "0", "", "0", "0", "0", "0", "0"]
    write_csvs(tmp_path / "csv", {"tVinlager_Salg": bad_line})
    load(tmp_path / "csv", tmp_path / "w.db")
    conn = sqlite3.connect(tmp_path / "w.db")
    assert conn.execute("SELECT item_id, quantity, invoice_id, warehouse_id FROM invoice_lines").fetchone() == (99, None, 77, 0)
    results = {r.name: r.status for r in run_all(tmp_path / "csv", tmp_path / "w.db")}
    assert results["invoice lines without item"] == "REVIEW"
    assert results["invoice lines without invoice"] == "REVIEW"
    assert results["invoice lines with quantity empty or <= 0"] == "REVIEW"
    assert "FAIL" not in results.values()


def test_verifier_detects_a_tampered_database(tmp_path):
    write_csvs(tmp_path / "csv")
    load(tmp_path / "csv", tmp_path / "w.db")
    conn = sqlite3.connect(tmp_path / "w.db")
    conn.execute("UPDATE items SET name = 'Vin A'")  # one character off: æøå damage
    conn.execute("UPDATE invoice_lines SET sales_price = 120.76")
    conn.commit()
    failed = {r.name for r in run_all(tmp_path / "csv", tmp_path / "w.db") if r.status == "FAIL"}
    assert {"cells items", "cells invoice_lines", "aggregates invoice_lines"} <= failed
    assert "aggregates items" not in failed  # same length: only the cell-for-cell check can see it


def test_header_mismatch_stops_the_load_and_writes_nothing(tmp_path):
    header = list(COLUMN_MAP["tKunder"]) + ["NewColumn"]
    write_csvs(tmp_path / "csv", {"tKunder": ["1"] * 13}, {"tKunder": header})
    with pytest.raises(LoadError, match="header differs"):
        load(tmp_path / "csv", tmp_path / "w.db")
    assert not (tmp_path / "w.db").exists()


def test_unparsable_value_rolls_everything_back(tmp_path):
    write_csvs(tmp_path / "csv", {"tVinlager": ["1", "2013-06-21", "1", "six", "", "1"]})
    with pytest.raises(LoadError, match="not a valid INTEGER"):
        load(tmp_path / "csv", tmp_path / "w.db")
    conn = sqlite3.connect(tmp_path / "w.db")
    assert conn.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0] == 0  # earlier tables rolled back too


def test_refuses_a_database_that_already_has_rows(tmp_path):
    write_csvs(tmp_path / "csv")
    load(tmp_path / "csv", tmp_path / "w.db")
    with pytest.raises(LoadError, match="already has rows"):
        load(tmp_path / "csv", tmp_path / "w.db")


def test_summary_report_has_no_row_level_data(tmp_path, capsys):
    write_csvs(tmp_path / "csv")
    assert main([str(tmp_path / "csv"), str(tmp_path / "w.db"), "--summary"]) == 0
    out = capsys.readouterr().out
    assert "FAIL 0" in out and "Ørsted" not in out and "a@b.dk" not in out


@pytest.mark.skipif(not os.environ.get("WINE_CSV_DIR"), reason="set WINE_CSV_DIR to audit a real export")
def test_real_export_has_no_failures(tmp_path):
    load(os.environ["WINE_CSV_DIR"], tmp_path / "real.db")
    assert not [r for r in run_all(os.environ["WINE_CSV_DIR"], tmp_path / "real.db") if r.status == "FAIL"]


def test_settings_are_checked_against_the_file(tmp_path):
    write_csvs(tmp_path / "csv")
    load(tmp_path / "csv", tmp_path / "w.db", tmp_path / "settings.json")
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    data["invoice_bank_details"] = "Konto 9999"   # tampered
    data["extra"] = "x"                            # not in Access
    (tmp_path / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    result = next(r for r in run_all(tmp_path / "csv", tmp_path / "w.db", tmp_path / "settings.json") if r.name == "settings.json")
    assert result.status == "FAIL" and len(result.rows) == 2


def test_unknown_setting_stops_the_load(tmp_path):
    write_csvs(tmp_path / "csv", settings_rows=[["<something_new>", "x", "d"]])
    with pytest.raises(LoadError, match="unknown setting"):
        load(tmp_path / "csv", tmp_path / "w.db", tmp_path / "settings.json")
    assert not (tmp_path / "settings.json").exists() and not (tmp_path / "w.db").exists()
