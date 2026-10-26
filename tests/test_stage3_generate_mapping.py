"""Mapping generator CLI: HeritageGraph LinkML schema -> Stage 3 mapping (ticket #20)."""
import hashlib
import shutil
import sys
from pathlib import Path

import pytest
import yaml
from linkml_runtime.utils.schemaview import SchemaView

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE3_DIR = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "scripts"
SCHEMA = REPO_ROOT / "schemas" / "HeritageGraph.yaml"
COMMITTED = REPO_ROOT / "skills" / "03_heritage-rdf-mapper" / "assets" / "mappings" / "heritagegraph.yaml"

if str(STAGE3_DIR) not in sys.path:
    sys.path.insert(0, str(STAGE3_DIR))

from generate_mapping import main as gen_main  # noqa: E402


def run_gen(*args):
    orig = sys.argv
    try:
        sys.argv = ["generate_mapping"] + [str(a) for a in args]
        return gen_main()
    finally:
        sys.argv = orig


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("gen") / "heritagegraph.yaml"
    assert run_gen("--schema", SCHEMA, "--out", out) == 0
    return out


@pytest.fixture(scope="module")
def mapping(generated):
    return yaml.safe_load(generated.read_text(encoding="utf-8"))


def test_every_container_collection_is_covered(mapping):
    sv = SchemaView(str(SCHEMA))
    inherited = {s.name for s in sv.class_induced_slots("Entity")}
    expected = {
        s.name: s.range for s in sv.class_induced_slots("Container")
        if s.range in sv.all_classes() and s.multivalued and s.name not in inherited
    }
    assert set(mapping["container"]["collections"]) == set(expected)
    assert "was_derived_from" not in mapping["container"]["collections"]
    for col, rng in expected.items():
        assert mapping["container"]["collections"][col]["class"] == sv.get_uri(sv.get_class(rng), expand=False)


def test_class_and_slot_uris_match_the_ontology(mapping):
    structures = mapping["container"]["collections"]["structures"]
    assert structures["class"] == "heritageGraph:ArchitecturalStructure"
    slots = structures["slots"]
    assert slots["managed_by_guthi"] == {"p": "heritageGraph:managedByGuthi", "ref": True}
    assert slots["has_current_location"] == {"p": "crm:P55_has_current_location", "ref": True}
    assert slots["existence_status"]["p"] == "heritageGraph:existenceStatus"
    assert slots["existence_status"]["enum"] == "heritageGraph:ExistenceStatus"
    assert "Extant" in slots["existence_status"]["permissible_values"]
    assert slots["generated_at_time"] == {"p": "prov:generatedAtTime", "datatype": "xsd:dateTime"}
    assert slots["id"] == {"p": "dcterms:identifier", "datatype": "xsd:anyURI", "identity": True}
    assert slots["name"] == {"p": "rdfs:label"}


def test_every_used_prefix_is_declared(mapping):
    declared = set(mapping["prefixes"]) | {"rdf", "rdfs", "xsd", "skos", "dcterms"}
    for cfg in mapping["container"]["collections"].values():
        assert cfg["class"].split(":")[0] in declared
        for slot in cfg["slots"].values():
            assert slot["p"].split(":")[0] in declared
            for key in ("datatype", "enum"):
                if key in slot:
                    assert slot[key].split(":")[0] in declared


def test_regeneration_is_idempotent(generated, tmp_path):
    again = tmp_path / "again.yaml"
    assert run_gen("--schema", SCHEMA, "--out", again) == 0
    assert again.read_bytes() == generated.read_bytes()


def test_committed_mapping_is_fresh():
    assert run_gen("--schema", SCHEMA, "--out", COMMITTED, "--check") == 0


def test_header_records_schema_version_and_checksum(mapping):
    assert mapping["generated_from"]["schema_version"] == SchemaView(str(SCHEMA)).schema.version
    assert mapping["generated_from"]["sha256"] == hashlib.sha256(SCHEMA.read_bytes()).hexdigest()


def test_stale_mapping_is_detected(generated, tmp_path):
    changed = tmp_path / "HeritageGraph.yaml"
    shutil.copy(SCHEMA, changed)
    changed.write_text(changed.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
    assert run_gen("--schema", changed, "--out", generated, "--check") == 1


def test_overrides_can_change_or_suppress_rules(tmp_path):
    overrides = tmp_path / "overrides.yaml"
    overrides.write_text(yaml.safe_dump({
        "collections": {"structures": {"slots": {
            "note": {"p": "rdfs:comment"},
            "was_influenced_by": None,
        }}}
    }), encoding="utf-8")
    out = tmp_path / "m.yaml"
    assert run_gen("--schema", SCHEMA, "--overrides", overrides, "--out", out) == 0
    slots = yaml.safe_load(out.read_text(encoding="utf-8"))["container"]["collections"]["structures"]["slots"]
    assert slots["note"] == {"p": "rdfs:comment"}
    assert "was_influenced_by" not in slots
    assert "name" in slots
