"""The invoice printout (step 9): the document, the Access formats, the file name and the PDF."""
import re
from datetime import date

import pytest

from winedb import invoice_print
from winedb.db import connect
from winedb.invoice_print import (PRINT_LABELS, invoice_document, kr, padded, pdf_file_name, pdf_path, short_date,
                                  whole, write_pdf)
from winedb.invoices import cancel_line, create_header, save_line
from winedb.validation import ValidationError

SETTINGS = {"invoice_address": "Firm, Street 1", "invoice_bank_details": "Bank 1234", "invoice_payment_terms": "8 days",
            "invoice_pdf_folder": ""}


@pytest.fixture
def invoice(tmp_path):
    conn = connect(tmp_path / "t.db")
    conn.executescript("""
        INSERT INTO customers (customer_id, customer_name, address, postal_code, city)
            VALUES (157, 'Anna  Bo Ørn', 'Vej 1', 2700, 'Brønshøj');
        INSERT INTO warehouses (warehouse_id, warehouse_name) VALUES (1, 'Main');
        INSERT INTO items (item_id, item_code, name, vintage, producer, item_type) VALUES
            (1, 'A1', 'Malvasia', 2012, 'Abel Mendoza', 'Hvid'),
            (2, 'B2', 'Rosenberg', 2009, 'Becker Landgraf', 'Rød'),
            (3, 'B3', 'Riesling', 2011, 'becker landgraf', 'Hvid'),
            (4, 'O4', 'Øl', 2010, 'Ørsted', 'Rød'),
            (5, 'Z5', 'Zinfandel', 2015, 'Zeta', NULL),
            (6, 'N6', 'No house', 2001, NULL, 'Rød');
    """)
    number = create_header(conn, 157, invoice_date="2014-05-03", comment="Delivered.")

    def add(item, quantity=1, price=125.0, discount=0, vat=0.25):
        return save_line(conn, number, {"item_id": item, "warehouse_id": 1, "quantity": quantity, "sales_price": price,
                                        "vat_rate": vat, "discount": discount, "cost_price": 50})
    return conn, number, add


def test_access_formats():
    assert kr(1805) == "kr. 1.805,00" and kr(-35) == "kr. -35,00" and kr(0.5) == "kr. 0,50" and kr(None) == "kr. 0,00"
    assert kr(1234567.891) == "kr. 1.234.567,89"
    assert padded(83, 5) == "00083" and padded(157, 4) == "0157" and padded(None, 4) == "" and padded("x", 4) == "x"
    assert whole(2700.0) == "2700" and whole(None) == "" and whole(-1) == "-1"
    assert short_date("2014-05-03 00:00:00") == "03-05-2014" and short_date(None) == "" and short_date("old") == "old"


def test_the_labels_are_the_danish_access_labels():
    # Owner decision 17: the printout keeps the labels of rFaktura
    assert PRINT_LABELS["invoice_id"] == "Faktura nummer:" and PRINT_LABELS["total_incl_vat"] == "Samlet pris"
    assert PRINT_LABELS["vintage"] == "årgang"


def test_document_groups_by_house_without_case_in_danish_order_and_keeps_the_entry_order(invoice):
    conn, number, add = invoice
    for item in (4, 2, 1, 3, 5, 6, 2):
        add(item)
    doc = invoice_document(conn, number, SETTINGS)
    assert [g["house"] for g in doc["groups"]] == ["", "Abel Mendoza", "Becker Landgraf", "Zeta", "Ørsted"]
    becker = doc["groups"][2]["lines"]
    assert [line["text"] for line in becker] == ["Rosenberg - Rød", "Riesling - Hvid", "Rosenberg - Rød"]
    assert [line["sales_line_id"] for line in becker] == sorted(line["sales_line_id"] for line in becker)
    assert doc["groups"][3]["lines"][0]["text"] == "Zinfandel - "          # Access: & treats NULL as empty
    assert doc["texts"] == ["Firm, Street 1", "Bank 1234", "8 days"]


def test_document_totals_line_totals_and_adjustment(invoice):
    conn, number, add = invoice
    add(1, quantity=3, price=125, discount=15)       # 375 - 15 = 360 incl. VAT
    add(2, quantity=-1, price=250)                   # a return
    add(5, quantity=2, price=99.5, vat=0)
    doc = invoice_document(conn, number, SETTINGS)
    lines = [line for g in doc["groups"] for line in g["lines"]]
    assert sorted(line["line_total"] for line in lines) == [-250.0, 199.0, 375.0]   # before the discount, as Access
    assert doc["total_quantity"] == 4 and doc["adjustment"] == -15.0
    assert (doc["total_incl_vat"], doc["total_ex_vat"], doc["vat"]) == (309.0, 287.0, 22.0)   # 288 - 200 + 199


def test_cancelled_lines_are_never_printed(invoice):
    conn, number, add = invoice
    add(1)
    wrong = add(2, quantity=6, discount=10)
    cancel_line(conn, number, wrong)
    doc = invoice_document(conn, number, SETTINGS)
    assert [g["house"] for g in doc["groups"]] == ["Abel Mendoza"]
    assert (doc["total_quantity"], doc["adjustment"], doc["total_incl_vat"]) == (1, 0.0, 125.0)


