#!/usr/bin/env python3
"""Unified ingestion & living heritage preprocessor CLI for Stage 1 extraction.

Ingests heterogeneous raw cultural heritage inputs (.pdf, .csv, .tsv, .xlsx, .json),
normalizes OCR noise, and scans for living heritage vocabulary (Guthis, styles, eras)
to prepare structured candidate payloads for LinkML Container extraction.

Usage:
  python ingest_raw.py <input-file> [--out preprocessed.json] [--chunk-size 800]
"""
import argparse
import json
import sys
from pathlib import Path

# Relative imports or local scripts directory
try:
    from ingest_tabular import ingest_csv, ingest_excel, ingest_json
    from ingest_pdf import ingest_pdf
    from recognize_heritage import scan_text_for_heritage_entities
except ImportError:
    from skills._01_heritage_extract.scripts.ingest_tabular import ingest_csv, ingest_excel, ingest_json
    from skills._01_heritage_extract.scripts.ingest_pdf import ingest_pdf
    from skills._01_heritage_extract.scripts.recognize_heritage import scan_text_for_heritage_entities


def process_raw_file(file_path: Path, max_words_per_chunk: int = 800) -> dict:
    """Ingest raw file and augment items with living heritage entity tags."""
    p = Path(file_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p}")

    suffix = p.suffix.lower()

    if suffix == ".pdf":
        raw_result = ingest_pdf(p, max_words_per_chunk=max_words_per_chunk)
        metadata = {
            "source_file": raw_result["source_file"],
            "format": "pdf",
            "page_count": raw_result["page_count"],
            "is_scanned_image_only": raw_result["is_scanned_image_only"],
            "diagnostic_warning": raw_result.get("diagnostic_warning")
        }
        items = []
        for ch in raw_result.get("chunks", []):
            tags = scan_text_for_heritage_entities(ch["text"])
            items.append({
                "chunk_id": ch["chunk_id"],
                "text": ch["text"],
                "word_count": ch["word_count"],
                "heritage_tags": tags
            })

    elif suffix in (".csv", ".tsv"):
        records, metadata = ingest_csv(p)
        items = []
        for rec in records:
            narrative_text = " ".join(str(v) for v in rec.get("narrative", {}).values())
            tags = scan_text_for_heritage_entities(narrative_text)
            items.append({**rec, "heritage_tags": tags})

    elif suffix == ".xlsx":
        records, metadata = ingest_excel(p)
        items = []
        for rec in records:
            narrative_text = " ".join(str(v) for v in rec.get("narrative", {}).values())
            tags = scan_text_for_heritage_entities(narrative_text)
            items.append({**rec, "heritage_tags": tags})

    elif suffix == ".json":
        records, metadata = ingest_json(p)
        items = []
        for rec in records:
            narrative_text = " ".join(str(v) for v in rec.get("narrative", {}).values())
            tags = scan_text_for_heritage_entities(narrative_text)
            items.append({**rec, "heritage_tags": tags})

    else:
        raise ValueError(f"Unsupported file format '{suffix}'. Supported: .pdf, .csv, .tsv, .xlsx, .json")

    # Aggregate discovered living heritage entities across all items
    total_guthis = sum(len(it.get("heritage_tags", {}).get("guthis", [])) for it in items)
    total_styles = sum(len(it.get("heritage_tags", {}).get("architectural_styles", [])) for it in items)
    total_dates = sum(len(it.get("heritage_tags", {}).get("dates", [])) for it in items)
    total_traditions = sum(len(it.get("heritage_tags", {}).get("traditions", [])) for it in items)

    summary = {
        "total_items": len(items),
        "discovered_guthis": total_guthis,
        "discovered_architectural_styles": total_styles,
        "discovered_calendar_dates": total_dates,
        "discovered_traditions": total_traditions
    }

    return {
        "metadata": metadata,
        "summary": summary,
        "items": items
    }


def main():
    ap = argparse.ArgumentParser(description="Ingest and preprocess raw cultural heritage materials.")
    ap.add_argument("input_file", help="Path to raw input file (.pdf, .csv, .tsv, .xlsx, .json)")
    ap.add_argument("--out", default=None, help="Path to write preprocessed JSON payload")
    ap.add_argument("--chunk-size", type=int, default=800, help="Max words per chunk for PDF files")
    args = ap.parse_args()

    payload = process_raw_file(Path(args.input_file), max_words_per_chunk=args.chunk_size)

    meta = payload["metadata"]
    summ = payload["summary"]

    print(f"Ingested '{meta['source_file']}' ({meta['format']}): {summ['total_items']} item(s)/chunk(s)")
    if meta.get("diagnostic_warning"):
        print(f"WARNING: {meta['diagnostic_warning']}")
    print(f"Living heritage candidate tags: {summ['discovered_guthis']} Guthi(s), "
          f"{summ['discovered_architectural_styles']} style(s), {summ['discovered_calendar_dates']} date(s).")

    serialized = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(serialized, encoding="utf-8")
        print(f"Output saved to: {args.out}")
    else:
        print(serialized)

    return 0


if __name__ == "__main__":
    sys.exit(main())
