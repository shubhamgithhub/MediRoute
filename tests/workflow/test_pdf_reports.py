"""Report upload: text PDFs are read; locked, scanned or damaged files are reported per file with a
plain reason and never sink the other files (OCR is out of scope)."""
import pymupdf
import pytest

from mediroute.specialty_routing.extraction.pdf_parser import (
    REASON_BROKEN, REASON_PASSWORD, REASON_SCAN, PDFParser)

REPORT = "HISTOPATHOLOGY: Right breast lump. DIAGNOSIS: Invasive ductal carcinoma, grade 2."


def text_pdf(text: str = REPORT, password: str | None = None) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 72), text, fontsize=10)
    if password:
        data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password + "x")
    else:
        data = doc.tobytes()
    doc.close()
    return data


def scanned_pdf() -> bytes:
    """Image-only page: what a phone scan looks like to the parser."""
    src = pymupdf.open(stream=text_pdf(), filetype="pdf")
    pix = src[0].get_pixmap(dpi=72)
    out = pymupdf.open()
    out.new_page().insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pix)
    return out.tobytes()


@pytest.fixture(scope="module")
def parser():
    return PDFParser()


def test_text_pdf_is_read(parser):
    result = parser.parse_pdf_bytes(text_pdf(), "biopsy.pdf")
    assert result["status"] == "success" and "invasive ductal carcinoma" in result["text"].lower()


def test_password_protected_pdf_is_an_error_with_a_reason_not_a_crash(parser):
    result = parser.parse_pdf_bytes(text_pdf(password="1234"), "locked.pdf")
    assert result["status"] == "error" and result["reason"] == REASON_PASSWORD


def test_scanned_pdf_is_reported_as_a_scan(parser):
    result = parser.parse_pdf_bytes(scanned_pdf(), "scan.pdf")
    assert result["status"] == "needs_ocr" and result["reason"] == REASON_SCAN


def test_damaged_pdf_is_an_error_with_a_reason(parser):
    result = parser.parse_pdf_bytes(b"%PDF-1.7\nthis is not really a pdf", "broken.pdf")
    assert result["status"] == "error" and result["reason"] == REASON_BROKEN


def test_one_unreadable_file_does_not_sink_the_others(parser):
    summary = parser.parse_multiple_pdfs([("biopsy.pdf", text_pdf()), ("locked.pdf", text_pdf(password="1")),
                                          ("scan.pdf", scanned_pdf())])
    assert summary["overall_status"] == "partial_success"
    assert "invasive ductal carcinoma" in summary["combined_text"].lower()
    assert summary["unreadable_files"] == [{"filename": "locked.pdf", "reason": REASON_PASSWORD},
                                           {"filename": "scan.pdf", "reason": REASON_SCAN}]


def test_all_readable_means_nothing_to_report(parser):
    assert parser.parse_multiple_pdfs([("a.pdf", text_pdf())])["unreadable_files"] == []
