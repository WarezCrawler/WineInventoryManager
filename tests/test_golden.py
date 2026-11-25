"""Golden tests on the real data (design doc §8 step 4). They need the Access CSV export, so they run
only when WINE_CSV_DIR is set. Treat them as a contract: a later change to the formulas or to the data
model must give the same results.

The expected values come from the CSV files, not from fixed numbers, so the tests also work on a newer
copy of the Access data."""
import csv
import os
from collections import defaultdict
from pathlib import Path

import pytest

from migrate.load_csv import load
from winedb.db import connect
from winedb.invoices import open_invoices
from winedb.logic import LineAmounts, line_amounts
from winedb.stock import on_hand

CSV_DIR = os.environ.get("WINE_CSV_DIR")
pytestmark = pytest.mark.skipif(not CSV_DIR, reason="set WINE_CSV_DIR to run the golden tests on a real export")


def read_csv(name: str) -> list[dict]:
    with open(Path(CSV_DIR) / f"{name}.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def number(text: str) -> float:
    return float(text) if text else 0.0


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    path = tmp_path_factory.mktemp("golden") / "real.db"
    load(CSV_DIR, path)
    c = connect(path)
    yield c
    c.close()


def test_every_invoice_line_gives_the_stored_amounts(conn):
    rows = conn.execute(
        "SELECT sales_line_id, sales_price, quantity, discount, vat_rate, cost_price,"
        " amount_incl_vat, amount_ex_vat, amount_cost FROM invoice_lines").fetchall()
    assert len(rows) == len(read_csv("tVinlager_Salg"))
    mismatches = []
    for r in rows:
        calculated = line_amounts(r["sales_price"], r["quantity"], r["discount"], r["vat_rate"], r["cost_price"])
        stored = LineAmounts(*(0.0 if r[k] is None else r[k] for k in ("amount_incl_vat", "amount_ex_vat", "amount_cost")))
        if calculated != stored:
            mismatches.append((r["sales_line_id"], calculated, stored))
    assert mismatches == []


def test_on_hand_matches_a_calculation_from_the_csv_files(conn):
    # An independent calculation from the CSV files: movements minus sales, without the lines of
    # soft-deleted invoices (Delete = True).
    deleted = {r["Fakt_ID"] for r in read_csv("tFaktura") if r["Delete"] == "True"}
    expected = defaultdict(float)
    for r in read_csv("tVinlager"):
        expected[(int(r["Vin_ID"]), int(r["Lager_ID"]))] += number(r["Quantity"])
    for r in read_csv("tVinlager_Salg"):
        key = (int(r["Vin_ID"]), int(r["Lager_ID"]))
        expected[key] += 0  # a wine that was only sold is a combination too
        if r["Fakt_ID"] not in deleted:
            expected[key] -= number(r["Quantity"])

    calculated = {key: on_hand(conn, *key) for key in expected}
    assert calculated == expected
    negative = sum(v < 0 for v in calculated.values())
    print(f"\n{len(calculated)} combinations of wine and warehouse, {negative} with negative on-hand stock")


def test_open_invoice_list_has_every_open_invoice(conn):
    # Design doc §8 step 5: with the left join, every invoice that is not closed is in the list.
    expected = sorted((int(r["Fakt_ID"]) for r in read_csv("tFaktura") if r["Lukket"] != "True"), reverse=True)
    assert [r["invoice_id"] for r in open_invoices(conn)] == expected
    print(f"\n{len(expected)} open invoices")


def test_every_historical_line_entered_again_gives_the_stored_amounts(tmp_path):
    # Design doc §8 step 8: enter historical lines again through save_line() and get identical values. The
    # design names three cases (a discount, 0 % VAT, a negative quantity); this test enters every line that
    # the screen accepts. Lines with quantity 0 or without a real wine or warehouse cannot be entered on the
    # screen (new rules, validate on write); they are counted, not checked.
    from winedb.invoices import create_header, save_line
    path = tmp_path / "again.db"
    load(CSV_DIR, path)
    c = connect(path)
    try:
        customer = c.execute("SELECT MIN(customer_id) FROM customers").fetchone()[0]
        number = create_header(c, customer)
        old = [dict(r) for r in c.execute("SELECT * FROM invoice_lines WHERE invoice_id <> ? ORDER BY sales_line_id", (number,))]
        mismatches, refused, cases = [], [], {"discount": 0, "zero VAT": 0, "negative quantity": 0}
        for r in old:
            fields = {k: r[k] for k in ("item_id", "warehouse_id", "quantity", "sales_price", "price_type", "vat_rate",
                                        "discount", "cost_price", "comment")}
            try:
                new_id = save_line(c, number, fields)
            except Exception as e:  # noqa: BLE001  (a refused line is counted)
                refused.append((r["sales_line_id"], str(e)))
                continue
            new = c.execute("SELECT amount_incl_vat, amount_ex_vat, amount_cost FROM invoice_lines WHERE sales_line_id = ?",
                            (new_id,)).fetchone()
            stored = tuple(0.0 if r[k] is None else r[k] for k in ("amount_incl_vat", "amount_ex_vat", "amount_cost"))
            if tuple(new) != stored:
                mismatches.append((r["sales_line_id"], tuple(new), stored))
            cases["discount"] += bool(r["discount"])
            cases["zero VAT"] += r["vat_rate"] == 0
            cases["negative quantity"] += (r["quantity"] or 0) < 0
    finally:
        c.close()
    assert mismatches == []
    assert all(cases.values()), cases
    allowed = ("quantity other than 0", "Enter the quantity", "Choose a warehouse", "Choose a wine")
    assert all(any(reason in why for reason in allowed) for _, why in refused), refused
    print(f"\n{len(old) - len(refused)} lines entered again, 0 mismatches; {len(refused)} refused by the new rules; cases {cases}")


# --- Invoice PDF against the Access reference PDFs (design doc §8 step 9) ---

import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

REFERENCE_DIR = os.environ.get("WINE_REFERENCE_DIR") or (str(Path(CSV_DIR).parent / "reference_invoices") if CSV_DIR else "")
# file -> (invoice, hide_subtotals). The hidesubtotals variant was made from invoice 83 with the flag set
# (WineDB_work/scripts/Render-Invoices.ps1); the test sets the same flag on the document.
REFERENCES = {"F00062_zerovat_multipage.pdf": (62, False), "F00066_negative_qty.pdf": (66, False),
              "F00083_rabat.pdf": (83, False), "F00083_hidesubtotals.pdf": (83, True), "F00116_plain.pdf": (116, False)}


def pdf_text(path) -> str:
    """The text of a PDF, with all white space as one space. Positions are not compared."""
    out = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True, check=True).stdout
    return out.decode("utf-8")


