"""Ids stay as URIs; Stage 2 links become skos:exactMatch (ticket #21), via the Stage 3 CLI."""
import json
import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import OWL, SKOS

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE3_DIR = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"
MAPPING = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "assets" / "mappings" / "heritagegraph.yaml"

for d in (STAGE3_DIR, COMMON_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from map_to_rdf import main as map_main  # noqa: E402

HG = Namespace("https://cair-nepal.org/heritagegraph/")
WD = "http://www.wikidata.org/entity/Q1234"
GETTY = "http://vocab.getty.edu/aat/300000001"

RESOLVED = {
    "id": "heritageGraph:batch-resolved-01",
    "guthis": [
        {"id": "heritageGraph:guthi-patan-kumbheshwor", "name": "Kumbheshwor Guthi",
         "resolution": {"uri": WD, "status": "linked", "source": "wikidata", "confidence": 0.95}},
        {"id": "heritageGraph:guthi-ambiguous", "name": "Dhaubahal Guthi",
         "resolution": {"uri": str(HG) + "group/dhaubahal-guthi", "status": "ambiguous", "source": "local-mint"}},
    ],
    "structures": [
        {"id": "heritageGraph:struct-kumbheshwor", "name": "Kumbheshwor Temple",
         "managed_by_guthi": ["heritageGraph:guthi-patan-kumbheshwor"],
         "resolution": {"uri": str(HG) + "structure/kumbheshwor-temple", "status": "local", "source": "local-mint"}},
    ],
    "materials": [
        {"id": "heritageGraph:material-brick", "name": "Brick",
         "resolution": {"uri": GETTY, "status": "linked", "source": "getty"}},
    ],
}


def run(tmp_path, data, capsys):
    src = tmp_path / "resolved.json"
    src.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "graph.ttl"
    orig = sys.argv
    try:
        sys.argv = ["map_to_rdf", str(src), "--mapping", str(MAPPING), "--base", str(HG), "--out", str(out)]
        assert map_main() == 0
    finally:
        sys.argv = orig
    report = json.loads(capsys.readouterr().out)
    return Graph().parse(str(out), format="turtle"), report


def test_linked_entity_keeps_its_id_and_gains_an_external_match(tmp_path, capsys):
    g, _ = run(tmp_path, RESOLVED, capsys)
    guthi = HG["guthi-patan-kumbheshwor"]
    assert (guthi, RDF.type, HG.Guthi) in g
    assert (guthi, SKOS.exactMatch, URIRef(WD)) in g
    # the external URI is only ever an object, never a typed subject
    assert not list(g.triples((URIRef(WD), None, None)))
    assert (HG["material-brick"], SKOS.exactMatch, URIRef(GETTY)) in g


def test_cross_references_resolve_to_heritagegraph_ids(tmp_path, capsys):
    g, _ = run(tmp_path, RESOLVED, capsys)
    struct = HG["struct-kumbheshwor"]
    targets = list(g.objects(struct, HG.managedByGuthi))
    assert targets == [HG["guthi-patan-kumbheshwor"]]
    assert (targets[0], RDF.type, HG.Guthi) in g


def test_ambiguous_entity_is_flagged_for_review(tmp_path, capsys):
    g, _ = run(tmp_path, RESOLVED, capsys)
    amb = HG["guthi-ambiguous"]
    assert any("needs human review" in str(c) for c in g.objects(amb, RDFS.comment))
    assert not list(g.objects(amb, SKOS.exactMatch))


def test_local_entity_has_no_match_or_review_flag(tmp_path, capsys):
    g, _ = run(tmp_path, RESOLVED, capsys)
    local = HG["struct-kumbheshwor"]
    assert not list(g.objects(local, SKOS.exactMatch))
    assert not list(g.objects(local, RDFS.comment))


def test_entity_counts_and_determinism(tmp_path, capsys):
    _, report = run(tmp_path, RESOLVED, capsys)
    assert report["entities"] == {"linked": 2, "local": 1, "ambiguous": 1}
    first = (tmp_path / "graph.ttl").read_bytes()
    run(tmp_path, RESOLVED, capsys)
    assert (tmp_path / "graph.ttl").read_bytes() == first


def test_graded_skos_and_identity_mappings(tmp_path, capsys):
    data = {
        "id": "heritageGraph:batch-resolved-graded",
        "guthis": [
            {"id": "heritageGraph:guthi-exact", "name": "Exact Guthi",
             "resolution": {"uri": "http://www.wikidata.org/entity/Q1", "status": "linked", "match_type": "exact"}},
            {"id": "heritageGraph:guthi-close", "name": "Close Guthi",
             "resolution": {"uri": "http://www.wikidata.org/entity/Q2", "status": "linked", "match_type": "close"}},
            {"id": "heritageGraph:guthi-broad", "name": "Broad Guthi",
             "resolution": {"uri": "http://www.wikidata.org/entity/Q3", "status": "linked", "match_type": "broad"}},
            {"id": "heritageGraph:guthi-narrow", "name": "Narrow Guthi",
             "resolution": {"uri": "http://www.wikidata.org/entity/Q4", "status": "linked", "match_type": "narrow"}},
            {"id": "heritageGraph:guthi-sameas", "name": "SameAs Guthi",
             "resolution": {"uri": "http://www.wikidata.org/entity/Q5", "status": "linked", "match_type": "sameAs"}},
        ]
    }
    g, _ = run(tmp_path, data, capsys)
    assert (HG["guthi-exact"], SKOS.exactMatch, URIRef("http://www.wikidata.org/entity/Q1")) in g
    assert (HG["guthi-close"], SKOS.closeMatch, URIRef("http://www.wikidata.org/entity/Q2")) in g
    assert (HG["guthi-broad"], SKOS.broadMatch, URIRef("http://www.wikidata.org/entity/Q3")) in g
    assert (HG["guthi-narrow"], SKOS.narrowMatch, URIRef("http://www.wikidata.org/entity/Q4")) in g
    assert (HG["guthi-sameas"], OWL.sameAs, URIRef("http://www.wikidata.org/entity/Q5")) in g

