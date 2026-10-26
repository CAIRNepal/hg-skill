"""Stage 3 Container-walking mapper, driven through the Stage 3 CLI (ticket #19)."""
import json
import sys
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import XSD

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE3_DIR = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"
MAPPING = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "assets" / "mappings" / "heritagegraph.yaml"
GOLDEN = REPO_ROOT / "tests" / "golden" / "stage3_structure.ttl"

for d in (STAGE3_DIR, COMMON_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from map_to_rdf import main as map_main  # noqa: E402

HG = Namespace("https://cair-nepal.org/heritagegraph/")

CONTAINER = {
    "id": "heritageGraph:batch-golden-01",
    "structures": [
        {
            "id": "heritageGraph:struct-krishna-mandir",
            "name": "कृष्ण मन्दिर (Krishna Mandir)",
            "note": "Stone temple in Patan Durbar Square",
            "existence_status": "Extant",
            "has_current_location": "heritageGraph:place-patan",
        }
    ],
}


def run_cli(args):
    orig = sys.argv
    try:
        sys.argv = ["map_to_rdf"] + [str(a) for a in args]
        return map_main()
    finally:
        sys.argv = orig


@pytest.fixture
def container_file(tmp_path):
    p = tmp_path / "container.json"
    p.write_text(json.dumps(CONTAINER, ensure_ascii=False), encoding="utf-8")
    return p


def map_container(container_file, out, *extra):
    return run_cli([container_file, "--mapping", MAPPING, "--base", str(HG), "--out", out, *extra])


def test_structure_is_typed_with_heritagegraph_class(container_file, tmp_path):
    out = tmp_path / "graph.ttl"
    assert map_container(container_file, out) == 0

    g = Graph().parse(str(out), format="turtle")
    s = HG["struct-krishna-mandir"]
    assert (s, RDF.type, HG.ArchitecturalStructure) in g
    assert not any(str(o).startswith("http://www.cidoc-crm.org/cidoc-crm/E") for o in g.objects(s, RDF.type))
    assert (s, RDFS.label, Literal("कृष्ण मन्दिर (Krishna Mandir)")) in g
    assert (s, URIRef("http://www.cidoc-crm.org/cidoc-crm/P55_has_current_location"), HG["place-patan"]) in g
    assert (s, HG.existenceStatus, URIRef(str(HG) + "ExistenceStatus#Extant")) in g
    assert (s, URIRef("http://purl.org/dc/terms/identifier"),
            Literal(str(s), datatype=XSD.anyURI)) in g


def test_output_matches_golden_byte_for_byte(container_file, tmp_path):
    out = tmp_path / "graph.ttl"
    assert map_container(container_file, out) == 0
    assert out.read_bytes() == GOLDEN.read_bytes()


def test_output_is_deterministic(container_file, tmp_path):
    a, b = tmp_path / "a.ttl", tmp_path / "b.ttl"
    assert map_container(container_file, a) == 0
    assert map_container(container_file, b) == 0
    assert a.read_bytes() == b.read_bytes()


def test_unmapped_fields_are_reported_and_strict_fails(tmp_path, capsys):
    data = json.loads(json.dumps(CONTAINER))
    data["structures"][0]["mystery_field"] = "dropped?"
    src = tmp_path / "c.json"
    src.write_text(json.dumps(data), encoding="utf-8")

    out = tmp_path / "g.ttl"
    assert map_container(src, out) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["unmapped_fields"] == {"structures.mystery_field": 1}

    assert map_container(src, out, "--strict") == 1


def test_heritagegraph_is_the_default_mapping(container_file, tmp_path):
    out = tmp_path / "graph.ttl"
    assert run_cli([container_file, "--base", str(HG), "--out", out]) == 0
    g = Graph().parse(str(out), format="turtle")
    assert (HG["struct-krishna-mandir"], RDF.type, HG.ArchitecturalStructure) in g


def test_inlined_ref_extra_fields_are_reported_unmapped(tmp_path, capsys):
    data = json.loads(json.dumps(CONTAINER))
    data["structures"][0]["has_current_location"] = {
        "id": "heritageGraph:place-patan",
        "extra_field": "not_triplified",
    }
    src = tmp_path / "inlined_extra.json"
    src.write_text(json.dumps(data), encoding="utf-8")

    out = tmp_path / "out.ttl"
    assert map_container(src, out) == 0
    report = json.loads(capsys.readouterr().out)
    assert "structures.has_current_location.extra_field" in report["unmapped_fields"]


def test_items_missing_id_and_unknown_collections_are_reported_unmapped(tmp_path, capsys):
    data = json.loads(json.dumps(CONTAINER))
    data["structures"].append({"name": "No ID Temple", "note": "Orphan"})
    data["unknown_collection"] = [{"id": "heritageGraph:x1", "label": "Dropped"}]
    src = tmp_path / "missing_id.json"
    src.write_text(json.dumps(data), encoding="utf-8")

    out = tmp_path / "out.ttl"
    assert map_container(src, out) == 0
    report = json.loads(capsys.readouterr().out)
    unmapped = report["unmapped_fields"]
    assert "structures._missing_id" in unmapped
    assert "structures.name" in unmapped
    assert "unknown_collection.id" in unmapped
    assert "unknown_collection.label" in unmapped


def test_invalid_enum_value_does_not_crash_and_is_reported_unmapped(tmp_path, capsys):
    data = json.loads(json.dumps(CONTAINER))
    # 'Partially Extant' contains a space and is not a permissible value (PartiallyExtant is)
    data["structures"][0]["existence_status"] = "Partially Extant"
    src = tmp_path / "invalid_enum.json"
    src.write_text(json.dumps(data), encoding="utf-8")

    out = tmp_path / "out.ttl"
    # Should not crash on serialize, exit 0 without --strict, and report existence_status in unmapped
    assert map_container(src, out) == 0
    report = json.loads(capsys.readouterr().out)
    assert "structures.existence_status" in report["unmapped_fields"]

    g = Graph().parse(str(out), format="turtle")
    s = HG["struct-krishna-mandir"]
    assert not list(g.objects(s, HG.existenceStatus))
    assert map_container(src, out, "--strict") == 1