def flat(text: str) -> str:
    return " ".join(text.split())


@pytest.fixture(scope="module")
def printed(tmp_path_factory):
    folder = tmp_path_factory.mktemp("print")
    load(CSV_DIR, folder / "real.db", folder / "settings.json")
    from winedb.settings import load_settings
    c = connect(folder / "real.db")
    yield c, load_settings(folder / "settings.json"), folder
    c.close()


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="pdftotext (poppler) is needed to read the PDFs")
@pytest.mark.parametrize("file_name", sorted(REFERENCES))
def test_invoice_pdf_shows_what_the_access_pdf_shows(file_name, printed):
    from winedb.invoice_print import PRINT_LABELS, invoice_document, padded, short_date, write_pdf
    reference = Path(REFERENCE_DIR) / file_name
    if not reference.exists():
        pytest.skip(f"no reference PDF {reference}")
    c, settings, folder = printed
    invoice_id, hide = REFERENCES[file_name]
    doc = {**invoice_document(c, invoice_id, settings), "hide_subtotals": hide}
    new = write_pdf(doc, folder / file_name)
    old_text, new_text = pdf_text(reference), pdf_text(new)
    old, ours = flat(old_text), flat(new_text)

    amounts = re.compile(r"kr\. -?[\d.]+,\d\d")
    assert sorted(amounts.findall(ours)) == sorted(amounts.findall(old))                 # every amount, same count
    assert old_text.count("\f") == new_text.count("\f")                                  # same number of pages
    quantity = re.compile(r"(-?\d+) stk i alt")
    assert quantity.findall(ours) == quantity.findall(old) == [str(doc["total_quantity"])]
    for text in {flat(line["text"]) for g in doc["groups"] for line in g["lines"]}:      # the wine lines
        assert ours.count(text) == old.count(text) > 0, text
    for label in PRINT_LABELS.values():                                                  # shown and hidden alike
        if label != PRINT_LABELS["title"]:
            assert (label in ours) == (label in old), label
    for text in (padded(invoice_id, 5), padded(doc["customer_id"], 4), short_date(doc["invoice_date"]), *doc["texts"]):
        assert flat(text) in ours and flat(text) in old, text
