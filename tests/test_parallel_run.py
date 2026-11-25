"""The parallel run check (step 11): compare what Access and the app changed since the same starting point."""
import os
import shutil

import pytest

from migrate.parallel_run import compare, render
from winedb.db import connect

BASE = """
    INSERT INTO warehouses (warehouse_id, warehouse_name) VALUES (1, 'Main');
    INSERT INTO customers (customer_id, customer_name) VALUES (7, 'Anna');
    INSERT INTO items (item_id, item_code, name, vintage) VALUES (10, 'A', 'Malvasia', 2012), (11, 'B', 'Rosso', 2010);
    INSERT INTO invoice_header (invoice_id, customer_id, is_closed, warehouse_id, invoice_date, is_deleted)
        VALUES (5, 7, 0, 1, '2014-05-03 00:00:00', 0);
    INSERT INTO invoice_lines (sales_line_id, item_id, created_at, quantity, invoice_id, sales_price, amount_ex_vat,
        amount_incl_vat, cost_price, amount_cost, vat_rate, warehouse_id, discount)
        VALUES (50, 10, '2014-05-03 10:00:00', 2, 5, 125, 200, 250, 50, 100, 0.25, 1, 0);
"""

# The same scenario as Access stores it and as the app stores it: a new invoice with one line, and a stock change.
SCENARIO = """
    INSERT INTO invoice_header (invoice_id, customer_id, is_closed, warehouse_id, invoice_date, is_deleted, hide_subtotals)
        VALUES ({inv}, 7, 0, 1, '2026-11-26 00:00:00', 0, 0);
    INSERT INTO invoice_lines (sales_line_id, item_id, created_at, quantity, invoice_id, sales_price, amount_ex_vat,
        amount_incl_vat, price_type, cost_price, amount_cost, vat_rate, warehouse_id, discount)
        VALUES ({line}, 11, '2026-11-26 {time}', 3, {inv}, 150, 352, 440, 'Alm', 80, 240, 0.25, 1, 10);
    INSERT INTO stock_transactions (stock_line_id, created_at, item_id, quantity, comment, warehouse_id)
        VALUES ({stock}, '2026-11-26 {time}', 10, 6, 'Parallel run', 1);
"""


@pytest.fixture
def dbs(tmp_path):
    """BEFORE, and two copies of it: what Access changed and what the app changed."""
    before = tmp_path / "before.db"
    c = connect(before)
    c.executescript(BASE)
    c.close()
    for name in ("access.db", "app.db"):
        shutil.copyfile(before, tmp_path / name)
    conns = {n: connect(tmp_path / f"{n}.db") for n in ("before", "access", "app")}
    yield conns
    for c in conns.values():
        c.close()


def check(dbs):
    results = compare(dbs["before"], dbs["access"], dbs["app"])
    return {r.table: r for r in results}, render(results)


def test_nothing_changed_is_a_pass(dbs):
    results, text = check(dbs)
    assert all(r.status == "PASS" for r in results.values())
    assert "neither system changed anything" in text


def test_the_same_scenario_passes_with_other_numbers_and_entry_times(dbs):
    # Access gave the new invoice number 9 (an AutoNumber can skip numbers); the app gave 6. The lines point to them.
    dbs["access"].executescript(SCENARIO.format(inv=9, line=60, stock=70, time="10:01:02"))
    dbs["app"].executescript(SCENARIO.format(inv=6, line=51, stock=1, time="14:22:59"))
    results, text = check(dbs)
    assert {t: r.status for t, r in results.items()} == dict.fromkeys(results, "PASS"), text
    assert (results["invoice_lines"].access_changes, results["invoice_lines"].app_changes) == (1, 1)
    assert "numbered 9 in Access and 6 in the app" in text
    assert text.startswith("Parallel run check: PASS")


def test_a_different_amount_is_reported(dbs):
    dbs["access"].executescript(SCENARIO.format(inv=6, line=51, stock=1, time="10:00:00"))
    dbs["app"].executescript(SCENARIO.format(inv=6, line=51, stock=1, time="10:00:00"))
    dbs["app"].execute("UPDATE invoice_lines SET amount_ex_vat = 352.01 WHERE sales_line_id = 51")
    results, text = check(dbs)
    assert results["invoice_lines"].status == "DIFF"
    assert "amount_ex_vat: Access 352.0, app 352.01" in text and text.startswith("Parallel run check: DIFF")


def test_a_different_date_and_a_missing_row_are_reported(dbs):
    dbs["access"].executescript(SCENARIO.format(inv=6, line=51, stock=1, time="10:00:00"))
    dbs["app"].executescript(SCENARIO.format(inv=6, line=51, stock=1, time="10:00:00"))
    dbs["app"].execute("UPDATE stock_transactions SET created_at = '2026-11-27 10:00:00'")
    dbs["app"].execute("INSERT INTO stock_transactions (item_id, quantity, warehouse_id, created_at) VALUES (11, -2, 1, '2026-11-26 10:00:00')")
    results, text = check(dbs)
    assert any("created_at: Access '2026-11-26 10:00:00', app '2026-11-27 10:00:00'" in p for p in results["stock_transactions"].problems)
    assert "new rows: 1 in Access, 2 in the app" in text


def test_changes_to_existing_rows_are_compared_by_key(dbs):
    for side in ("access", "app"):
        dbs[side].execute("UPDATE invoice_header SET is_closed = 1 WHERE invoice_id = 5")      # closed in both
    dbs["app"].execute("UPDATE items SET country = 'Italien' WHERE item_id = 11")             # only in the app
    results, text = check(dbs)
    assert results["invoice_header"].status == "PASS"
    assert results["items"].problems == ["item_id 11 (changed): country: Access None, app 'Italien'"]


def test_a_line_deleted_in_access_and_cancelled_in_the_app_is_a_note(dbs):
    dbs["access"].execute("DELETE FROM invoice_lines WHERE sales_line_id = 50")
    dbs["app"].execute("UPDATE invoice_lines SET quantity = 0, amount_ex_vat = 0, amount_incl_vat = 0, amount_cost = 0,"
                       " is_deleted = 1, comment = 'Cancelled' WHERE sales_line_id = 50")
    results, text = check(dbs)
    assert results["invoice_lines"].status == "PASS"
    assert "deleted in Access, cancelled in the app (decision 16)" in text


def test_a_row_removed_only_in_access_is_reported(dbs):
    dbs["access"].execute("DELETE FROM invoice_lines WHERE sales_line_id = 50")
    results, _ = check(dbs)
    assert results["invoice_lines"].problems == ["sales_line_id 50: removed only in Access"]


ACCDB = os.environ.get("WINE_ACCDB")


@pytest.mark.skipif(not ACCDB, reason="set WINE_ACCDB to check a real Access file against its own import")
def test_a_real_access_file_against_its_own_import_is_a_pass(tmp_path):
    from migrate.import_accdb import import_accdb
    from migrate.parallel_run import main
    before = tmp_path / "BEFORE.accdb"
    shutil.copyfile(ACCDB, before)                                       # never the original file
    assert import_accdb(before, tmp_path / "app.db", tmp_path / "settings.json").ok
    connect(tmp_path / "app.db").close()                                 # the program upgrades the file at start
    assert main([str(before), str(before), str(tmp_path / "app.db"), "--report", str(tmp_path / "report.txt")]) == 0
    assert (tmp_path / "report.txt").read_text(encoding="utf-8").startswith("Parallel run check: PASS")
