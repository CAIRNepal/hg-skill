import sys
from pathlib import Path
import pytest
from pypdf import PdfWriter

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "01_heritage-extract" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from ingest_pdf import (
    normalize_ocr_text,
    chunk_document_text,
    ingest_pdf
)


def test_normalize_ocr_text():
    raw_ocr = (
        "The Nyatapola tem-\n"
        "ple was consecrated by King Bhu-\n"
        "patindra Malla in NS 822.\n\n"
        "   14   \n\n"
        "It is dedicated to Siddhi Lakshmi."
    )
    cleaned = normalize_ocr_text(raw_ocr)
    assert "temple" in cleaned
    assert "tem-" not in cleaned
    assert "Bhupatindra" in cleaned
    assert "14" not in cleaned
    assert "Siddhi Lakshmi" in cleaned


def test_chunk_document_text():
    paragraphs = [
        "Paragraph one about Nyatapola temple and its architecture in Bhaktapur.",
        "Paragraph two about Bhairavnath temple located on the south side.",
        "Paragraph three about the Siddhi Lakshmi Guthi and festival rituals.",
        "Paragraph four about the Bisket Jatra festival chariot procession."
    ]
    long_text = "\n\n".join(paragraphs)
    # Target chunk size of roughly 20 words
    chunks = chunk_document_text(long_text, max_words=20)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk["text"].split()) <= 35


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
    assert "OCR" in result["diagnostic_warning"]
    assert len(result["chunks"]) == 0
