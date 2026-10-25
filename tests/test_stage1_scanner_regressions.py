"""Regression tests for recognize_heritage.py, written from the code review findings."""
import sys
from pathlib import Path

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "01_heritage-extract" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from recognize_heritage import (
    ARCHITECTURAL_STYLE_PATTERNS,
    GUTHI_PATTERNS,
    scan_text_for_heritage_entities,
    tag_architectural_styles,
    tag_calendar_dates,
    tag_eras,
    tag_guthi_mentions,
)


def test_generic_guthi_requires_capitalized_name_and_has_no_enum():
    assert tag_guthi_mentions("the funeral guthi and our local guthi") == []
    found = tag_guthi_mentions("Managed by the Siddhi Lakshmi Guthi.")
    assert len(found) == 1
    assert found[0]["enum_value"] is None
    assert found[0]["name_hint"] == "Siddhi Lakshmi"


def test_sentence_initial_article_is_not_part_of_name():
    found = tag_guthi_mentions("The Siddhi Guthi maintains the shrine.")
    assert found[0]["name_hint"] == "Siddhi"
    assert found[0]["matched_text"] == "Siddhi Guthi"


def test_specific_guthi_keeps_name_hint():
    found = tag_guthi_mentions("Run by the Siddhi Lakshmi Jatra Guthi each year.")
    assert len(found) == 1
    assert found[0]["enum_value"] == "JatraGuthi"
    assert found[0]["name_hint"] == "Siddhi Lakshmi"


def test_lowercase_abbreviations_are_not_calendar_dates():
    assert tag_calendar_dates("ns 5 and ss 1624 and bs 12") == []


def test_saka_and_iso_bounds():
    dates = {d["calendar_system"]: d for d in tag_calendar_dates("Saka 1624, 12 BCE and 1702 CE")}
    assert dates["ShakaSambat"]["numeric_year"] == 1624
    assert dates["ShakaSambat"]["iso_bounds"] is None
    assert dates["CommonEra"]["iso_bounds"] == {"earliest": "1702", "latest": "1702"}
    assert dates["BeforeCommonEra"]["iso_bounds"]["earliest"] == "-0012"


def test_sambat_paired_only_when_text_states_ce_year():
    paired = tag_calendar_dates("Built in NS 822 (1702 CE).")[0]
    assert paired["calendar_system"] == "NepalSambat"
    assert paired["iso_bounds"] == {"earliest": "1702", "latest": "1702"}

    dates = tag_calendar_dates("Built in NS 822. Later, 1850 CE.")
    unpaired = next(d for d in dates if d["calendar_system"] == "NepalSambat")
    assert unpaired["iso_bounds"] is None


def test_dome_suppressed_in_stupa_sentence_but_kept_elsewhere():
    assert {s["enum_value"] for s in tag_architectural_styles("The stupa has a large dome.")} == {"Stupa"}
    mixed = tag_architectural_styles("A stupa stands here. The hall has a dome.")
    assert {s["enum_value"] for s in mixed} == {"Stupa", "Dome"}


def test_every_style_occurrence_reported():
    styles = tag_architectural_styles("One pagoda here. Another pagoda there.")
    assert [s["enum_value"] for s in styles] == ["Pagoda", "Pagoda"]


def test_eras_detected():
    eras = {e["era"] for e in tag_eras("Licchavi inscriptions, Malla kings, and the Shah dynasty.")}
    assert eras == {"Licchavi", "Malla", "Shah"}


def test_unified_candidate_shape():
    result = scan_text_for_heritage_entities("The Pagoda of Si Guthi, NS 822, Buddhist, Malla period.")
    for key in ("guthis", "architectural_styles", "dates", "eras", "traditions"):
        assert result[key], key
        for cand in result[key]:
            assert {"category", "matched_text", "span", "context", "target_collection"} <= cand.keys()


def test_vocabularies_come_from_schema():
    schema = Path(__file__).resolve().parent.parent / "schemas" / "HeritageGraph.yaml"
    enums = yaml.safe_load(schema.read_text(encoding="utf-8"))["enums"]
    assert {g[0] for g in GUTHI_PATTERNS} == set(enums["GuthiType"]["permissible_values"])
    assert {s[0] for s in ARCHITECTURAL_STYLE_PATTERNS} == set(enums["ArchitecturalStyle"]["permissible_values"])
