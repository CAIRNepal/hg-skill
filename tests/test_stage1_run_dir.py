"""Tests for Stage 0 & Stage 1 RunWorkspace integration (Ticket 2 / #8)."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE1_DIR = REPO_ROOT / "skills" / "01_heritage-extract" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"
for d in (STAGE1_DIR, COMMON_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from ingest_raw import main as ingest_main
from validate_extraction import main as validate_main
from run_workspace import RunWorkspace


@pytest.fixture
def temp_workspace():
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def sample_csv(temp_workspace):
    csv_file = temp_workspace / "monuments.csv"
    csv_file.write_text(
        "id,monument_name,style,description\n"
        "M01,Nyatapola Temple,Pagoda,Five-storey pagoda built in 1702 by Bhupatindra Malla.\n",
        encoding="utf-8"
    )
    return csv_file


def test_ingest_auto_run_dir(sample_csv, temp_workspace, monkeypatch):
    run_base = temp_workspace / "runs"
    # Monkeypatch DEFAULT_RUNS_DIR in run_workspace
    import run_workspace
    monkeypatch.setattr(run_workspace, "DEFAULT_RUNS_DIR", run_base)

    # Ingest without --run-dir or --out should auto-create runs/<run_id>/00_preprocessed.json
    rc = ingest_main_cli([str(sample_csv)])
    assert rc == 0

    run_dirs = list(run_base.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    preprocessed_path = run_dir / "00_preprocessed.json"
    manifest_path = run_dir / "manifest.json"

    assert preprocessed_path.exists()
    assert manifest_path.exists()

    with open(manifest_path, encoding="utf-8") as f:
        m = json.load(f)
    assert m["status"] == "in_progress"
    assert "stage_00_ingest" in m["stages"]
    assert m["stages"]["stage_00_ingest"]["status"] == "success"
    assert m["stages"]["stage_00_ingest"]["metrics"]["total_items"] == 1


def test_ingest_explicit_run_dir(sample_csv, temp_workspace):
    custom_run = temp_workspace / "custom_run_01"
    rc = ingest_main_cli([str(sample_csv), "--run-dir", str(custom_run)])
    assert rc == 0

    assert (custom_run / "00_preprocessed.json").exists()
    assert (custom_run / "manifest.json").exists()


def test_validate_run_dir(temp_workspace):
    run_dir = temp_workspace / "run_validate"
    ws = RunWorkspace.init(source_path="test_doc.pdf", run_dir=run_dir)

    # Put valid 01_extracted.json into run_dir
    extracted_data = {
        "id": "heritageGraph:batch-test-01",
        "structures": [
            {
                "id": "heritageGraph:struct-test-01",
                "name": "Test Temple",
                "has_architectural_style": "Pagoda"
            }
        ]
    }
    extracted_path = ws.artifact_path(1)
    extracted_path.write_text(json.dumps(extracted_data), encoding="utf-8")

    # Run validator passing the run directory
    rc = validate_main_cli(["--run-dir", str(run_dir)])
    assert rc == 0

    m = ws.load_manifest()
    assert "stage_01_extract" in m["stages"]
    assert m["stages"]["stage_01_extract"]["status"] == "success"
    assert m["stages"]["stage_01_extract"]["metrics"]["total_entities"] == 1


def ingest_main_cli(args_list):
    import sys
    orig = sys.argv
    try:
        sys.argv = ["ingest_raw.py"] + args_list
        return ingest_main()
    finally:
        sys.argv = orig


def validate_main_cli(args_list):
    import sys
    orig = sys.argv
    try:
        sys.argv = ["validate_extraction.py"] + args_list
        return validate_main()
    finally:
        sys.argv = orig
