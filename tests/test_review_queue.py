"""Tests for Review Queue Staging & Candidate Aggregation (Ticket 1 / #14)."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE2_DIR = REPO_ROOT / "skills" / "02_heritage-entity-resolution" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"

for d in (STAGE2_DIR, COMMON_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from run_workspace import RunWorkspace
from resolve_entities import fetch_candidates, main as resolve_main


@pytest.fixture
def temp_run_env():
    tmp = tempfile.mkdtemp()
    ws = RunWorkspace.init(source_path="test_source.pdf", run_dir=tmp)
    yield ws
    shutil.rmtree(tmp, ignore_errors=True)


def test_fetch_candidates_from_gazetteer():
    gaz_dir = REPO_ROOT / "skills" / "02_heritage-entity-resolution" / "assets" / "gazetteers"
    candidates = fetch_candidates("Patan", "place", "Kathmandu Valley", gazetteers_dir=gaz_dir, query_network=False)
    assert len(candidates) >= 1
    assert any("example.org/gazetteer/place/patan" in c["uri"] for c in candidates)


def test_review_queue_staging(temp_run_env):
    ws = temp_run_env

    # Seed 01_extracted.json with one gazetteer match and one unlinked monument
    extracted_data = {
        "id": "heritageGraph:batch-test-review-01",
        "places": [
            {
                "id": "heritageGraph:place-patan",
                "name": "Patan",
                "note": "Ancient city in Kathmandu Valley"
            }
        ],
        "structures": [
            {
                "id": "heritageGraph:struct-radha-krishna-swotha",
                "name": "Radha Krishna Temple at Swotha",
                "note": "Temple damaged in 2015 earthquake"
            }
        ]
    }
    ws.artifact_path(1).write_text(json.dumps(extracted_data), encoding="utf-8")

    # Run non-interactive resolve_entities
    rc = run_cli(resolve_main, ["--run-dir", str(ws.run_dir), "--no-network"])
    assert rc == 0

    # 02_resolved.json must exist
    assert ws.artifact_path(2).exists()

    # 02_review_queue.json must exist in run directory
    review_queue_path = ws.run_dir / "02_review_queue.json"
    assert review_queue_path.exists()

    with open(review_queue_path, encoding="utf-8") as f:
        queue = json.load(f)

    # Radha Krishna Temple was unlinked, so it must be in the review queue
    assert len(queue) == 1
    assert queue[0]["id"] == "heritageGraph:struct-radha-krishna-swotha"
    assert queue[0]["status"] == "local"
    assert "candidates" in queue[0]

    # Check manifest updates
    m = ws.load_manifest()
    stage02 = m["stages"]["stage_02_resolve"]
    assert stage02["metrics"]["needs_human_review"] is True
    assert stage02["metrics"]["review_queue_count"] == 1


def run_cli(main_fn, args_list):
    orig = sys.argv
    try:
        sys.argv = ["script"] + args_list
        return main_fn()
    finally:
        sys.argv = orig
