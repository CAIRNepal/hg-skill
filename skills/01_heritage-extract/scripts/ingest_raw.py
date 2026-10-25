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

# Ensure local script directory and common skills directory are on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[3]
COMMON_DIR = REPO_ROOT / "skills" / "common"
for d in (SCRIPTS_DIR, COMMON_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from ingest_tabular import ingest_csv, ingest_excel, ingest_json
from ingest_pdf import ingest_pdf
from recognize_heritage import scan_text_for_heritage_entities

try:
    from run_workspace import RunWorkspace
except ImportError:
    RunWorkspace = None


def _extract_all_text(rec: dict) -> str:
    """Extract unique text content from structured and narrative fields for heritage tagging."""
    parts = []
    seen = set()
    for container in (rec.get("structured", {}), rec.get("narrative", {})):
        for v in container.values():
            if isinstance(v, str):
                s = v.strip()
                if s and s not in seen:
                    parts.append(s)
                    seen.add(s)
    if "name" in rec and rec["name"]:
        name_str = str(rec["name"]).strip()
        if name_str not in seen:
            parts.append(name_str)
            seen.add(name_str)
    return " ".join(parts)


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
            "scanned_pages": raw_result.get("scanned_pages", []),
            "diagnostic_warning": raw_result.get("diagnostic_warning")
        }
        items = []
        for ch in raw_result.get("chunks", []):
            tags = scan_text_for_heritage_entities(ch["text"])
            items.append({
                "chunk_id": ch["chunk_id"],
                "start_page": ch.get("start_page"),
                "end_page": ch.get("end_page"),
                "page_range": ch.get("page_range"),
                "text": ch["text"],
                "word_count": ch["word_count"],
                "heritage_tags": tags
            })

    elif suffix in (".csv", ".tsv", ".xlsx", ".json"):
        if suffix in (".csv", ".tsv"):
            records, metadata = ingest_csv(p)
        elif suffix == ".xlsx":
            records, metadata = ingest_excel(p)
        else:
            records, metadata = ingest_json(p)

        items = []
        for rec in records:
            combined_text = _extract_all_text(rec)
            tags = scan_text_for_heritage_entities(combined_text)
            items.append({**rec, "heritage_tags": tags})

    else:
        raise ValueError(f"Unsupported file format '{suffix}'. Supported: .pdf, .csv, .tsv, .xlsx, .json")

    # Aggregate discovered living heritage entities across all items
    total_guthis = sum(len(it.get("heritage_tags", {}).get("guthis", [])) for it in items)
    total_styles = sum(len(it.get("heritage_tags", {}).get("architectural_styles", [])) for it in items)
    total_dates = sum(len(it.get("heritage_tags", {}).get("dates", [])) for it in items)
    total_eras = sum(len(it.get("heritage_tags", {}).get("eras", [])) for it in items)
    total_traditions = sum(len(it.get("heritage_tags", {}).get("traditions", [])) for it in items)

    summary = {
        "total_items": len(items),
        "discovered_guthis": total_guthis,
        "discovered_architectural_styles": total_styles,
        "discovered_calendar_dates": total_dates,
        "discovered_eras": total_eras,
        "discovered_traditions": total_traditions
    }

    return {
        "metadata": metadata,
        "summary": summary,
        "items": items
    }


def main():
    # Configure UTF-8 stdout if supported by the console stream
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="Ingest and preprocess raw cultural heritage materials.")
    ap.add_argument("input_file", help="Path to raw input file (.pdf, .csv, .tsv, .xlsx, .json)")
    ap.add_argument("--out", default=None, help="Path to write preprocessed JSON payload")
    ap.add_argument("--run-dir", default=None, help="Path to pipeline run directory (auto-created if omitted and --out not set)")
    ap.add_argument("--chunk-size", type=int, default=800, help="Max words per chunk for PDF files")
    args = ap.parse_args()

    # Determine if RunWorkspace should be used
    ws = None
    target_out = None
    if args.run_dir or (not args.out and RunWorkspace is not None):
        ws = RunWorkspace.init(args.input_file, run_dir=args.run_dir)
        target_out = ws.artifact_path(0)
    elif args.out:
        target_out = Path(args.out)

    if ws:
        ws.record_stage_start(0, "ingest", {"command": "ingest_raw.py", "input_file": str(args.input_file)})

    try:
        payload = process_raw_file(Path(args.input_file), max_words_per_chunk=args.chunk_size)
    except Exception as e:
        if ws:
            ws.record_stage_finish(0, "ingest", status="failed", error=str(e))
        print(f"Error: {e}", file=sys.stderr)
        return 1

    meta = payload["metadata"]
    summ = payload["summary"]

    summary_msg = (
        f"Ingested '{meta['source_file']}' ({meta['format']}): {summ['total_items']} item(s)/chunk(s)\n"
    )
    if meta.get("diagnostic_warning"):
        summary_msg += f"WARNING: {meta['diagnostic_warning']}\n"
    summary_msg += (
        f"Living heritage candidate tags: {summ['discovered_guthis']} Guthi(s), "
        f"{summ['discovered_architectural_styles']} style(s), {summ['discovered_calendar_dates']} date(s), "
        f"{summ['discovered_eras']} era(s), {summ['discovered_traditions']} tradition(s)."
    )

    serialized = json.dumps(payload, indent=2, ensure_ascii=False)

    if target_out:
        target_out.parent.mkdir(parents=True, exist_ok=True)
        target_out.write_text(serialized, encoding="utf-8")
        if ws:
            ws.record_stage_finish(0, "ingest", status="success", metrics=summ)
            print(f"Pipeline run directory: {ws.run_dir}")
        print(summary_msg)
        print(f"Output saved to: {target_out}")
    else:
        print(summary_msg)
        try:
            print(serialized)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(serialized.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
