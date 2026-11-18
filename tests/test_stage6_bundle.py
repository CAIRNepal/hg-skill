"""Tests for Stage 06 Contribution Bundle Packaging & Provenance Activity (Ticket 5 / #41)."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE6_DIR = REPO_ROOT / "skills" / "06_heritage-contribute" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"
SRC_DIR = REPO_ROOT / "src"

for d in (STAGE6_DIR, COMMON_DIR, SRC_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from package_bundle import package_bundle, main as bundle_main

HG = "https://cair-nepal.org/heritagegraph/"


@pytest.fixture
def run_dir(tmp_path):
    """Create a minimal valid pipeline run directory."""
    rd = tmp_path / "run-test-001"
    rd.mkdir()

    # 03_graph.ttl
    (rd / "03_graph.ttl").write_text(
        f"""@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix hg: <{HG}> .
hg:struct-changu-narayan rdfs:label "Changu Narayan Temple" .
hg:struct-changu-narayan rdf:type hg:Monument .
""",
        encoding="utf-8",
    )

    # manifest.json
    (rd / "manifest.json").write_text(
        json.dumps({
            "run_id": "run-test-001",
            "source_path": "tests/fixtures/sample.pdf",
            "status": "completed",
            "restricted_distribution": False,
        }),
        encoding="utf-8",
    )

    # 01_extracted.json with evidence spans + sensitivity
    (rd / "01_extracted.json").write_text(
        json.dumps({
            "id": "heritageGraph:batch-test-001",
            "structures": [
                {
                    "id": "heritageGraph:struct-changu-narayan",
                    "name": "Changu Narayan Temple",
                    "sensitivity": "public",
                    "license": "CC-BY-4.0",
                    "evidence_span": {"page_number": 3, "paragraph_span": [1, 2]},
                },
                {
                    "id": "heritageGraph:struct-guthi-ritual-secret",
                    "name": "Secret Guthi Ritual",
                    "sensitivity": "restricted-sacred",
                    "license": "CC-BY-4.0",
                    "evidence_span": {"page_number": 7, "paragraph_span": [5, 6]},
                },
            ],
        }),
        encoding="utf-8",
    )

    # 05_diff_report.json
    (rd / "05_diff_report.json").write_text(
        json.dumps({"counts": {"new_entities": 1, "existing_references": 0, "suspected_duplicates": 0}}),
        encoding="utf-8",
    )

    return rd


def test_bundle_creates_expected_files(run_dir, tmp_path):
    """Bundle creates all required artifact files."""
    bundle_dir = tmp_path / "bundle-output"
    meta = package_bundle(run_dir=run_dir, bundle_dir=bundle_dir, run_id="run-test-001")

    assert bundle_dir.exists()
    assert (bundle_dir / "contribution-graph.nq").exists()
    assert (bundle_dir / "provenance.ttl").exists()
    assert (bundle_dir / "manifest.json").exists()
    assert (bundle_dir / "evidence.json").exists()
    assert (bundle_dir / "rights.json").exists()
    assert (bundle_dir / "diff_report.json").exists()
    assert (bundle_dir / "bundle.json").exists()


def test_bundle_named_graph_in_nquads(run_dir, tmp_path):
    """Contribution N-Quads contain the contribution named graph IRI."""
    bundle_dir = tmp_path / "bundle-output"
    meta = package_bundle(run_dir=run_dir, bundle_dir=bundle_dir, run_id="run-test-001")

    nq_content = (bundle_dir / "contribution-graph.nq").read_text(encoding="utf-8")
    assert "contribution-run-test-001" in nq_content
    assert "changu-narayan" in nq_content


def test_bundle_prov_metadata(run_dir, tmp_path):
    """Provenance TTL contains PROV-O Activity, Entity, wasDerivedFrom."""
    bundle_dir = tmp_path / "bundle-output"
    meta = package_bundle(run_dir=run_dir, bundle_dir=bundle_dir, run_id="run-test-001")

    prov_content = (bundle_dir / "provenance.ttl").read_text(encoding="utf-8")
    assert "prov:Activity" in prov_content or "Activity" in prov_content
    assert "prov:wasGeneratedBy" in prov_content or "wasGeneratedBy" in prov_content
    assert "prov:wasDerivedFrom" in prov_content or "wasDerivedFrom" in prov_content


def test_bundle_evidence_spans(run_dir, tmp_path):
    """Evidence JSON contains per-fact source spans from extraction."""
    bundle_dir = tmp_path / "bundle-output"
    meta = package_bundle(run_dir=run_dir, bundle_dir=bundle_dir, run_id="run-test-001")

    with open(bundle_dir / "evidence.json", encoding="utf-8") as f:
        evidence = json.load(f)

    assert len(evidence) >= 1
    span = evidence[0]
    assert "evidence_span" in span
    assert span["evidence_span"].get("page_number") == 3


def test_bundle_rights_metadata(run_dir, tmp_path):
    """Rights JSON captures cultural sensitivity metadata."""
    bundle_dir = tmp_path / "bundle-output"
    meta = package_bundle(run_dir=run_dir, bundle_dir=bundle_dir, run_id="run-test-001")

    with open(bundle_dir / "rights.json", encoding="utf-8") as f:
        rights = json.load(f)

    assert "named_graph" in rights
    assert "restricted_distribution" in rights
    entities = rights.get("entities", [])
    sensitive = [e for e in entities if e.get("sensitivity") == "restricted-sacred"]
    assert len(sensitive) >= 1


def test_bundle_meta_has_checksums(run_dir, tmp_path):
    """bundle.json contains SHA-256 checksums for all bundle files."""
    bundle_dir = tmp_path / "bundle-output"
    meta = package_bundle(run_dir=run_dir, bundle_dir=bundle_dir, run_id="run-test-001")

    with open(bundle_dir / "bundle.json", encoding="utf-8") as f:
        bundle_meta = json.load(f)

    assert "bundle_id" in bundle_meta
    assert "named_graph" in bundle_meta
    assert "checksums" in bundle_meta
    assert "contribution-graph.nq" in bundle_meta["checksums"]
    assert "provenance.ttl" in bundle_meta["checksums"]
    assert "evidence.json" in bundle_meta["checksums"]
    assert "rights.json" in bundle_meta["checksums"]


def test_bundle_cli(run_dir, tmp_path):
    """CLI command packages the bundle and exits 0."""
    bundle_dir = tmp_path / "cli-bundle"
    rc = bundle_main([str(run_dir), "--out", str(bundle_dir), "--run-id", "run-test-cli"])
    assert rc == 0
    assert (bundle_dir / "bundle.json").exists()
    assert (bundle_dir / "contribution-graph.nq").exists()

