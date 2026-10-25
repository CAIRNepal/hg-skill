"""Tests for Stages 2-4 RunWorkspace integration (Ticket 3 / #9)."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE2_DIR = REPO_ROOT / "skills" / "02_heritage-entity-resolution" / "scripts"
STAGE3_DIR = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "scripts"
STAGE4_DIR = REPO_ROOT / "skills" / "04_heritage-shacl-validate" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"

for d in (STAGE2_DIR, STAGE3_DIR, STAGE4_DIR, COMMON_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from run_workspace import RunWorkspace
from resolve_entities import main as resolve_main
from map_to_rdf import main as map_main
from validate import main as validate_main


@pytest.fixture
def temp_run_workspace():
    tmp = tempfile.mkdtemp()
    ws = RunWorkspace.init(source_path="test_doc.pdf", run_dir=tmp)
    yield ws
    shutil.rmtree(tmp, ignore_errors=True)


def test_map_to_rdf_run_dir(temp_run_workspace):
    ws = temp_run_workspace

    # Seed 01_extracted.json
    extracted_data = {
        "id": "heritageGraph:batch-test-01",
        "structures": [
            {
                "id": "heritageGraph:struct-krishna-mandir",
                "name": "Krishna Mandir",
                "has_architectural_style": "Shikhara",
                "note": "Iconic multi-tiered stone temple"
            }
        ]
    }
    ws.artifact_path(1).write_text(json.dumps(extracted_data), encoding="utf-8")

    # Run map_to_rdf with --run-dir
    mapping_file = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "assets" / "mappings" / "cidoc-crm.yaml"
    rc = run_cli(map_main, ["--run-dir", str(ws.run_dir), "--mapping", str(mapping_file)])
    assert rc == 0

    # Verify 03_graph.ttl exists
    graph_path = ws.artifact_path(3)
    assert graph_path.exists()
    assert graph_path.stat().st_size > 0

    # Verify manifest tracking
    m = ws.load_manifest()
    assert "stage_03_map" in m["stages"]
    assert m["stages"]["stage_03_map"]["status"] == "success"
    assert m["stages"]["stage_03_map"]["metrics"]["triples"] > 0


def test_shacl_validate_run_dir(temp_run_workspace):
    ws = temp_run_workspace

    # Seed a minimal valid RDF graph in 03_graph.ttl
    graph_ttl = """@prefix crm: <http://www.cidoc-crm.org/cidoc-crm/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix hg: <https://cair-nepal.org/heritagegraph/> .

hg:struct-01 a crm:E22_Human_Made_Object ;
    rdfs:label "Test Temple" .
"""
    ws.artifact_path(3).write_text(graph_ttl, encoding="utf-8")

    # Shapes file
    shapes_file = REPO_ROOT / "skills" / "04_heritage-shacl-validate" / "assets" / "shapes" / "cidoc-crm.shacl.ttl"
    if not shapes_file.exists():
        shapes_file = REPO_ROOT / "schemas" / "HeritageGraph.shacl.ttl"

    rc = run_cli(validate_main, ["--run-dir", str(ws.run_dir), "--shapes", str(shapes_file)])
    assert rc in (0, 1)  # 0 conforms or 1 validation report generated

    # Verify 04_shacl_report.json exists
    report_path = ws.artifact_path(4)
    assert report_path.exists()

    m = ws.load_manifest()
    assert "stage_04_validate" in m["stages"]
    assert m["stages"]["stage_04_validate"]["status"] in ("success", "violations")


def test_resolve_entities_run_dir(temp_run_workspace):
    ws = temp_run_workspace

    # Seed 01_extracted.json
    extracted_data = {
        "id": "heritageGraph:batch-test-02",
        "structures": [
            {
                "id": "heritageGraph:struct-test-01",
                "name": "Patan Temple",
                "note": "Ancient pagoda"
            }
        ]
    }
    ws.artifact_path(1).write_text(json.dumps(extracted_data), encoding="utf-8")

    rc = run_cli(resolve_main, ["--run-dir", str(ws.run_dir)])
    assert rc == 0

    # Verify 02_resolved.json exists
    resolved_path = ws.artifact_path(2)
    assert resolved_path.exists()

    with open(resolved_path, encoding="utf-8") as f:
        res = json.load(f)
    assert "resolution" in res["structures"][0]
    assert res["structures"][0]["resolution"]["status"] == "local"

    # Verify manifest tracking
    m = ws.load_manifest()
    assert "stage_02_resolve" in m["stages"]
    assert m["stages"]["stage_02_resolve"]["status"] == "success"
    assert m["stages"]["stage_02_resolve"]["metrics"]["local"] == 1


def run_cli(main_fn, args_list):
    orig = sys.argv
    try:
        sys.argv = ["script"] + args_list
        return main_fn()
    finally:
        sys.argv = orig
