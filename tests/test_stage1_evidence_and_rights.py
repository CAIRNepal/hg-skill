"""Tests for Evidence Spans and Cultural Rights Sensitivity Metadata (Ticket 3 / #39).

Verifies:
1. Evidence Spans:
   - Tabular extraction (CSV, XLSX, JSON) records evidence_span with row_index, column names, and column values.
   - PDF extraction records evidence_span with page number, paragraph_span, and block_span.
2. Cultural Rights & Sensitivity Metadata:
   - Records contain sensitivity field with allowed values: 'public', 'restricted-sacred', 'guthi-internal'.
   - Defaults to 'public'.
   - Records contain license field (e.g., 'CC-BY-4.0', 'CC0').
   - Rejects invalid sensitivity tiers with ValueError.
3. Run Workspace & Manifest Integration:
   - Manifest records summary of evidence spans count and sensitivity breakdown.
4. Sensitive Data Guard:
   - Entities marked 'restricted-sacred' or 'guthi-internal' have sensitivity flags preserved.
   - Manifest flags run for restricted distribution (restricted_distribution=True).
"""
import csv
import json
import sys
from pathlib import Path
import pytest
import openpyxl
from pypdf import PdfWriter

# Ensure scripts and common directories are on path
REPO_ROOT = Path(__file__).resolve().parent.parent
EXTRACT_SCRIPTS = REPO_ROOT / "skills" / "01_heritage-extract" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"

for d in (EXTRACT_SCRIPTS, COMMON_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from ingest_tabular import (
    ingest_csv,
    ingest_excel,
    ingest_json,
    partition_record,
    ALLOWED_SENSITIVITIES,
    validate_sensitivity,
)
from ingest_pdf import (
    ingest_pdf,
    chunk_pages_with_provenance,
)
from run_workspace import RunWorkspace


# -------------------------------------------------------------------------
# 1. Evidence Spans in Tabular Extraction
# -------------------------------------------------------------------------

def test_tabular_csv_evidence_span(tmp_path):
    csv_file = tmp_path / "monuments.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "district", "description"])
        writer.writeheader()
        writer.writerow({
            "id": "mon-001",
            "name": "Nyatapola Temple",
            "district": "Bhaktapur",
            "description": "Five-roofed pagoda built in 1702 CE."
        })
        writer.writerow({
            "id": "mon-002",
            "name": "Bhairavnath Temple",
            "district": "Bhaktapur",
            "description": "Temple dedicated to Kashi Bhairav."
        })

    records, metadata = ingest_csv(csv_file)
    assert len(records) == 2

    # Check evidence_span presence and structure on first record
    rec1 = records[0]
    assert "evidence_span" in rec1
    span1 = rec1["evidence_span"]
    assert "row_index" in span1
    assert span1["row_index"] == 0
    assert "columns" in span1
    assert "name" in span1["columns"]
    assert "district" in span1["columns"]
    assert "column_values" in span1
    assert span1["column_values"]["id"] == "mon-001"
    assert span1["column_values"]["district"] == "Bhaktapur"

    # Check second record row_index
    span2 = records[1]["evidence_span"]
    assert span2["row_index"] == 1
    assert span2["column_values"]["id"] == "mon-002"


def test_tabular_excel_evidence_span(tmp_path):
    xlsx_file = tmp_path / "monuments.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sites"
    ws.append(["id", "name", "latitude", "longitude"])
    ws.append(["mon-101", "Changu Narayan", 27.716, 85.427])
    ws.append(["mon-102", "Pashupatinath", 27.710, 85.348])
    wb.save(xlsx_file)

    records, metadata = ingest_excel(xlsx_file)
    assert len(records) == 2
    assert records[0]["evidence_span"]["row_index"] == 0
    assert records[0]["evidence_span"]["column_values"]["name"] == "Changu Narayan"
    assert records[1]["evidence_span"]["row_index"] == 1
    assert records[1]["evidence_span"]["column_values"]["name"] == "Pashupatinath"


def test_tabular_json_evidence_span(tmp_path):
    json_file = tmp_path / "monuments.json"
    data = [
        {"id": "mon-201", "name": "Krishna Mandir", "city": "Patan"},
        {"id": "mon-202", "name": "Golden Temple", "city": "Patan"},
    ]
    json_file.write_text(json.dumps(data), encoding="utf-8")

    records, metadata = ingest_json(json_file)
    assert len(records) == 2
    assert records[0]["evidence_span"]["row_index"] == 0
    assert records[0]["evidence_span"]["column_values"]["city"] == "Patan"
    assert records[1]["evidence_span"]["row_index"] == 1


# -------------------------------------------------------------------------
# 2. Evidence Spans in PDF Extraction
# -------------------------------------------------------------------------

def test_pdf_evidence_span_chunking():
    pages = [
        {
            "page_number": 1,
            "text": "First paragraph on page one about Nyatapola.\n\nSecond paragraph on page one about Malla architecture."
        },
        {
            "page_number": 2,
            "text": "First paragraph on page two about Bhairavnath Guthi rituals.\n\nSecond paragraph on page two about chariot festival."
        }
    ]
    chunks = chunk_pages_with_provenance(pages, max_words=50)
    assert len(chunks) >= 1

    for ch in chunks:
        assert "evidence_span" in ch
        span = ch["evidence_span"]
        assert "page_number" in span or "start_page" in span
        assert "paragraph_span" in span
        assert "block_span" in span
        assert isinstance(span["paragraph_span"], (list, tuple))
        assert isinstance(span["block_span"], (list, tuple))
        assert len(span["paragraph_span"]) == 2
        assert len(span["block_span"]) == 2


# -------------------------------------------------------------------------
# 3. Cultural Rights & Sensitivity Metadata
# -------------------------------------------------------------------------

def test_sensitivity_allowed_values():
    assert "public" in ALLOWED_SENSITIVITIES
    assert "restricted-sacred" in ALLOWED_SENSITIVITIES
    assert "guthi-internal" in ALLOWED_SENSITIVITIES

    assert validate_sensitivity("public") == "public"
    assert validate_sensitivity("restricted-sacred") == "restricted-sacred"
    assert validate_sensitivity("guthi-internal") == "guthi-internal"
    assert validate_sensitivity(None) == "public"  # default fallback

    # Rejection of invalid sensitivity
    with pytest.raises(ValueError, match="Invalid sensitivity"):
        validate_sensitivity("secret")

    with pytest.raises(ValueError, match="Invalid sensitivity"):
        validate_sensitivity("confidential")


def test_tabular_record_sensitivity_and_license_defaults(tmp_path):
    csv_file = tmp_path / "public_items.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name"])
        writer.writeheader()
        writer.writerow({"id": "mon-1", "name": "Public Monument"})

    records, _ = ingest_csv(csv_file)
    assert len(records) == 1
    assert records[0]["sensitivity"] == "public"
    assert records[0]["license"] == "CC-BY-4.0"


