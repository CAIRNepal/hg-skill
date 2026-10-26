"""Stage 4 must not pass vacuously and must report per-shape coverage (ticket #22)."""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE3_DIR = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "scripts"
STAGE4_DIR = REPO_ROOT / "skills" / "04_heritage-shacl-validate" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"
MAPPING = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "assets" / "mappings" / "heritagegraph.yaml"
BASE = "https://cair-nepal.org/heritagegraph/"

for d in (STAGE3_DIR, STAGE4_DIR, COMMON_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from map_to_rdf import main as map_main  # noqa: E402
from validate import main as validate_main  # noqa: E402

CONTAINER = {
    "id": "heritageGraph:batch-s4-01",
    "places": [{"id": "heritageGraph:place-patan", "name": "Patan"}],
    "guthis": [{"id": "heritageGraph:guthi-x", "name": "X Guthi"}],
    "structures": [{
        "id": "heritageGraph:struct-k", "name": "Krishna Mandir", "existence_status": "Extant",
        "has_current_location": "heritageGraph:place-patan",
        "managed_by_guthi": ["heritageGraph:guthi-x"],
    }],
}


def cli(fn, *args):
    orig = sys.argv
    try:
        sys.argv = ["x"] + [str(a) for a in args]
        return fn()
    finally:
        sys.argv = orig


def mapped_graph(tmp_path):
    src = tmp_path / "container.json"
    src.write_text(json.dumps(CONTAINER), encoding="utf-8")
    out = tmp_path / "graph.ttl"
    assert cli(map_main, src, "--mapping", MAPPING, "--base", BASE, "--out", out) == 0
    return out


def test_mapped_graph_conforms_and_reports_coverage(tmp_path):
    graph = mapped_graph(tmp_path)
    report = tmp_path / "report.json"
    assert cli(validate_main, graph, "--report", report) == 0

    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["conforms"] is True
    cov = data["shape_coverage"]
    assert cov["shapes_total"] > cov["shapes_matched"] > 0
    assert cov["matched"]["ArchitecturalStructure"] == 1
    assert cov["matched"]["Guthi"] == 1
    assert data["heritagegraph_instances"] == 2


def test_graph_without_heritagegraph_instances_fails(tmp_path, capsys):
    graph = tmp_path / "empty.ttl"
    graph.write_text(
        '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n'
        '<https://example.org/x> rdfs:label "just a label" .\n',
        encoding="utf-8",
    )
    report = tmp_path / "report.json"
    assert cli(validate_main, graph, "--report", report) == 1

    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["conforms"] is False
    assert data["vacuous"] is True
    assert data["heritagegraph_instances"] == 0
    assert "heritageGraph:" in capsys.readouterr().out


def test_crm_only_graph_needs_explicit_opt_in(tmp_path):
    graph = tmp_path / "crm.ttl"
    graph.write_text(
        '@prefix crm: <http://www.cidoc-crm.org/cidoc-crm/> .\n'
        '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n'
        '<https://example.org/o> a crm:E22_Human-Made_Object ; rdfs:label "obj" .\n',
        encoding="utf-8",
    )
    assert cli(validate_main, graph, "--report", tmp_path / "a.json") == 1
    cli(validate_main, graph, "--report", tmp_path / "b.json", "--allow-crm-only")
    data = json.loads((tmp_path / "b.json").read_text(encoding="utf-8"))
    assert data["vacuous"] is False
