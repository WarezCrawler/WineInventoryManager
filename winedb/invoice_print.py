"""The invoice printout (design doc §6.5, decision 12; replaces the Access report rFaktura).

invoice_document() collects what the invoice shows: the header, the lines grouped by wine house (producer)
and the totals. The on-screen preview and the PDF both use it, so their amounts are always the same.
write_pdf() draws the PDF with ReportLab in the layout of rFaktura (export/report_spec/rFaktura.spec.json).

The printed labels are Danish, as in Access (owner decision 17, 2026-11-25: the company and its customers are
Danish). PRINT_LABELS is the one place with Danish text in the program; the Danish letters are written as
\\u escapes. A later version can read the labels from configuration. Numbers and dates use the Danish
formats of the Access report: "kr. 1.805,00" and "03-05-2014".

Cancelled lines (decision 16) are never printed. They have quantity 0 and amount 0, so the totals are the
same with or without them; invoices.totals() leaves them out too."""
import os
import re
from datetime import date
from pathlib import Path

from winedb.config import data_dir
from winedb.invoices import get_header, lines, totals
from winedb.validation import ValidationError

PRINT_LABELS = {
    "title": "Faktura",
    "invoice_id": "Faktura nummer:",
    "invoice_date": "Fakturerings dato",
    "customer_id": "Kundenummer:",
    "quantity": "stk.",
    "wine": "Hus / vinnavn",
    "vintage": "\u00e5rgang",
    "unit_price": "stk pris m. moms",
    "line_total": "I alt",
    "total_quantity": "stk i alt",
    "adjustment": "Evt. Justering",
    "total_incl_vat": "Samlet pris",
    "vat": "Heraf moms",
    "total_ex_vat": "Pris uden moms",
}


# --- Formats of the Access report ---

def kr(value) -> str:
    """An amount as the Access format '"kr. "#,##0.00;"kr. -"#,##0.00' shows it on a Danish PC."""
    amount = round(float(value or 0), 2)
    text = f"{abs(amount):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"kr. -{text}" if amount < 0 else f"kr. {text}"


def whole(value) -> str:
    """A number as Access shows a general number: 2700, not 2700.0; empty for NULL."""
    if value is None or value == "":
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def padded(value, digits: int) -> str:
    """The Access formats '00000' (invoice number) and '0000' (customer number)."""
    if value is None or value == "":
        return ""
    try:
        return str(int(value)).zfill(digits)
    except (TypeError, ValueError):
        return str(value)        # an old value that is not a number is shown as it is


def short_date(value) -> str:
    """A stored date ('YYYY-MM-DD 00:00:00') as the Danish short date 'DD-MM-YYYY'. An old value that is
    not a date is shown as it is (validate on write only)."""
    if value in (None, ""):
        return ""
    try:
        return date.fromisoformat(str(value).strip()[:10]).strftime("%d-%m-%Y")
    except ValueError:
        return str(value)


# --- The document ---

_DANISH_ORDER = str.maketrans({"\u00e6": "{1", "\u00f8": "{2", "\u00e5": "{3"})   # the three Danish letters sort after z


def _house_key(house: str) -> str:
    """Access groups and sorts text without case, and in Danish order."""
    return house.casefold().translate(_DANISH_ORDER)


def _print_line(line: dict) -> dict:
    return {
        "sales_line_id": line["sales_line_id"],
        "quantity": line["quantity"],
        # Access: [Vin_Navn] & " - " & [Vin_Type]; & treats NULL as empty text
        "text": f"{line['name'] or ''} - {line['item_type'] or ''}",
        "vintage": line["vintage"],
        "unit_price": line["sales_price"],
        # Access: SamletPris_mMoms + Rabat, the line amount before the discount. NULL counts as 0 (§5.1).
        "line_total": round((line["amount_incl_vat"] or 0) + (line["discount"] or 0), 2),
    }


