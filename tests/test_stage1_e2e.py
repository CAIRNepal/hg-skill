import csv
import json
import subprocess
import sys
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "01_heritage-extract" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def test_ingest_raw_cli_csv(tmp_path):
    csv_file = tmp_path / "survey_monuments.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "district", "description"])
        writer.writeheader()
        writer.writerow({
            "id": "mon-201",
            "name": "Nyatapola Temple",
            "district": "Bhaktapur",
            "description": "Five-tiered pagoda built in NS 822. Managed by the local Si Guthi during festivals."
        })

    out_file = tmp_path / "preprocessed.json"
    res = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "ingest_raw.py"), str(csv_file), "--out", str(out_file)],
        capture_output=True,
        text=True
    )
    assert res.returncode == 0
    assert out_file.exists()

    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["metadata"]["format"] == "csv"
    assert len(payload["items"]) == 1

    item = payload["items"][0]
    assert item["id"] == "mon-201"
    assert item["structured"]["district"] == "Bhaktapur"
    tags = item["heritage_tags"]
    assert any(g["enum_value"] == "SiGuthi" for g in tags["guthis"])
    assert any(s["enum_value"] == "Pagoda" for s in tags["architectural_styles"])
    assert any(d["calendar_system"] == "NepalSambat" for d in tags["dates"])


def test_ingest_raw_tags_name_column(tmp_path):
    csv_file = tmp_path / "monuments_name_style.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name"])
        writer.writeheader()
        writer.writerow({
            "id": "m1",
            "name": "Nyatapola Pagoda"
        })

    out_file = tmp_path / "out.json"
    res = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "ingest_raw.py"), str(csv_file), "--out", str(out_file)],
        capture_output=True,
        text=True
    )
    assert res.returncode == 0
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    styles = payload["items"][0]["heritage_tags"]["architectural_styles"]
    assert len(styles) == 1
    assert styles[0]["enum_value"] == "Pagoda"


def test_ingest_raw_devanagari_and_missing_file(tmp_path):
    # Test missing file error exit code
    missing = tmp_path / "nonexistent.pdf"
    res_missing = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "ingest_raw.py"), str(missing)],
        capture_output=True,
        text=True
    )
    assert res_missing.returncode == 1
    assert "Error:" in res_missing.stderr
    assert "Traceback" not in res_missing.stderr

    # Test Devanagari text processing
    dev_csv = tmp_path / "devanagari.csv"
    with open(dev_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "description"])
        writer.writeheader()
        writer.writerow({
            "id": "m2",
            "name": "न्यातपोल मन्दिर",
            "description": "पाँचतले प्यागोडा शैलीको मन्दिर"
        })

    res_dev = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "ingest_raw.py"), str(dev_csv)],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )
    assert res_dev.returncode == 0


def test_validate_extraction_rejects_non_canonical_curie(tmp_path):
    bad_prefix_data = {
        "id": "heritageGraph:batch-001",
        "structures": [
            {
                "id": "hg:struct-001",  # Non-canonical prefix
                "name": "Nyatapola"
            }
        ]
    }
    test_file = tmp_path / "bad_prefix.json"
    test_file.write_text(json.dumps(bad_prefix_data), encoding="utf-8")

    res = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "validate_extraction.py"), str(test_file)],
        capture_output=True,
        text=True
    )
    assert res.returncode == 1
    assert "authoritative 'heritageGraph:' prefix" in res.stdout


def test_e2e_ingest_to_validation_flow(tmp_path):
    # Step 1: Preprocess raw input
    csv_file = tmp_path / "raw.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "description"])
        writer.writeheader()
        writer.writerow({
            "id": "bhak-01",
            "name": "Nyatapola Temple",
            "description": "Pagoda temple in Taumadhi Square with Si Guthi association."
        })

    preprocessed_file = tmp_path / "preprocessed.json"
    cmd_ingest = [sys.executable, str(SCRIPTS_DIR / "ingest_raw.py"), str(csv_file), "--out", str(preprocessed_file)]
    res_ingest = subprocess.run(cmd_ingest, capture_output=True, text=True)
    assert res_ingest.returncode == 0

    # Step 2: Agent synthesizes LinkML Container informed by preprocessed tags
    container_data = {
        "id": "heritageGraph:batch-test-001",
        "structures": [
            {
                "id": "heritageGraph:struct-nyatapola",
                "name": "Nyatapola Temple",
                "note": "Pagoda temple in Taumadhi Square with Si Guthi association.",
                "has_architectural_style": "Pagoda",
                "managed_by_guthi": ["heritageGraph:guthi-si"]
            }
        ],
        "guthis": [
            {
                "id": "heritageGraph:guthi-si",
                "name": "Si Guthi",
                "guthi_type": "SiGuthi"
            }
        ]
    }
    extracted_file = tmp_path / "extracted.json"
    extracted_file.write_text(json.dumps(container_data, indent=2), encoding="utf-8")

    # Step 3: Run validate_extraction.py quality gate
    cmd_validate = [sys.executable, str(SCRIPTS_DIR / "validate_extraction.py"), str(extracted_file)]
    res_validate = subprocess.run(cmd_validate, capture_output=True, text=True)
    assert res_validate.returncode == 0
    assert "valid" in res_validate.stdout.lower()
