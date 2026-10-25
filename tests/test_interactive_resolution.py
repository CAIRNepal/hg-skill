"""Tests for interactive terminal review and curated gazetteer feedback loop (Ticket 2 / #15)."""
import csv
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
from resolve_entities import main as resolve_main


@pytest.fixture
def temp_run_env():
    tmp = tempfile.mkdtemp()
    ws = RunWorkspace.init(source_path="test_source.pdf", run_dir=tmp)
    yield ws
    shutil.rmtree(tmp, ignore_errors=True)


def test_interactive_selection_and_gazetteer_feedback(temp_run_env, monkeypatch):
    ws = temp_run_env
    gaz_dir = temp_run_env.run_dir / "gazetteers"
    gaz_dir.mkdir(parents=True, exist_ok=True)
    curated_csv = gaz_dir / "curated-links.csv"

    # Seed 01_extracted.json
    extracted_data = {
        "id": "heritageGraph:batch-test-interactive",
        "structures": [
            {
                "id": "heritageGraph:struct-radha-krishna",
                "name": "Radha Krishna Temple at Swotha",
                "note": "Temple in Patan"
            }
        ]
    }
    ws.artifact_path(1).write_text(json.dumps(extracted_data), encoding="utf-8")

    # Simulate curator inputs:
    # 1. Custom URI: choice 'c'
    # 2. URI string: 'http://www.wikidata.org/entity/Q108882341'
    # 3. Save to curated-links.csv: 'y'
    inputs = iter(["c", "http://www.wikidata.org/entity/Q108882341", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    rc = run_cli(resolve_main, [
        "--run-dir", str(ws.run_dir),
        "--interactive",
        "--gazetteers", str(gaz_dir),
        "--no-network"
    ])
    assert rc == 0

    # 1. Verify 02_resolved.json has human-curator resolution
    with open(ws.artifact_path(2), encoding="utf-8") as f:
        resolved = json.load(f)

    struct = resolved["structures"][0]
    assert struct["resolution"]["status"] == "linked"
    assert struct["resolution"]["uri"] == "http://www.wikidata.org/entity/Q108882341"
    assert "human-curator" in struct["resolution"]["source"]
    assert struct["resolution"]["confidence"] == 1.0

    # 2. Verify curated-links.csv was created and written
    assert curated_csv.exists()
    with open(curated_csv, encoding="utf-8", newline="") as f:
        reader = list(csv.DictReader(f))
    assert len(reader) == 1
    assert reader[0]["label"] == "Radha Krishna Temple at Swotha"
    assert reader[0]["uri"] == "http://www.wikidata.org/entity/Q108882341"

    # 3. Verify manifest tracking
    m = ws.load_manifest()
    assert m["stages"]["stage_02_resolve"]["metrics"]["curator_decisions"] == 1


def test_interactive_candidate_choice(temp_run_env, monkeypatch):
    ws = temp_run_env
    gaz_dir = temp_run_env.run_dir / "gazetteers"
    gaz_dir.mkdir(parents=True, exist_ok=True)
    curated_csv = gaz_dir / "curated-links.csv"

    extracted_data = {
        "id": "heritageGraph:batch-test-cand",
        "structures": [
            {
                "id": "heritageGraph:struct-temple-p1",
                "name": "Balkumari Temple",
                "note": "Ancient shrine"
            }
        ]
    }
    ws.artifact_path(1).write_text(json.dumps(extracted_data), encoding="utf-8")

    # Mock candidate search to return a mock candidate
    def mock_fetch_candidates(label, kind, context="", gazetteers_dir=None, query_network=True):
        return [{
            "uri": "http://www.wikidata.org/entity/Q11111",
            "source": "wikidata",
            "description": "Balkumari Temple in Lalitpur"
        }]

    monkeypatch.setattr("resolve_entities.fetch_candidates", mock_fetch_candidates)

    # Curator selects option 1 (the mocked candidate), then answers 'y' to save to gazetteer
    inputs = iter(["1", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    rc = run_cli(resolve_main, [
        "--run-dir", str(ws.run_dir),
        "--interactive",
        "--gazetteers", str(gaz_dir),
        "--no-network"
    ])
    assert rc == 0

    with open(ws.artifact_path(2), encoding="utf-8") as f:
        resolved = json.load(f)

    struct = resolved["structures"][0]
    assert struct["resolution"]["status"] == "linked"
    assert struct["resolution"]["uri"] == "http://www.wikidata.org/entity/Q11111"
    assert "wikidata" in struct["resolution"]["source"]
    assert struct["resolution"]["confidence"] == 1.0


def test_interactive_skip(temp_run_env, monkeypatch):
    ws = temp_run_env
    gaz_dir = temp_run_env.run_dir / "gazetteers"
    gaz_dir.mkdir(parents=True, exist_ok=True)

    extracted_data = {
        "id": "heritageGraph:batch-test-skip",
        "structures": [
            {
                "id": "heritageGraph:struct-skip-01",
                "name": "Unknown Shrine",
                "note": "Unknown"
            }
        ]
    }
    ws.artifact_path(1).write_text(json.dumps(extracted_data), encoding="utf-8")

    # Curator chooses 's' to skip
    inputs = iter(["s"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    rc = run_cli(resolve_main, [
        "--run-dir", str(ws.run_dir),
        "--interactive",
        "--gazetteers", str(gaz_dir),
        "--no-network"
    ])
    assert rc == 0

    with open(ws.artifact_path(2), encoding="utf-8") as f:
        resolved = json.load(f)

    struct = resolved["structures"][0]
    # Retains minted fallback URI because it was skipped
    assert struct["resolution"]["status"] == "local"
    assert "curator" not in struct["resolution"]["source"]


def run_cli(main_fn, args_list):
    orig = sys.argv
    try:
        sys.argv = ["script"] + args_list
        return main_fn()
    finally:
        sys.argv = orig
