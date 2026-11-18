"""Tests for embedded Oxigraph mirror resolution in Stage 2 (Ticket 2 / #38)."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE2_DIR = REPO_ROOT / "skills" / "02_heritage-entity-resolution" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"
SRC_DIR = REPO_ROOT / "src"

for d in (STAGE2_DIR, COMMON_DIR, SRC_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from run_workspace import RunWorkspace
from resolve_entities import main as resolve_main, resolve_container_entities
from hg.mirror import OxigraphMirror


@pytest.fixture
def sample_nt_snapshot(tmp_path):
    """Fixture providing a small N-Triples KG snapshot."""
    snapshot_path = tmp_path / "snapshot.nt"
    triples = """<https://cair-nepal.org/heritagegraph/struct-nyatapola> <http://www.w3.org/2000/01/rdf-schema#label> "Nyatapola Temple" .
<https://cair-nepal.org/heritagegraph/struct-nyatapola> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://cair-nepal.org/heritagegraph/Monument> .
<https://cair-nepal.org/heritagegraph/struct-balkumari-patan> <http://www.w3.org/2000/01/rdf-schema#label> "Balkumari Temple" .
<https://cair-nepal.org/heritagegraph/struct-balkumari-patan> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://cair-nepal.org/heritagegraph/Monument> .
<https://cair-nepal.org/heritagegraph/struct-balkumari-thimi> <http://www.w3.org/2000/01/rdf-schema#label> "Balkumari Temple" .
<https://cair-nepal.org/heritagegraph/struct-balkumari-thimi> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://cair-nepal.org/heritagegraph/Monument> .
<https://cair-nepal.org/heritagegraph/place-bhaktapur> <http://www.w3.org/2000/01/rdf-schema#label> "Bhaktapur" .
<https://cair-nepal.org/heritagegraph/place-bhaktapur> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://cair-nepal.org/heritagegraph/Place> .
"""
    snapshot_path.write_text(triples, encoding="utf-8")
    return snapshot_path


@pytest.fixture
def temp_run_env():
    tmp = tempfile.mkdtemp()
    ws = RunWorkspace.init(source_path="test_source.pdf", run_dir=tmp)
    yield ws
    shutil.rmtree(tmp, ignore_errors=True)


def test_oxigraph_mirror_direct_methods(sample_nt_snapshot):
    """Unit test for OxigraphMirror check_exact_uri and find_candidate_entities."""
    mirror = OxigraphMirror(sample_nt_snapshot)

    # 1. Exact URI check (full IRI and prefixed)
    assert mirror.check_exact_uri("https://cair-nepal.org/heritagegraph/struct-nyatapola") is True
    assert mirror.check_exact_uri("heritageGraph:struct-nyatapola") is True
    assert mirror.check_exact_uri("https://cair-nepal.org/heritagegraph/struct-nonexistent") is False
    assert mirror.check_exact_uri("heritageGraph:nonexistent") is False

    # 2. find_candidate_entities exact match
    cands = mirror.find_candidate_entities("Nyatapola Temple", entity_type="Monument", limit=5)
    assert len(cands) >= 1
    top = cands[0]
    assert top["uri"] == "https://cair-nepal.org/heritagegraph/struct-nyatapola"
    assert top["label"] == "Nyatapola Temple"
    assert top["type"] == "https://cair-nepal.org/heritagegraph/Monument"
    assert top["score"] == 1.0
    assert top["source"] == "kg_mirror"
    assert top["match_type"] == "exact"

    # 3. find_candidate_entities ambiguous matches
    ambig_cands = mirror.find_candidate_entities("Balkumari Temple", entity_type="Monument", limit=5)
    assert len(ambig_cands) == 2
    uris = {c["uri"] for c in ambig_cands}
    assert "https://cair-nepal.org/heritagegraph/struct-balkumari-patan" in uris
    assert "https://cair-nepal.org/heritagegraph/struct-balkumari-thimi" in uris


def run_cli(args_list):
    """Run resolve_entities with simulated CLI arguments."""
    return resolve_main(args_list)


def test_stage2_exact_uri_reuse(temp_run_env, sample_nt_snapshot):
    """Test 1: Exact URI match in extracted JSON -> reuses the URI and asserts match."""
    ws = temp_run_env

    extracted_data = {
        "id": "heritageGraph:batch-test-exact-uri",
        "structures": [
            {
                "id": "heritageGraph:struct-nyatapola",
                "name": "Nyatapola Five Roof Temple",
                "note": "Famous multi-roof temple in Taumadhi Square"
            }
        ]
    }
    ws.artifact_path(1).write_text(json.dumps(extracted_data), encoding="utf-8")

    # Run resolve_entities with --mirror
    rc = run_cli([
        "--run-dir", str(ws.run_dir),
        "--mirror", str(sample_nt_snapshot),
        "--no-network"
    ])
    assert rc == 0

    with open(ws.artifact_path(2), encoding="utf-8") as f:
        resolved = json.load(f)

    struct = resolved["structures"][0]
    assert struct["resolution"]["status"] == "linked"
    assert "struct-nyatapola" in struct["resolution"]["uri"]
    assert struct["resolution"]["source"] == "kg_mirror"
    assert struct["resolution"]["match_type"] == "exact"
    assert struct["resolution"]["confidence"] == 1.0


def test_stage2_label_search_mirror_resolution(temp_run_env, sample_nt_snapshot):
    """Test 2: Label search in mirror -> entity named 'Nyatapola Temple' with temporary ID

    resolves to existing heritageGraph:struct-nyatapola instead of minting a new URI.
    """
    ws = temp_run_env

    extracted_data = {
        "id": "heritageGraph:batch-test-label-search",
        "structures": [
            {
                "id": "temp-struct-001",
                "name": "Nyatapola Temple",
                "note": "Temple in Bhaktapur"
            }
        ]
    }
    ws.artifact_path(1).write_text(json.dumps(extracted_data), encoding="utf-8")

    rc = run_cli([
        "--run-dir", str(ws.run_dir),
        "--mirror", str(sample_nt_snapshot),
        "--no-network"
    ])
    assert rc == 0

    with open(ws.artifact_path(2), encoding="utf-8") as f:
        resolved = json.load(f)

    struct = resolved["structures"][0]
    assert struct["resolution"]["status"] == "linked"
    assert struct["resolution"]["uri"] == "https://cair-nepal.org/heritagegraph/struct-nyatapola"
    assert struct["resolution"]["source"] == "kg_mirror"
    assert struct["resolution"]["match_type"] == "exact"
    assert "struct/nyatapola-temple" not in struct["resolution"]["uri"]


def test_stage2_ambiguous_match_staging_in_review_queue(temp_run_env, sample_nt_snapshot):
    """Test 3: Ambiguous match -> when multiple monuments share a similar name,

    adds candidates to 02_review_queue.json.
    """
    ws = temp_run_env

    extracted_data = {
        "id": "heritageGraph:batch-test-ambiguous",
        "structures": [
            {
                "id": "temp-struct-balkumari",
                "name": "Balkumari Temple",
                "note": "Temple to Balkumari"
            }
        ]
    }
    ws.artifact_path(1).write_text(json.dumps(extracted_data), encoding="utf-8")

    rc = run_cli([
        "--run-dir", str(ws.run_dir),
        "--mirror", str(sample_nt_snapshot),
        "--no-network"
    ])
    assert rc == 0

    # Review queue must exist and stage the ambiguous item
    review_queue_path = ws.run_dir / "02_review_queue.json"
    assert review_queue_path.exists()

    with open(review_queue_path, encoding="utf-8") as f:
        queue = json.load(f)

    assert len(queue) == 1
    item = queue[0]
    assert item["label"] == "Balkumari Temple"
    candidates = item.get("candidates", [])
    assert len(candidates) >= 2
    cand_uris = {c["uri"] for c in candidates}
    assert "https://cair-nepal.org/heritagegraph/struct-balkumari-patan" in cand_uris
    assert "https://cair-nepal.org/heritagegraph/struct-balkumari-thimi" in cand_uris


def test_stage2_unmatched_falls_through(temp_run_env, sample_nt_snapshot):
    """Test 4: Unmatched entity falls through to gazetteer / external LOD / fallback minting."""
    ws = temp_run_env
    gaz_dir = REPO_ROOT / "skills" / "02_heritage-entity-resolution" / "assets" / "gazetteers"

    extracted_data = {
        "id": "heritageGraph:batch-test-unmatched",
        "places": [
            {
                "id": "temp-place-patan",
                "name": "Patan",
                "note": "City in Kathmandu Valley"
            }
        ],
        "structures": [
            {
                "id": "temp-struct-unknown-shrine-99",
                "name": "Completely Unknown Shrine 99",
                "note": "Undocumented rural shrine"
            }
        ]
    }
    ws.artifact_path(1).write_text(json.dumps(extracted_data), encoding="utf-8")

    rc = run_cli([
        "--run-dir", str(ws.run_dir),
        "--mirror", str(sample_nt_snapshot),
        "--gazetteers", str(gaz_dir),
        "--no-network"
    ])
    assert rc == 0

    with open(ws.artifact_path(2), encoding="utf-8") as f:
        resolved = json.load(f)

    # 1. Patan is not in mirror, but is in gazetteer -> resolved via gazetteer
    place = resolved["places"][0]
    assert place["resolution"]["status"] == "linked"
    assert "example.org/gazetteer/place/patan" in place["resolution"]["uri"] or "patan" in place["resolution"]["uri"]

    # 2. Unknown shrine is neither in mirror nor in gazetteer -> minted local fallback
    struct = resolved["structures"][0]
    assert struct["resolution"]["status"] == "local"
    assert struct["resolution"]["source"] == "local-mint"
    assert "structure/completely-unknown-shrine-99" in struct["resolution"]["uri"]
