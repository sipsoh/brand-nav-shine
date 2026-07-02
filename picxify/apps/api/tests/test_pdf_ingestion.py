"""PDF table extraction: digital text-layer tables, multi-page recombination,
and the OCR fallback for scanned pages."""

from io import BytesIO

import pytest
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Image as RLImage
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from app.services.normalization import normalize_table
from app.services.parser import add_union_candidates, count_pdf_pages, parse_file, parse_pdf


def pdf_with_table(rows: list[list], repeat_header: bool = False) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    table = Table(rows, repeatRows=1 if repeat_header else 0)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    doc.build([table])
    return buffer.getvalue()


def scanned_image_pdf(width=1200, height=500) -> bytes:
    """A PDF page holding only a rasterized image — no text layer at all,
    the shape of a scanned document. Columns are genuinely x-separated so
    the OCR column-clustering has real structure to find."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    rows = [("Region", "Revenue"), ("West", "1200"), ("East", "980"), ("South", "1450")]
    for i, (left_cell, right_cell) in enumerate(rows):
        y = 40 + i * 60
        draw.text((60, y), left_cell, fill="black", font=font)
        draw.text((600, y), right_cell, fill="black", font=font)
    image_buffer = BytesIO()
    img.save(image_buffer, format="PNG")
    image_buffer.seek(0)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    doc.build([RLImage(image_buffer, width=500, height=500 * height // width)])
    return buffer.getvalue()


def test_digital_pdf_table_extracted():
    rows = [["Region", "Month", "Revenue"]]
    for month in ["Jan 2026", "Feb 2026"]:
        for region in ["West", "East"]:
            rows.append([region, month, "$1,200.00"])
    data = pdf_with_table(rows)
    tables = parse_file("report.pdf", data)
    assert len(tables) == 1
    df = tables[0].dataframe
    assert list(df.columns) == ["Region", "Month", "Revenue"]
    assert len(df) == 4
    kinds = {n.finding_type for n in tables[0].notes}
    assert "table_from_pdf" in kinds


def test_pdf_values_coerce_through_normalization():
    rows = [["Item", "Cost"], ["Widget", "$1,250.00"], ["Gadget", "$980.50"], ["Gizmo", "$430.00"]]
    data = pdf_with_table(rows)
    tables = parse_file("costs.pdf", data)
    normalized = normalize_table(tables[0].dataframe)
    assert normalized.dataframe["Cost"].tolist() == pytest.approx([1250.0, 980.5, 430.0])
    assert normalized.type_hints.get("Cost") == "currency"


def test_multi_page_pdf_table_recombines_via_union():
    header = ["Order ID", "Customer", "Amount"]
    rows = [header] + [[f"O{i}", f"Cust {i % 10}", f"${100 + i}.00"] for i in range(60)]
    data = pdf_with_table(rows, repeat_header=True)
    assert count_pdf_pages(data) >= 2

    tables = parse_file("orders.pdf", data)
    assert len(tables) >= 2  # one per page, all page-labeled

    combined_set = add_union_candidates(tables)
    combined = [t for t in combined_set if t.name.startswith("Combined")]
    assert len(combined) == 1
    assert combined[0].dataframe.shape[0] == 60
    assert "Page" in combined[0].dataframe.columns


def test_pdf_page_union_requires_only_two_not_three():
    # PDF pages union more eagerly than Excel sheets (2, not 3) since a page
    # break is an extraction artifact, not a deliberate split.
    header = ["A", "B"]
    rows = [header, ["1", "2"], ["3", "4"]]
    data = pdf_with_table(rows)
    tables = parse_file("two_row.pdf", data)
    assert len(tables) == 1  # a single small table, nothing to union


def test_scanned_pdf_with_no_ocr_available_falls_back_gracefully(monkeypatch):
    # Simulate an environment without tesseract: OCR should be skipped, not
    # crash, and the caller sees "no tables" rather than an exception.
    import app.services.parser as parser_module

    data = scanned_image_pdf()
    monkeypatch.setattr(parser_module, "_ocr_available", lambda: False)
    tables = parser_module.parse_pdf_with_ocr("scan.pdf", data)
    assert tables == []


def test_scanned_pdf_produces_zero_tables_from_digital_extraction():
    data = scanned_image_pdf()
    assert parse_pdf("scan.pdf", data) == []
