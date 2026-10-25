import sys
from pathlib import Path
import pytest
from pypdf import PdfWriter

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "01_heritage-extract" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from ingest_pdf import (
    normalize_ocr_text,
    strip_running_headers_and_footers,
    chunk_pages_with_provenance,
    ingest_pdf
)


def test_normalize_ocr_text_conservative_dehyphenation():
    raw_ocr = (
        "The Newar-\n"
        "Buddhist shrine was consecrated in 1702-\n"
        "1750 CE. An ancient tem-\n"
        "ple with ar-\n"
        "chitectural excellence.\n\n"
        "   14   \n\n"
        "Founded in\n1702\nby the king."
    )
    cleaned = normalize_ocr_text(raw_ocr)
    # Lowercase hyphenated words are rejoined
    assert "temple" in cleaned
    assert "architectural" in cleaned
    # Proper nouns and year ranges keep hyphen
    assert "Newar-Buddhist" in cleaned
    assert "1702-1750" in cleaned
    # Standalone page number 14 is stripped
    lines = [line.strip() for line in cleaned.splitlines()]
    assert "14" not in lines
    # Standalone year 1702 is preserved
    assert "1702" in lines


def test_strip_running_headers_and_footers():
    pages = [
        {"page_number": 1, "text": "ARCHAEOLOGICAL REPORT 2019\nContent of page 1.\nDEPARTMENT OF ARCHAEOLOGY"},
        {"page_number": 2, "text": "ARCHAEOLOGICAL REPORT 2019\nContent of page 2.\nDEPARTMENT OF ARCHAEOLOGY"},
        {"page_number": 3, "text": "ARCHAEOLOGICAL REPORT 2019\nContent of page 3.\nDEPARTMENT OF ARCHAEOLOGY"}
    ]
    cleaned = strip_running_headers_and_footers(pages)
    for p in cleaned:
        assert "ARCHAEOLOGICAL REPORT 2019" not in p["text"]
        assert "DEPARTMENT OF ARCHAEOLOGY" not in p["text"]
        assert "Content of page" in p["text"]


def test_chunk_pages_with_provenance():
    pages = [
        {"page_number": 1, "text": "Page one text describes Nyatapola in Bhaktapur.\n" * 15},
        {"page_number": 2, "text": "Page two text describes Bhairavnath temple.\n" * 15},
        {"page_number": 3, "text": "Page three text describes Siddhi Lakshmi Guthi.\n" * 15}
    ]
    chunks = chunk_pages_with_provenance(pages, max_words=60)
    assert len(chunks) >= 2
    for c in chunks:
        assert "start_page" in c
        assert "end_page" in c
        assert "page_range" in c
        assert c["start_page"] <= c["end_page"]
        assert c["word_count"] <= 120


def test_ingest_scanned_blank_pdf(tmp_path):
    pdf_path = tmp_path / "scanned_doc.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_blank_page(width=72, height=72)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    result = ingest_pdf(pdf_path)
    assert result["is_scanned_image_only"] is True
    assert result["page_count"] == 2
    assert result["scanned_pages"] == [1, 2]
    assert "OCR" in result["diagnostic_warning"]
    assert len(result["chunks"]) == 0
