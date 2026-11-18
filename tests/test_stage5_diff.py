"""Tests for Stage 05 Diff & Deduplication Gate (Ticket 4 / #40)."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE5_DIR = REPO_ROOT / "skills" / "05_heritage-diff" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"
SRC_DIR = REPO_ROOT / "src"

for d in (STAGE5_DIR, COMMON_DIR, SRC_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from hg.mirror import OxigraphMirror
from diff_graph import compute_diff, main as diff_main


HG = "https://cair-nepal.org/heritagegraph/"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


@pytest.fixture
def mirror_snapshot(tmp_path):
    """Small N-Triples KG mirror with two known entities."""
    snap = tmp_path / "mirror.nt"
    snap.write_text(
        f"<{HG}struct-nyatapola> <{RDFS}label> \"Nyatapola Temple\" .\n"
        f"<{HG}struct-nyatapola> <{RDF}type> <{HG}Monument> .\n"
        f"<{HG}place-bhaktapur> <{RDFS}label> \"Bhaktapur\" .\n"
        f"<{HG}place-bhaktapur> <{RDF}type> <{HG}Place> .\n",
        encoding="utf-8",
    )
    return snap


@pytest.fixture
def mirror(mirror_snapshot):
    return OxigraphMirror(mirror_snapshot)


def _write_ttl(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_diff_new_entity_only(tmp_path, mirror):
    """Completely novel entity => appears in new_entities, not suspected_duplicates.

    Note: hg:Monument class URI may appear in existing_references as an object ref
    since it's typed in the mirror snapshot. What matters is the entity subject itself
    is a new_entity, not a suspected_duplicate.
    """
    graph = _write_ttl(
        tmp_path / "03_graph.ttl",
        f"""@prefix rdfs: <{RDFS}> .
@prefix rdf: <{RDF}> .
@prefix hg: <{HG}> .
hg:struct-changu-narayan rdfs:label "Changu Narayan Temple" .
hg:struct-changu-narayan rdf:type hg:Monument .
""",
    )
    report = compute_diff(graph, mirror)
    assert report["counts"]["new_entities"] == 1
    assert report["counts"]["suspected_duplicates"] == 0
    new_uris = [e["uri"] for e in report["new_entities"]]
    assert f"{HG}struct-changu-narayan" in new_uris


def test_diff_exact_uri_existing(tmp_path, mirror):
    """Entity whose URI already exists in mirror => existing_references."""
    graph = _write_ttl(
        tmp_path / "03_graph.ttl",
        f"""@prefix rdfs: <{RDFS}> .
@prefix hg: <{HG}> .
hg:struct-nyatapola rdfs:label "Nyatapola" .
""",
    )
    report = compute_diff(graph, mirror)
    assert report["counts"]["existing_references"] >= 1
    assert report["counts"]["new_entities"] == 0
    existing_uris = [e["uri"] for e in report["existing_references"]]
    assert f"{HG}struct-nyatapola" in existing_uris


def test_diff_suspected_duplicate(tmp_path, mirror):
    """New URI with same label as existing mirror entity => suspected_duplicates."""
    graph = _write_ttl(
        tmp_path / "03_graph.ttl",
        f"""@prefix rdfs: <{RDFS}> .
@prefix rdf: <{RDF}> .
@prefix hg: <{HG}> .
hg:struct-nyatapola-new rdfs:label "Nyatapola Temple" .
hg:struct-nyatapola-new rdf:type hg:Monument .
""",
    )
    report = compute_diff(graph, mirror)
    assert report["counts"]["suspected_duplicates"] >= 1
    dup = report["suspected_duplicates"][0]
    assert dup["uri"] == f"{HG}struct-nyatapola-new"
    assert dup["label"] == "Nyatapola Temple"
    assert any("struct-nyatapola" in c["uri"] for c in dup["candidates"])


def test_diff_mixed_graph(tmp_path, mirror):
    """Graph with new, existing, and duplicate entities => all categories filled."""
    graph = _write_ttl(
        tmp_path / "03_graph.ttl",
        f"""@prefix rdfs: <{RDFS}> .
@prefix rdf: <{RDF}> .
@prefix hg: <{HG}> .
hg:struct-nyatapola rdfs:label "Nyatapola" .
hg:struct-changu-narayan rdfs:label "Changu Narayan Temple" .
hg:struct-nyatapola-new rdfs:label "Nyatapola Temple" .
hg:struct-nyatapola-new rdf:type hg:Monument .
""",
    )
    report = compute_diff(graph, mirror)
    assert report["counts"]["existing_references"] >= 1
    assert report["counts"]["new_entities"] >= 1
    assert report["counts"]["suspected_duplicates"] >= 1


def test_diff_object_ref_existing(tmp_path, mirror):
    """Object reference to known mirror URI => appears in existing_references."""
    graph = _write_ttl(
        tmp_path / "03_graph.ttl",
        f"""@prefix hg: <{HG}> .
@prefix rdfs: <{RDFS}> .
hg:struct-changu-narayan rdfs:label "Changu Narayan" .
hg:struct-changu-narayan hg:locatedIn hg:place-bhaktapur .
""",
    )
    report = compute_diff(graph, mirror)
    existing_uris = [e["uri"] for e in report["existing_references"]]
    assert f"{HG}place-bhaktapur" in existing_uris


def test_diff_report_written_to_file(tmp_path, mirror_snapshot):
    """compute_diff output is serializable and CLI writes the report file."""
    graph = _write_ttl(
        tmp_path / "03_graph.ttl",
        f"<{HG}struct-new-entity> <{RDFS}label> \"New Entity\" .\n",
    )
    out = tmp_path / "05_diff_report.json"
    rc = diff_main([
        str(graph),
        "--mirror", str(mirror_snapshot),
        "--out", str(out),
        "--no-fail-on-duplicates",
    ])
    assert rc == 0
    assert out.exists()
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    assert "counts" in data
    assert "new_entities" in data
    assert "suspected_duplicates" in data
    assert "existing_references" in data


def test_diff_gate_fails_on_duplicates(tmp_path, mirror_snapshot):
    """Gate exits with code 1 if suspected duplicates exist and --no-fail-on-duplicates not set."""
    graph = _write_ttl(
        tmp_path / "03_graph.ttl",
        f"<{HG}struct-nyatapola-dup> <{RDFS}label> \"Nyatapola Temple\" .\n",
    )
    out = tmp_path / "05_diff_report.json"
    rc = diff_main([
        str(graph),
        "--mirror", str(mirror_snapshot),
        "--out", str(out),
    ])
    assert rc == 1


def test_diff_gate_no_fail_flag(tmp_path, mirror_snapshot):
    """Gate exits with code 0 when --no-fail-on-duplicates is passed even with duplicates."""
    graph = _write_ttl(
        tmp_path / "03_graph.ttl",
        f"<{HG}struct-nyatapola-dup> <{RDFS}label> \"Nyatapola Temple\" .\n",
    )
    out = tmp_path / "05_diff_report.json"
    rc = diff_main([
        str(graph),
        "--mirror", str(mirror_snapshot),
        "--out", str(out),
        "--no-fail-on-duplicates",
    ])
    assert rc == 0