def test_unknown_invoice(invoice):
    conn, _, _ = invoice
    with pytest.raises(ValidationError, match="does not exist"):
        invoice_document(conn, 999, SETTINGS)


def test_file_name_as_access(invoice):
    conn, number, _ = invoice
    doc = invoice_document(conn, number, SETTINGS)
    assert pdf_file_name(doc) == f"F{number}_ABØ157_03-05-2014.pdf"      # initials of each word, double space too
    nameless = {**doc, "customer_name": None, "customer_id": None, "invoice_date": None}
    assert pdf_file_name(nameless, today=date(2026, 11, 25)) == f"F{number}__25-11-2026.pdf"
    assert pdf_file_name({**doc, "customer_name": "/Vin ?Hus"}) == f"F{number}___157_03-05-2014.pdf"   # not allowed in a file name


def test_pdf_path_needs_an_existing_folder(invoice, tmp_path):
    conn, number, _ = invoice
    doc = invoice_document(conn, number, SETTINGS)
    with pytest.raises(ValidationError, match="No PDF folder"):
        pdf_path(doc, "")
    with pytest.raises(ValidationError, match="does not exist"):
        pdf_path(doc, str(tmp_path / "missing"))
    assert pdf_path(doc, f'"{tmp_path}"') == tmp_path / pdf_file_name(doc)


def drawn_texts(monkeypatch) -> list[str]:
    """Record every text the PDF draws (the page streams are compressed, so the file is not searched)."""
    texts, draw = [], invoice_print._Page.text

    def record(self, top, left, width, value, *args, **kwargs):
        if value not in (None, ""):
            texts.append(str(value))
        return draw(self, top, left, width, value, *args, **kwargs)
    monkeypatch.setattr(invoice_print._Page, "text", record)
    return texts


def pages(path) -> int:
    return len(re.findall(rb"/Type /Page[^s]", path.read_bytes()))


def test_pdf_has_the_lines_totals_labels_and_texts(invoice, tmp_path, monkeypatch):
    conn, number, add = invoice
    add(1, quantity=3, discount=15)
    add(2)
    texts = drawn_texts(monkeypatch)
    target = write_pdf(invoice_document(conn, number, SETTINGS), tmp_path / "out.pdf")
    assert target.read_bytes().startswith(b"%PDF") and pages(target) == 1
    assert not list(tmp_path.glob("*.tmp"))
    for expected in ("Faktura nummer:", f"{number:05d}", "03-05-2014", "0157", "Anna  Bo Ørn", "Brønshøj",
                     "Malvasia - Hvid", "kr. 125,00", "kr. 375,00", "Evt. Justering", "kr. -15,00", "kr. 485,00",
                     "Samlet pris", "Heraf moms", "Pris uden moms", "4", "Delivered.", "Firm, Street 1", "Bank 1234", "8 days"):
        assert expected in texts, expected


def test_hide_subtotals_leaves_out_unit_prices_and_line_totals(invoice, tmp_path, monkeypatch):
    conn, number, add = invoice
    add(1, quantity=2)
    conn.execute("UPDATE invoice_header SET hide_subtotals = 1 WHERE invoice_id = ?", (number,))
    conn.commit()
    texts = drawn_texts(monkeypatch)
    write_pdf(invoice_document(conn, number, SETTINGS), tmp_path / "out.pdf")
    assert "kr. 125,00" not in texts and PRINT_LABELS["unit_price"] not in texts
    assert "kr. 250,00" in texts and PRINT_LABELS["line_total"] in texts          # the totals stay
    assert "Evt. Justering" not in texts                                            # hidden when 0, as Access


def test_long_invoice_goes_on_to_more_pages_with_the_footer_on_each(invoice, tmp_path, monkeypatch):
    conn, number, add = invoice
    for n in range(60):
        add(1 + n % 6)
    texts = drawn_texts(monkeypatch)
    target = write_pdf(invoice_document(conn, number, SETTINGS), tmp_path / "out.pdf")
    assert pages(target) == 2 and texts.count("Bank 1234") == 2 and texts.count("Faktura nummer:") == 1


def test_a_locked_target_leaves_no_temporary_file(invoice, tmp_path, monkeypatch):
    conn, number, add = invoice
    add(1)

    def locked(src, dst):
        raise PermissionError("in use")
    monkeypatch.setattr(invoice_print.os, "replace", locked)
    with pytest.raises(PermissionError):
        write_pdf(invoice_document(conn, number, SETTINGS), tmp_path / "out.pdf")
    assert list(tmp_path.glob("out.pdf*")) == []


def test_pdf_with_the_company_logo(invoice, tmp_path):
    from PIL import Image                     # Pillow comes with ReportLab; it reads the PNG logo
    conn, number, add = invoice
    add(1)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (400, 60), (60, 120, 60, 255)).save(logo)
    target = write_pdf(invoice_document(conn, number, SETTINGS), tmp_path / "out.pdf", logo)
    assert b"/Subtype /Image" in target.read_bytes()
