import sys
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "01_heritage-extract" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from recognize_heritage import (
    scan_text_for_heritage_entities,
    tag_guthi_mentions,
    tag_architectural_styles,
    tag_calendar_dates,
    tag_religious_traditions
)


def test_tag_guthi_mentions():
    text = "The funeral rites were handled by the local Si Guthi, while the royal lands belong to the Raj Guthi."
    guthis = tag_guthi_mentions(text)
    assert len(guthis) == 2
    types = {g["enum_value"] for g in guthis}
    assert "SiGuthi" in types
    assert "RajGuthi" in types
    assert guthis[0]["target_collection"] == "guthis"


def test_tag_architectural_styles():
    text = "Nyatapola is a five-tiered pagoda temple, whereas Mahabouddha is built in the shikhara style."
    styles = tag_architectural_styles(text)
    assert len(styles) == 2
    enum_values = {s["enum_value"] for s in styles}
    assert "Pagoda" in enum_values
    assert "Shikhara" in enum_values


def test_tag_calendar_dates():
    text = "Inscribed in NS 822 during the reign of Bhupatindra Malla. Another record dates to VS 2015."
    dates = tag_calendar_dates(text)
    assert len(dates) == 2
    cals = {d["calendar_system"] for d in dates}
    assert "NepalSambat" in cals
    assert "BikramSambat" in cals
    assert dates[0]["numeric_year"] == 822
    assert dates[1]["numeric_year"] == 2015


def test_tag_religious_traditions():
    text = "A Vajrayana Buddhist vihara with syncretic Hindu shrines dedicated to Shiva and Vishnu."
    traditions = tag_religious_traditions(text)
    tags = {t["tradition"] for t in traditions}
    assert "Buddhist" in tags
    assert "Shaiva" in tags
    assert "Vaishnava" in tags


def test_scan_text_for_heritage_entities():
    sample = (
        "Nyatapola Temple in Bhaktapur is a multi-tiered pagoda constructed in NS 822. "
        "The annual rituals are conducted by the Siddhi Lakshmi Jatra Guthi during Bisket Jatra."
    )
    result = scan_text_for_heritage_entities(sample)
    assert len(result["guthis"]) >= 1
    assert result["guthis"][0]["enum_value"] == "JatraGuthi"
    assert len(result["architectural_styles"]) >= 1
    assert result["architectural_styles"][0]["enum_value"] == "Pagoda"
    assert len(result["dates"]) >= 1
    assert result["dates"][0]["calendar_system"] == "NepalSambat"
