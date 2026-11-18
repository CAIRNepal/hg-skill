#!/usr/bin/env python3
"""PDF document ingestion and OCR text normalization engine.

Extracts text page-by-page from cultural heritage PDF survey reports,
rejoins OCR line-break hyphenations conservatively, strips running headers/footers,
preserves digit-only dates while removing page numbers, detects individual scanned pages,
and chunks documents with explicit page provenance and evidence spans.
"""
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader

ALLOWED_SENSITIVITIES = {"public", "restricted-sacred", "guthi-internal"}
DEFAULT_SENSITIVITY = "public"
DEFAULT_LICENSE = "CC-BY-4.0"


def validate_sensitivity(val: Optional[str]) -> str:
    """Validate cultural rights sensitivity tier."""
    if val is None:
        return DEFAULT_SENSITIVITY
    norm = str(val).strip().lower()
    if norm not in ALLOWED_SENSITIVITIES:
        raise ValueError(
            f"Invalid sensitivity '{val}'. Allowed values: {sorted(ALLOWED_SENSITIVITIES)}"
        )
    return norm


def normalize_ocr_text(text: str) -> str:
    """Normalize OCR text noise and formatting artifacts.

    - Reconnects hyphenated word breaks across newlines ONLY for split lowercase words (e.g. 'tem-\\nple' -> 'temple').
    - Preserves hyphenated proper nouns ('Newar-\\nBuddhist' -> 'Newar-Buddhist') and year ranges ('1702-\\n1750' -> '1702-1750').
    - Removes solitary page numbers (1-3 digits or 'Page N') without deleting isolated 4-digit calendar years.
    - Normalizes Unicode representations to NFC.
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)

    # 1. Hyphenation repairs:
    # 1a. Hyphenated year ranges or numbers: preserve hyphen (e.g. '1702-\n1750' -> '1702-1750')
    text = re.sub(r"(\b\d{1,4})[-‐‑⁃]\s*\n\s*(\d{1,4}\b)", r"\1-\2", text)

    # 1b. Hyphenated capitalized compounds: preserve hyphen (e.g. 'Newar-\nBuddhist' -> 'Newar-Buddhist')
    text = re.sub(r"(\b[A-Z][a-z]+)[-‐‑⁃]\s*\n\s*([A-Z][a-z]+\b)", r"\1-\2", text)

    # 1c. Genuine hyphenated word breaks in lowercase text: rejoin into single word (e.g. 'tem-\nple' -> 'temple')
    text = re.sub(r"(\b[a-zA-Z]+)[-‐‑⁃]\s*\n\s*([a-z]+\b)", r"\1\2", text)

    # 2. Page number stripping:
    # Strip standalone page numbers: '1' to '999', or 'Page 12', or '- 14 -'
    # Do NOT strip standalone 4-digit years (e.g. 1000-2099)
    text = re.sub(r"(?im)^\s*(?:page\s*)?[-–—]?\s*(?!1[0-9]{3}|20[0-9]{2})[1-9]\d{0,2}\s*[-–—]?\s*$", "", text)

    # 3. Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def strip_running_headers_and_footers(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect and remove repetitive running headers and footers across multi-page documents."""
    if len(pages) < 3:
        return pages

    top_lines = []
    bottom_lines = []

    for p in pages:
        lines = [line.strip() for line in p["text"].split("\n") if line.strip()]
        if lines:
            top_lines.extend(lines[:2])
            bottom_lines.extend(lines[-2:])

    threshold = max(2, int(len(pages) * 0.5))
    top_counts = Counter(top_lines)
    bottom_counts = Counter(bottom_lines)

    repetitive_headers = {line for line, count in top_counts.items() if count >= threshold and len(line) > 3}
    repetitive_footers = {line for line, count in bottom_counts.items() if count >= threshold and len(line) > 3}
    repetitive = repetitive_headers | repetitive_footers

    if not repetitive:
        return pages

    cleaned_pages = []
    for p in pages:
        raw_lines = p["text"].split("\n")
        filtered_lines = [
            line for line in raw_lines
            if line.strip() not in repetitive
        ]
        cleaned_text = "\n".join(filtered_lines).strip()
        cleaned_pages.append({**p, "text": cleaned_text})

    return cleaned_pages


