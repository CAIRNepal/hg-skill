"""Unit tests for run_workspace and manifest management (Ticket 1 / #7)."""
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Ensure skills/common is on sys.path
import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
COMMON_DIR = REPO_ROOT / "skills" / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from run_workspace import (
    STAGE_ARTIFACTS,
    RunWorkspace,
    compute_sha256,
    generate_run_id,
    resolve_run_dir,
)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_file(temp_dir):
    p = temp_dir / "sample_doc.pdf"
    p.write_bytes(b"%PDF-1.4 test heritage content")
    return p


def test_compute_sha256(sample_file):
    h = compute_sha256(sample_file)
    assert isinstance(h, str)
    assert len(h) == 64


def test_generate_run_id():
    run_id = generate_run_id("admin,+IDJMSS-1(1)_89-103.pdf")
    assert "idjmss" in run_id
    assert run_id.startswith("20")  # starts with year


def test_resolve_run_dir_default(sample_file, temp_dir):
    # When no run_dir is passed, should default under a specified base or root runs/
    run_dir = resolve_run_dir(sample_file, base_dir=temp_dir / "runs")
    assert run_dir.exists()
    assert (temp_dir / "runs") in run_dir.parents or run_dir.parent == (temp_dir / "runs")


def test_resolve_run_dir_explicit(sample_file, temp_dir):
    explicit = temp_dir / "custom_run"
    run_dir = resolve_run_dir(sample_file, run_dir=explicit)
    assert run_dir == explicit
    assert run_dir.exists()


def test_workspace_init_manifest(sample_file, temp_dir):
    ws = RunWorkspace.init(sample_file, run_dir=temp_dir / "run_01")
    manifest_path = ws.manifest_path
    assert manifest_path.exists()

    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["run_id"] == "run_01"
    assert data["status"] == "in_progress"
    assert data["source"]["file_name"] == "sample_doc.pdf"
    assert data["source"]["sha256"] == compute_sha256(sample_file)
    assert data["source"]["byte_size"] == sample_file.stat().st_size
    assert "schema_version" in data["environment"]
    assert "stages" in data


def test_workspace_stage_lifecycle(sample_file, temp_dir):
    ws = RunWorkspace.init(sample_file, run_dir=temp_dir / "run_02")

    # Record stage 0 start and finish
    ws.record_stage_start(0, "ingest", {"command": "ingest_raw.py"})
    ws.record_stage_finish(0, "ingest", status="success", metrics={"chunks": 14})

    m = ws.load_manifest()
    stage0 = m["stages"]["stage_00_ingest"]
    assert stage0["status"] == "success"
    assert stage0["metrics"]["chunks"] == 14
    assert "duration_seconds" in stage0


def test_workspace_artifact_paths(sample_file, temp_dir):
    ws = RunWorkspace.init(sample_file, run_dir=temp_dir / "run_03")

    p0 = ws.artifact_path(0)
    assert p0.name == "00_preprocessed.json"
    p1 = ws.artifact_path(1)
    assert p1.name == "01_extracted.json"
    p2 = ws.artifact_path(2)
    assert p2.name == "02_resolved.json"
    p3 = ws.artifact_path(3)
    assert p3.name == "03_graph.ttl"
    p4 = ws.artifact_path(4)
    assert p4.name == "04_shacl_report.json"


def test_workspace_finalize(sample_file, temp_dir):
    ws = RunWorkspace.init(sample_file, run_dir=temp_dir / "run_04")
    ws.finalize(status="completed", summary={"total_entities": 15})

    m = ws.load_manifest()
    assert m["status"] == "completed"
    assert m["summary"]["total_entities"] == 15
    assert "completed_at" in m