def invoice_document(conn, invoice_id: int, settings: dict) -> dict:
    """Everything the invoice shows (the record source of rFaktura). `settings` gives the three texts of
    the page footer (settings.json, decision 13)."""
    header = get_header(conn, invoice_id)
    if header is None:
        raise ValidationError([f"Invoice {invoice_id} does not exist."])
    printed = [line for line in lines(conn, invoice_id) if not line["is_deleted"]]
    groups: dict[str, dict] = {}
    for line in printed:                     # in the order the lines were entered
        house = line["producer"] or ""
        group = groups.setdefault(_house_key(house), {"house": house, "lines": []})
        group["lines"].append(_print_line(line))
    amounts = totals(conn, invoice_id)
    discount = round(sum(line["discount"] or 0 for line in printed), 2)
    return {
        **{k: header[k] for k in ("invoice_id", "customer_id", "customer_name", "address", "postal_code", "city",
                                  "invoice_date", "comment")},
        "hide_subtotals": bool(header["hide_subtotals"]),
        "is_closed": header["is_closed"] == 1,
        "is_deleted": header["is_deleted"] == 1,
        "groups": [groups[k] for k in sorted(groups)],
        "total_quantity": sum(line["quantity"] or 0 for line in printed),
        "adjustment": -discount if discount else 0.0,
        "total_incl_vat": amounts["amount_incl_vat"],
        "total_ex_vat": amounts["amount_ex_vat"],
        "vat": round(amounts["amount_incl_vat"] - amounts["amount_ex_vat"], 2),
        "texts": [settings.get(k) or "" for k in ("invoice_address", "invoice_bank_details", "invoice_payment_terms")],
    }


# --- The file ---

def pdf_file_name(doc: dict, today: date | None = None) -> str:
    """The Access file name: F<invoice>_<customer initials><customer number>_<invoice date>.pdf, for example
    F83_AB157_03-05-2014.pdf. Without an invoice date, today's date. Characters that Windows does not allow
    in a file name become '_'."""
    initials = "".join(word[:1] for word in (doc["customer_name"] or "").split(" "))
    day = short_date(doc["invoice_date"]) or (today or date.today()).strftime("%d-%m-%Y")
    name = f"F{doc['invoice_id']}_{initials}{whole(doc['customer_id'])}_{day}.pdf"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)


def pdf_path(doc: dict, folder: str) -> Path:
    """Where the PDF goes: the PDF folder from settings.json (`invoice_pdf_folder`), which must exist. Without
    that setting, the folder "invoices" in the data folder, which is made when needed (all user data in one
    folder)."""
    folder = (folder or "").strip().strip('"')
    if not folder:
        default = data_dir() / "invoices"
        default.mkdir(parents=True, exist_ok=True)
        return default / pdf_file_name(doc)
    if not Path(folder).is_dir():
        raise ValidationError([f"The PDF folder does not exist: {folder}. Create it, or change invoice_pdf_folder "
                               "in settings.json."])
    return Path(folder) / pdf_file_name(doc)


# --- The PDF (layout of rFaktura; positions in twips, 1/20 point, as in the Access spec) ---

PAGE_TOP_MARGIN = PAGE_BOTTOM_MARGIN = 1080
PAGE_LEFT_MARGIN = 504
PAGE_FOOTER_HEIGHT = 1360
REPORT_HEADER_HEIGHT = 1020
INVOICE_HEADER_HEIGHT = 1870
HOUSE_HEIGHT = 330
DETAIL_HEIGHT = 289
REPORT_FOOTER_HEIGHT = 2250
COMMENT_TOP, COMMENT_LEFT, COMMENT_WIDTH = 1980, 225, 6015
FIELD_COLOUR, LABEL_COLOUR, LINE_COLOUR = 0x404040, 0x7F7F7F, 0x000000