def chunk_pages_with_provenance(
    pages: List[Dict[str, Any]],
    max_words: int = 800,
    source_file: Optional[str] = None,
    default_sensitivity: str = DEFAULT_SENSITIVITY,
    default_license: Optional[str] = DEFAULT_LICENSE,
) -> List[Dict[str, Any]]:
    """Chunk document text with explicit page range and paragraph/block span provenance."""
    # Break into atomic blocks with page and paragraph tracking:
    # list of (block_text, page_number, paragraph_idx, block_idx)
    blocks: List[Tuple[str, int, int, int]] = []
    global_para = 0

    for p in pages:
        page_num = p["page_number"]
        page_text = p.get("text", "").strip()
        if not page_text:
            continue
        raw_sections = page_text.split("\n\n")
        for sec in raw_sections:
            sec_clean = sec.strip()
            if not sec_clean:
                continue
            global_para += 1
            words = sec_clean.split()
            if len(words) > max_words:
                lines = sec_clean.split("\n")
                buf = []
                buf_words = 0
                sub_block = 0
                for line in lines:
                    line_clean = line.strip()
                    if not line_clean:
                        continue
                    l_words = len(line_clean.split())
                    if buf_words + l_words > max_words and buf:
                        sub_block += 1
                        blocks.append(("\n".join(buf), page_num, global_para, sub_block))
                        buf = [line_clean]
                        buf_words = l_words
                    else:
                        buf.append(line_clean)
                        buf_words += l_words
                if buf:
                    sub_block += 1
                    blocks.append(("\n".join(buf), page_num, global_para, sub_block))
            else:
                blocks.append((sec_clean, page_num, global_para, 1))

    chunks = []
    current_blocks: List[str] = []
    current_pages: List[int] = []
    current_paras: List[int] = []
    current_block_ids: List[int] = []
    current_word_count = 0

    def _build_chunk(c_blocks, c_pages, c_paras, c_bids, w_count) -> Dict[str, Any]:
        start_p = min(c_pages)
        end_p = max(c_pages)
        para_start = min(c_paras)
        para_end = max(c_paras)
        block_start = min(c_bids)
        block_end = max(c_bids)

        evidence_span: Dict[str, Any] = {
            "page_number": start_p,
            "start_page": start_p,
            "end_page": end_p,
            "page_range": [start_p, end_p],
            "paragraph_span": [para_start, para_end],
            "block_span": [block_start, block_end],
        }
        if source_file:
            evidence_span["source_file"] = source_file

        return {
            "chunk_id": f"chunk-{len(chunks) + 1:03d}",
            "start_page": start_p,
            "end_page": end_p,
            "page_range": [start_p, end_p],
            "text": "\n\n".join(c_blocks),
            "word_count": w_count,
            "evidence_span": evidence_span,
            "sensitivity": validate_sensitivity(default_sensitivity),
            "license": default_license,
        }

    for block_text, page_num, p_idx, b_idx in blocks:
        block_words = len(block_text.split())
        if current_word_count + block_words > max_words and current_blocks:
            chunks.append(_build_chunk(
                current_blocks, current_pages, current_paras, current_block_ids, current_word_count
            ))
            current_blocks = [block_text]
            current_pages = [page_num]
            current_paras = [p_idx]
            current_block_ids = [b_idx]
            current_word_count = block_words
        else:
            current_blocks.append(block_text)
            current_pages.append(page_num)
            current_paras.append(p_idx)
            current_block_ids.append(b_idx)
            current_word_count += block_words

    if current_blocks:
        chunks.append(_build_chunk(
            current_blocks, current_pages, current_paras, current_block_ids, current_word_count
        ))

    return chunks


def ingest_pdf(
    file_path: Path,
    max_words_per_chunk: int = 800,
    default_sensitivity: str = DEFAULT_SENSITIVITY,
    default_license: Optional[str] = DEFAULT_LICENSE,
) -> Dict[str, Any]:
    """Ingest a PDF file and return clean text pages, page-tracked chunks, and scanned page diagnostics."""
    p = Path(file_path)
    reader = PdfReader(p)
    page_count = len(reader.pages)

    pages_text = []
    scanned_pages = []

    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        raw_text = page.extract_text() or ""
        char_count = len(raw_text.strip())
        if char_count < 15:
            scanned_pages.append(page_num)

        cleaned_page = normalize_ocr_text(raw_text)

        # Break page text into paragraphs with local evidence spans
        paragraphs = []
        for p_idx, para in enumerate(cleaned_page.split("\n\n")):
            para_clean = para.strip()
            if para_clean:
                paragraphs.append({
                    "paragraph_index": p_idx + 1,
                    "text": para_clean,
                    "evidence_span": {
                        "page_number": page_num,
                        "paragraph_index": p_idx + 1,
                        "block_index": p_idx + 1,
                        "paragraph_span": [p_idx + 1, p_idx + 1],
                        "block_span": [p_idx + 1, p_idx + 1],
                        "source_file": str(p.name),
                    }
                })

        pages_text.append({
            "page_number": page_num,
            "raw_text": raw_text,
            "text": cleaned_page,
            "char_count": char_count,
            "is_scanned": page_num in scanned_pages,
            "paragraphs": paragraphs,
        })

    # Strip running headers and footers across pages
    pages_text = strip_running_headers_and_footers(pages_text)

    is_all_scanned = len(scanned_pages) == page_count
    full_cleaned_text = "\n\n".join(pg["text"] for pg in pages_text if pg["text"]).strip()

    chunks = chunk_pages_with_provenance(
        pages_text,
        max_words=max_words_per_chunk,
        source_file=str(p.name),
        default_sensitivity=default_sensitivity,
        default_license=default_license,
    ) if not is_all_scanned else []

    diagnostic_warning = None
    if is_all_scanned:
        diagnostic_warning = (
            f"Scanned image-only PDF detected ({page_count} page(s), 0 extractable text characters). "
            "No OCR text layer found. Please process this file with an OCR tool "
            "(e.g., ocrmypdf, Tesseract with 'nep+eng' models, or Surya OCR) before extraction."
        )
    elif scanned_pages:
        diagnostic_warning = (
            f"Partial scanned pages detected: page(s) {scanned_pages} have no text layer. "
            "Text from remaining pages was extracted successfully."
        )

    return {
        "source_file": str(p.name),
        "format": "pdf",
        "page_count": page_count,
        "is_scanned_image_only": is_all_scanned,
        "scanned_pages": scanned_pages,
        "diagnostic_warning": diagnostic_warning,
        "pages": pages_text,
        "full_text": full_cleaned_text,
        "chunks": chunks,
        "sensitivity": validate_sensitivity(default_sensitivity),
        "license": default_license,
    }
