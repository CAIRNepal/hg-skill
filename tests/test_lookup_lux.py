"""Tests for Yale LUX candidate lookup and integration into Stage 2 entity resolution."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE2_DIR = REPO_ROOT / "skills" / "02_heritage-entity-resolution" / "scripts"
COMMON_DIR = REPO_ROOT / "skills" / "common"

for d in (STAGE2_DIR, COMMON_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from lookup_lux import query_lux, LUX_ENDPOINT_MAP
from resolve_entities import fetch_candidates, resolve_container_entities


def test_lux_endpoint_map_coverage():
    assert "concept" in LUX_ENDPOINT_MAP
    assert "place" in LUX_ENDPOINT_MAP
    assert "person" in LUX_ENDPOINT_MAP
    assert "object" in LUX_ENDPOINT_MAP
    assert "material" in LUX_ENDPOINT_MAP


def test_query_lux_mocked():
    mock_item = {
        "id": "https://lux.collections.yale.edu/data/concept/mock-1234",
        "type": "Type",
        "_label": "Gilt bronze",
        "classified_as": [{"_label": "material"}]
    }
    
    mock_luxy_res = MagicMock()
    mock_luxy_res.json = {"orderedItems": [{"id": mock_item["id"], "type": "Type"}]}
    mock_luxy_res.get_item_data.return_value = mock_item

    with patch("lookup_lux._luxy_search", return_value=[{
        "uri": mock_item["id"],
        "label": mock_item["_label"],
        "source": "lux",
        "description": "Type",
        "confidence": 0.85,
    }]):
        hits = query_lux("gilt bronze", kind="material", limit=2)
        assert len(hits) == 1
        assert hits[0]["uri"] == "https://lux.collections.yale.edu/data/concept/mock-1234"
        assert hits[0]["label"] == "Gilt bronze"
        assert hits[0]["source"] == "lux"


def test_fetch_candidates_includes_lux(monkeypatch):
    mock_lux_hits = [
        {
            "uri": "https://lux.collections.yale.edu/data/concept/test-wood",
            "label": "Wood carving",
            "source": "lux",
            "description": "Technique",
            "confidence": 0.85,
        }
    ]
    monkeypatch.setattr("lookup_lux.query_lux", lambda *args, **kwargs: mock_lux_hits)
    # Also mock wikidata and getty to return empty
    monkeypatch.setattr("lookup_wikidata.query_wikidata", lambda *args, **kwargs: [])
    monkeypatch.setattr("lookup_getty.query_getty", lambda *args, **kwargs: [])

    candidates = fetch_candidates(label="Wood carving", kind="technique", query_network=True)
    assert any(c["uri"] == "https://lux.collections.yale.edu/data/concept/test-wood" and c["source"] == "lux" for c in candidates)
