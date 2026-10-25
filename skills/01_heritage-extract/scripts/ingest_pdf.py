#!/usr/bin/env python3
"""PDF document ingestion and OCR text normalization engine.

Extracts text page-by-page from cultural heritage PDF survey reports,
rejoins OCR line-break hyphenations, strips solitary page numbers,
and chunks documents into manageable sections for LinkML Container extraction.
"""
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

from pypdf import PdfReader


def normalize_ocr_text(text: str) -> str:
    """Normalize OCR text noise and formatting artifacts.

    - Reconnects hyphenated word breaks across newlines (e.g., 'tem-\nple' -> 'temple').
    - Removes solitary page numbers (e.g., '\n   14   \n').
    - Normalizes Unicode representations to NFC while preserving Devanagari.
    - Cleans irregular whitespace and excess blank lines.
    """
    if not text:
        return ""

    # Normalize Unicode
    text = unicodedata.normalize("NFC", text)

    # Rejoin words broken across line endings with hyphens
    # Matches a word ending with a hyphen, optional spaces, newline, optional spaces, and the rest of the word
    text = re.sub(r"(\b\w+)[-‐‑⁃]\s*\n\s*(\w+\b)", r"\1\2", text)

    # Strip solitary page numbers or 'Page 12' lines
    text = re.sub(r"(?im)^\s*(?:page\s*)?\d+\s*$", "", text)

    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Clean whitespace around lines
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def chunk_document_text(text: str, max_words: int = 800) -> List[Dict[str, Any]]:
    """Chunk document text into coherent sections respecting paragraph boundaries."""
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current_paras: List[str] = []
    current_word_count = 0

    for para in paragraphs:
        para_words = len(para.split())
        if current_word_count + para_words > max_words and current_paras:
            chunk_body = "\n\n".join(current_paras)
            chunks.append({
                "chunk_id": f"chunk-{len(chunks) + 1:03d}",
                "text": chunk_body,
                "word_count": current_word_count
            })
            current_paras = [para]
            current_word_count = para_words
        else:
            current_paras.append(para)
            current_word_count += para_words

    if current_paras:
        chunk_body = "\n\n".join(current_paras)
        chunks.append({
            "chunk_id": f"chunk-{len(chunks) + 1:03d}",
            "text": chunk_body,
            "word_count": current_word_count
        })

    return chunks


def ingest_pdf(file_path: Path, max_words_per_chunk: int = 800) -> Dict[str, Any]:
    """Ingest a PDF file and return clean text pages, chunks, and metadata."""
    p = Path(file_path)
    reader = PdfReader(p)
    page_count = len(reader.pages)

    pages_text = []
    total_raw_chars = 0

    for idx, page in enumerate(reader.pages):
        raw_text = page.extract_text() or ""
        total_raw_chars += len(raw_text.strip())
        cleaned_page = normalize_ocr_text(raw_text)
        pages_text.append({
            "page_number": idx + 1,
            "raw_text": raw_text,
            "text": cleaned_page
        })

    # Check for image-only scanned PDFs
    is_scanned_image_only = (total_raw_chars == 0 or (total_raw_chars / max(1, page_count)) < 15)

    full_cleaned_text = "\n\n".join(p["text"] for p in pages_text if p["text"]).strip()
    chunks = chunk_document_text(full_cleaned_text, max_words=max_words_per_chunk) if not is_scanned_image_only else []

    diagnostic_warning = None
    if is_scanned_image_only:
        diagnostic_warning = (
            f"Scanned image-only PDF detected ({page_count} page(s), 0 extractable text characters). "
            "No OCR text layer found. Please process this file with an OCR tool "
            "(e.g., ocrmypdf, Tesseract with 'nep+eng' models, or Surya OCR) before extraction."
        )

    return {
        "source_file": str(p.name),
        "format": "pdf",
        "page_count": page_count,
        "is_scanned_image_only": is_scanned_image_only,
        "diagnostic_warning": diagnostic_warning,
        "pages": pages_text,
        "full_text": full_cleaned_text,
        "chunks": chunks
    }
