"""Golden-Fixture Isomorphism, Determinism, SHACL, and URI Idempotence Tests (Ticket 7 / #43).

Verifies that:
  1. Golden document fixture produces an RDF graph strictly isomorphic to expected graph.
  2. Transformation is deterministic (same input produces identical graph serialization & hash).
  3. Pre-flight resolution is idempotent against local mirror (reuses existing URI, no duplicates).
  4. Output graph conforms to authoritative SHACL shapes without vacuous pass.
  5. Diff gate verifies existing references vs new entities against mirror.
"""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest
from rdflib import Graph
from rdflib.compare import isomorphic
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
MAPPING_FILE = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "assets" / "mappings" / "heritagegraph.yaml"
SHAPES_FILE = REPO_ROOT / "schemas" / "HeritageGraph.shacl.ttl"

STAGE2_DIR = REPO_ROOT / "skills" / "02_heritage-entity-resolution" / "scripts"
STAGE3_DIR = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "scripts"
STAGE4_DIR = REPO_ROOT / "skills" / "04_heritage-shacl-validate" / "scripts"
STAGE5_DIR = REPO_ROOT / "skills" / "05_heritage-diff" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"
SRC_DIR = REPO_ROOT / "src"

for d in (STAGE2_DIR, STAGE3_DIR, STAGE4_DIR, STAGE5_DIR, COMMON_DIR, SRC_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from map_to_rdf import main as map_main
from validate import main as validate_main
from diff_graph import compute_diff
from hg.mirror import OxigraphMirror
from resolve_entities import resolve_container_entities


def cli_call(fn, *args):
    orig = sys.argv
    try:
        sys.argv = ["script"] + [str(a) for a in args]
        return fn()
    finally:
        sys.argv = orig


@pytest.fixture
def golden_container_path():
    return FIXTURES_DIR / "golden_container.json"


@pytest.fixture
def golden_expected_path():
    return FIXTURES_DIR / "golden_expected.ttl"


@pytest.fixture
def mirror_snapshot_path():
    return FIXTURES_DIR / "mirror_snapshot.nt"


def test_golden_graph_isomorphism(golden_container_path, golden_expected_path, tmp_path):
    """Test 1: Transformation produces an RDF graph strictly isomorphic to expected golden graph."""
    out_ttl = tmp_path / "actual_golden.ttl"

    # Run Stage 3 mapper on golden container
    rc = cli_call(
        map_main,
        golden_container_path,
        "--mapping", MAPPING_FILE,
        "--out", out_ttl,
    )
    assert rc == 0
    assert out_ttl.exists()

    actual_g = Graph()
    actual_g.parse(str(out_ttl), format="turtle")

    expected_g = Graph()
    expected_g.parse(str(golden_expected_path), format="turtle")

    # Isomorphism verification
    assert isomorphic(actual_g, expected_g), (
        f"Generated RDF graph is not isomorphic to golden expected graph.\n"
        f"Actual triples: {len(actual_g)}, Expected triples: {len(expected_g)}"
    )


def test_graph_determinism(golden_container_path, tmp_path):
    """Test 2: Determinism test - repeated runs on same input produce identical graph hash."""
    out_run1 = tmp_path / "run1.ttl"
    out_run2 = tmp_path / "run2.ttl"

    rc1 = cli_call(map_main, golden_container_path, "--mapping", MAPPING_FILE, "--out", out_run1)
    rc2 = cli_call(map_main, golden_container_path, "--mapping", MAPPING_FILE, "--out", out_run2)
    assert rc1 == 0 and rc2 == 0

    g1 = Graph().parse(str(out_run1), format="turtle")
    g2 = Graph().parse(str(out_run2), format="turtle")

    # Normalize to canonical N-Triples strings for hashing
    nt1 = g1.serialize(format="nt")
    nt2 = g2.serialize(format="nt")

    hash1 = hashlib.sha256(nt1.encode("utf-8")).hexdigest()
    hash2 = hashlib.sha256(nt2.encode("utf-8")).hexdigest()

    assert hash1 == hash2, "Repeated pipeline mapping produced differing graph hashes!"


def test_uri_idempotence_against_mirror(golden_container_path, mirror_snapshot_path):
    """Test 3: URI Idempotence - pre-flight resolution reuses existing canonical URI without re-minting."""
    mirror = OxigraphMirror(mirror_snapshot_path)

    with open(golden_container_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Resolve entities using the local mirror
    res = resolve_container_entities(
        data,
        query_network=False,
        mirror=mirror,
    )
    resolved_data = res["data"]
    struct = resolved_data["structures"][0]

    # Verify existing URI was reused directly
    assert struct["resolution"]["status"] == "linked"
    assert struct["resolution"]["source"] == "kg_mirror"
    assert "struct-krishna-mandir" in struct["resolution"]["uri"]
    assert struct["resolution"]["match_type"] == "exact"
    # Ensure no duplicate re-minted URI
    assert "structure/krishna-mandir" not in struct["resolution"]["uri"]


def test_golden_graph_shacl_conformance(golden_container_path, tmp_path):
    """Test 4: SHACL conformance - golden graph validates with 0 violations and non-vacuous coverage."""
    out_ttl = tmp_path / "graph_for_shacl.ttl"
    rep_json = tmp_path / "shacl_report.json"

    rc_map = cli_call(map_main, golden_container_path, "--mapping", MAPPING_FILE, "--out", out_ttl)
    assert rc_map == 0

    rc_val = cli_call(validate_main, out_ttl, "--shapes", SHAPES_FILE, "--report", rep_json)
    assert rc_val == 0, f"SHACL validation failed with code {rc_val}"
    assert rep_json.exists()

    with open(rep_json, encoding="utf-8") as f:
        report = json.load(f)

    assert report["conforms"] is True
    assert report.get("vacuous") is False
    assert report.get("shape_coverage", {}).get("shapes_matched", 0) > 0


def test_golden_graph_diff_against_mirror(golden_container_path, mirror_snapshot_path, tmp_path):
    """Test 5: Stage 05 Diff Gate correctly identifies existing references with 0 duplicates."""
    out_ttl = tmp_path / "graph_for_diff.ttl"
    cli_call(map_main, golden_container_path, "--mapping", MAPPING_FILE, "--out", out_ttl)

    mirror = OxigraphMirror(mirror_snapshot_path)
    diff = compute_diff(out_ttl, mirror)

    assert diff["counts"]["suspected_duplicates"] == 0
    assert diff["counts"]["existing_references"] >= 1
    existing_uris = [e["uri"] for e in diff["existing_references"]]
    assert any("struct-krishna-mandir" in u for u in existing_uris)
