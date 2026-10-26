"""End-to-end tests for pipeline run lifecycle and orchestration (Ticket 4 / #10)."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
ORCH_DIR = REPO_ROOT / "skills" / "00_heritage-to-rdf" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"

for d in (ORCH_DIR, COMMON_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from run_workspace import RunWorkspace
from run_pipeline import run_pipeline


@pytest.fixture
def temp_run_env():
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


def test_run_pipeline_from_extracted(temp_run_env):
    # Create a run workspace seeded with 01_extracted.json
    run_dir = temp_run_env / "test_run"
    ws = RunWorkspace.init(source_path="survey.pdf", run_dir=run_dir)

    extracted_data = {
        "id": "heritageGraph:batch-e2e-01",
        "structures": [
            {
                "id": "heritageGraph:struct-e2e-krishna",
                "name": "Krishna Mandir",
                "has_architectural_style": "Shikhara",
                "note": "Famous stone temple in Patan"
            }
        ]
    }
    ws.artifact_path(1).write_text(json.dumps(extracted_data), encoding="utf-8")

    # Run pipeline on the run directory
    rc = run_pipeline(run_dir=run_dir, ontology="cidoc-crm")
    assert rc == 0

    # Verify artifacts exist: 02_resolved.json, 03_graph.ttl, 04_shacl_report.json
    assert ws.artifact_path(1).exists()
    assert ws.artifact_path(2).exists()
    assert ws.artifact_path(3).exists()
    assert ws.artifact_path(4).exists()

    # Verify manifest.json
    m = ws.load_manifest()
    assert m["status"] == "completed"
    assert "stage_02_resolve" in m["stages"]
    assert "stage_03_map" in m["stages"]
    assert "stage_04_validate" in m["stages"]
    assert m["summary"]["total_triples"] > 0


def test_run_pipeline_defaults_to_native_heritagegraph(temp_run_env):
    run_dir = temp_run_env / "native_run"
    ws = RunWorkspace.init(source_path="survey.pdf", run_dir=run_dir)
    container = {
        "id": "heritageGraph:batch-native-01",
        "places": [{"id": "heritageGraph:place-patan", "name": "Patan"}],
        "guthis": [{"id": "heritageGraph:guthi-x", "name": "X Guthi"}],
        "structures": [{
            "id": "heritageGraph:struct-native-krishna", "name": "Krishna Mandir",
            "existence_status": "Extant",
            "has_current_location": "heritageGraph:place-patan",
            "managed_by_guthi": ["heritageGraph:guthi-x"],
        }],
    }
    ws.artifact_path(1).write_text(json.dumps(container), encoding="utf-8")

    rc = run_pipeline(run_dir=run_dir)  # no ontology argument: heritagegraph is the default
    assert rc == 0

    from rdflib import Graph, Namespace, RDF
    hg = Namespace("https://cair-nepal.org/heritagegraph/")
    g = Graph().parse(str(ws.artifact_path(3)), format="turtle")
    assert (hg["struct-native-krishna"], RDF.type, hg.ArchitecturalStructure) in g

    report = json.loads(ws.artifact_path(4).read_text(encoding="utf-8"))
    assert report["conforms"] is True and report["vacuous"] is False
    assert report["shape_coverage"]["matched"]["ArchitecturalStructure"] == 1

    m = ws.load_manifest()
    assert m["status"] == "completed"
    assert m["summary"]["ontology"] == "heritagegraph"
    metrics = m["stages"]["stage_03_map"]["metrics"]
    assert metrics["mapping"] == "heritagegraph"
    assert metrics["schema_version"] == "1.0.1"