def test_tabular_record_explicit_sensitivity_and_license(tmp_path):
    csv_file = tmp_path / "sacred_items.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "sensitivity", "license"])
        writer.writeheader()
        writer.writerow({
            "id": "mon-secret",
            "name": "Secret Agama Deity",
            "sensitivity": "restricted-sacred",
            "license": "CC0"
        })
        writer.writerow({
            "id": "guthi-ledger",
            "name": "Guthi Minutes",
            "sensitivity": "guthi-internal",
            "license": "CC-BY-4.0"
        })
        writer.writerow({
            "id": "mon-public",
            "name": "Public Stele",
            "sensitivity": "public",
            "license": "CC-BY-4.0"
        })

    records, _ = ingest_csv(csv_file)
    assert len(records) == 3
    assert records[0]["sensitivity"] == "restricted-sacred"
    assert records[0]["license"] == "CC0"
    assert records[1]["sensitivity"] == "guthi-internal"
    assert records[2]["sensitivity"] == "public"


def test_tabular_rejects_invalid_sensitivity_row(tmp_path):
    csv_file = tmp_path / "invalid_tier.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "sensitivity"])
        writer.writeheader()
        writer.writerow({"id": "mon-x", "name": "Test", "sensitivity": "top-secret"})

    with pytest.raises(ValueError, match="Invalid sensitivity"):
        ingest_csv(csv_file)


# -------------------------------------------------------------------------
# 4. Run Workspace & Manifest Integration
# -------------------------------------------------------------------------

def test_manifest_records_evidence_and_sensitivity_summary(tmp_path):
    ws = RunWorkspace.init(source_path="monuments.csv", run_dir=tmp_path / "run_ws")
    ws.record_stage_start(1, "extract")

    records = [
        {
            "id": "m1",
            "sensitivity": "public",
            "evidence_span": {"row_index": 0, "columns": ["id", "name"], "column_values": {"id": "m1"}}
        },
        {
            "id": "m2",
            "sensitivity": "public",
            "evidence_span": {"row_index": 1, "columns": ["id", "name"], "column_values": {"id": "m2"}}
        },
        {
            "id": "m3",
            "sensitivity": "restricted-sacred",
            "evidence_span": {"row_index": 2, "columns": ["id", "name"], "column_values": {"id": "m3"}}
        },
        {
            "id": "m4",
            "sensitivity": "guthi-internal",
            "evidence_span": {"row_index": 3, "columns": ["id", "name"], "column_values": {"id": "m4"}}
        },
    ]

    ws.record_evidence_and_rights(records)
    ws.record_stage_finish(1, "extract", status="success")

    manifest = ws.load_manifest()

    # Evidence spans count
    assert manifest["summary"]["evidence_spans_count"] == 4

    # Sensitivity breakdown
    breakdown = manifest["summary"]["sensitivity_breakdown"]
    assert breakdown["public"] == 2
    assert breakdown["restricted-sacred"] == 1
    assert breakdown["guthi-internal"] == 1

    # Restricted distribution guard flagged
    assert manifest["summary"]["restricted_distribution"] is True
    assert manifest["restricted_distribution"] is True


def test_manifest_public_only_not_restricted(tmp_path):
    ws = RunWorkspace.init(source_path="public.csv", run_dir=tmp_path / "run_pub")
    records = [
        {"id": "m1", "sensitivity": "public", "evidence_span": {"row_index": 0}},
        {"id": "m2", "sensitivity": "public", "evidence_span": {"row_index": 1}},
    ]
    ws.record_evidence_and_rights(records)

    manifest = ws.load_manifest()
    assert manifest["summary"]["evidence_spans_count"] == 2
    assert manifest["summary"]["sensitivity_breakdown"]["public"] == 2
    assert manifest["summary"]["sensitivity_breakdown"]["restricted-sacred"] == 0
    assert manifest["summary"]["sensitivity_breakdown"]["guthi-internal"] == 0
    assert manifest["summary"]["restricted_distribution"] is False
    assert manifest["restricted_distribution"] is False