def _fonts() -> dict[str, str]:
    """Calibri as in Access when Windows has it (embedded in the PDF), otherwise Helvetica."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    folder = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    files = {"regular": "calibri.ttf", "bold": "calibrib.ttf", "italic": "calibrii.ttf"}
    if all((folder / f).exists() for f in files.values()):
        names = {style: "Calibri" + ("" if style == "regular" else "-" + style.title()) for style in files}
        for style, name in names.items():
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(folder / files[style])))
        return names
    return {"regular": "Helvetica", "bold": "Helvetica-Bold", "italic": "Helvetica-Oblique"}


class _Page:
    """Draws text at Access positions: `top` counts twips from the top of the page, `left` from the left
    margin."""

    def __init__(self, canvas, fonts):
        from reportlab.lib.colors import HexColor
        from reportlab.lib.pagesizes import A4

        self.canvas, self.fonts, self.colour = canvas, fonts, HexColor
        self.page_height = A4[1] * 20
        self.body_end = self.page_height - PAGE_BOTTOM_MARGIN - PAGE_FOOTER_HEIGHT

    def x(self, left: float) -> float:
        return (PAGE_LEFT_MARGIN + left) / 20

    def y(self, top: float) -> float:
        return (self.page_height - top) / 20

    def text(self, top, left, width, value, size=10, align="left", style="regular", colour=FIELD_COLOUR, cut=False,
             underline=False) -> None:
        """One text box; the Access padding is 30 twips. With `cut`, text wider than the box is cut, as Access
        did; this is used for data that would run into the next column. Fixed labels are never cut."""
        from reportlab.pdfbase.pdfmetrics import stringWidth

        text = "" if value is None else str(value)
        if not text:
            return
        font = self.fonts[style]
        room = (width - 60) / 20
        while cut and text and stringWidth(text, font, size) > room:
            text = text[:-1]
        c = self.canvas
        c.setFont(font, size)
        c.setFillColor(self.colour(colour))
        baseline = self.y(top + 30 + size * 16)
        length = stringWidth(text, font, size)
        if align == "right":
            start = self.x(left + width - 30) - length
        elif align == "centre":
            start = self.x(left + width / 2) - length / 2
        else:
            start = self.x(left + 30)
        c.drawString(start, baseline, text)
        if underline:
            c.setStrokeColor(self.colour(colour))
            c.setLineWidth(size / 16)
            c.line(start, baseline - size / 8, start + length, baseline - size / 8)

    def rule(self, top, left=120, width=10590) -> None:
        c = self.canvas
        c.setStrokeColor(self.colour(LINE_COLOUR))
        c.setLineWidth(0.75)
        c.line(self.x(left), self.y(top), self.x(left + width), self.y(top))


def _draw_svg(canvas, path, x: float, y: float, width: float, height: float) -> None:
    """Draw an SVG logo in the box, as large as fits and centred (the PNG logo is placed the same way)."""
    from reportlab.graphics import renderPDF
    from svglib.svglib import svg2rlg

    drawing = svg2rlg(str(path))
    if drawing is None or not drawing.width or not drawing.height:
        return                                   # not a usable SVG: the invoice is printed without a logo
    scale = min(width / drawing.width, height / drawing.height)
    drawing.scale(scale, scale)
    renderPDF.draw(drawing, canvas, x + (width - drawing.width * scale) / 2, y + (height - drawing.height * scale) / 2)


def _comment_lines(text: str, font: str) -> list[str]:
    from reportlab.lib.utils import simpleSplit

    return simpleSplit(text or "", font, 9, (COMMENT_WIDTH - 60) / 20) if text else []


def write_pdf(doc: dict, target: Path | str, logo: Path | str | None = None) -> Path:
    """Draw the invoice as a PDF file at `target` (written to a temporary file first, then renamed, so a
    failed run leaves no half file). `logo` is the optional company logo, a .png or .svg file
    (settings.logo_path())."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas

    target = Path(target)
    tmp = target.with_name(target.name + ".tmp")
    fonts = _fonts()
    canvas = Canvas(str(tmp), pagesize=A4)
    canvas.setTitle(f"{PRINT_LABELS['title']} {padded(doc['invoice_id'], 5)}")
    canvas.setCreator("Wine Inventory Manager")
    page = _Page(canvas, fonts)
    show_prices = not doc["hide_subtotals"]
    L = PRINT_LABELS

    def page_footer() -> None:
        top = page.body_end
        page.rule(top + 60)
        address, bank, terms = doc["texts"]
        page.text(top + 225, 885, 9135, address, size=9, align="centre", colour=LABEL_COLOUR)
        page.text(top + 615, 2445, 6405, bank, size=9, align="centre", colour=LABEL_COLOUR)
        page.text(top + 960, 4095, 3195, terms, size=8, colour=LABEL_COLOUR)

    cursor = PAGE_TOP_MARGIN

    def room(height: float) -> float:
        """The top of a band of `height`; starts a new page if the band does not fit (KeepTogether)."""
        nonlocal cursor
        if cursor + height > page.body_end and cursor > PAGE_TOP_MARGIN:
            page_footer()
            canvas.showPage()
            cursor = PAGE_TOP_MARGIN
        top = cursor
        cursor += height
        return top

    # Report header (first page only): the logo
    top = room(REPORT_HEADER_HEIGHT)
    if logo and Path(logo).is_file():
        box = (page.x(2664), page.y(top + 56 + 870), 5400 / 20, 870 / 20)       # x, y, width, height in points
        if Path(logo).suffix.lower() == ".svg":
            _draw_svg(canvas, logo, *box)
        else:
            canvas.drawImage(ImageReader(str(logo)), *box, preserveAspectRatio=True, anchor="c", mask="auto")

    # Invoice header (group header of the customer)
    top = room(INVOICE_HEADER_HEIGHT)
    page.text(top + 64, 120, 1470, L["invoice_id"], colour=LABEL_COLOUR)
    page.text(top + 56, 1814, 726, padded(doc["invoice_id"], 5))
    page.text(top + 390, 120, 1605, L["invoice_date"], colour=LABEL_COLOUR)
    page.text(top + 393, 1813, 1701, short_date(doc["invoice_date"]))
    page.text(top + 56, 8730, 1380, L["customer_id"], colour=LABEL_COLOUR)
    page.text(top + 60, 10158, 531, padded(doc["customer_id"], 4), align="right")
    page.text(top + 345, 7173, 3516, doc["customer_name"], align="right", cut=True)
    page.text(top + 630, 7155, 2901, doc["city"], align="right", cut=True)
    page.text(top + 630, 10128, 561, whole(doc["postal_code"]), align="right")
    page.text(top + 915, 7155, 3516, doc["address"], align="right", cut=True)
    page.rule(top + 1417)
    page.text(top + 1474, 165, 513, L["quantity"], size=8, colour=LABEL_COLOUR)
    page.text(top + 1485, 795, 1020, L["wine"], size=8, colour=LABEL_COLOUR)
    page.text(top + 1474, 6111, 558, L["vintage"], size=8, align="right", colour=LABEL_COLOUR)
    if show_prices:
        page.text(top + 1474, 6872, 1575, L["unit_price"], size=8, align="right", colour=LABEL_COLOUR)
    page.text(top + 1474, 9924, 765, L["line_total"], size=8, align="right", colour=LABEL_COLOUR)
    page.rule(top + 1815)

    # The lines, grouped by wine house
    for group in doc["groups"]:
        top = room(HOUSE_HEIGHT + DETAIL_HEIGHT)    # a house name never stands alone at the foot of a page
        cursor = top + HOUSE_HEIGHT
        page.text(top + 60, 165, 1701 * 3, group["house"], style="italic")   # Access cut the name at 1701 twips; here it is whole
        for line in group["lines"]:
            top = room(DETAIL_HEIGHT)
            page.text(top + 4, 166, 576, whole(line["quantity"]), align="right")
            page.text(top, 1020, 4821, line["text"], cut=True)
            page.text(top + 4, 5943, 726, whole(line["vintage"]), align="right")
            if show_prices:
                page.text(top, 6746, 1701, "" if line["unit_price"] is None else kr(line["unit_price"]), align="right")
                page.text(top + 4, 8478, 2211, kr(line["line_total"]), align="right")

    # Report footer: the totals and the invoice comment (kept together, it grows with the comment)
    comment = _comment_lines(doc["comment"], fonts["regular"])
    height = max(REPORT_FOOTER_HEIGHT, COMMENT_TOP + 60 + len(comment) * 9 * 24)
    top = room(height)
    page.text(top + 345, 225, 577, whole(doc["total_quantity"]), align="right")
    page.text(top + 340, 850, 684, L["total_quantity"], colour=LABEL_COLOUR)
    if doc["adjustment"]:                   # Access hides the adjustment (and its label) when it is 0
        page.text(top + 345, 6936, 1164, L["adjustment"], colour=LABEL_COLOUR)
        page.text(top + 345, 8988, 1701, kr(doc["adjustment"]), align="right", style="italic")
    page.text(top + 735, 6930, 1605, L["total_incl_vat"], size=11, colour=LABEL_COLOUR)
    page.text(top + 735, 8589, 2100, kr(doc["total_incl_vat"]), size=11, align="right", style="bold",
              underline=True)
    page.text(top + 1245, 6930, 1470, L["vat"], size=9, colour=LABEL_COLOUR)
    page.text(top + 1245, 8733, 1956, kr(doc["vat"]), size=9, align="right")
    page.text(top + 1530, 6930, 1530, L["total_ex_vat"], size=9, colour=LABEL_COLOUR)
    page.text(top + 1530, 8733, 1956, kr(doc["total_ex_vat"]), size=9, align="right")
    for n, text in enumerate(comment):
        page.text(top + COMMENT_TOP + n * 9 * 24, COMMENT_LEFT, COMMENT_WIDTH, text, size=9)

    page_footer()
    canvas.save()
    try:
        os.replace(tmp, target)      # fails when the old PDF is open in a viewer that locks it
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return target
