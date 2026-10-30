#!/usr/bin/env python3
"""Look up candidate Yale LUX URIs for cultural heritage concepts, places, agents, and objects.

Queries Yale LUX Search API via the `luxy` wrapper if installed, with native urllib
fallback. Outputs JSON candidate list: {uri, label, source, description, confidence}.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List

LUX_SEARCH_API = "https://lux.collections.yale.edu/api/search/"

LUX_ENDPOINT_MAP = {
    "concept": "concept",
    "material": "concept",
    "technique": "concept",
    "deity": "concept",
    "place": "place",
    "person": "agent",
    "group": "agent",
    "actor": "agent",
    "object": "item",
    "structure": "item",
    "work": "work",
}


def _luxy_search(label: str, endpoint: str, limit: int = 5, timeout: int = 10) -> List[Dict[str, Any]]:
    """Query using the luxy python package if available."""
    try:
        import luxy
    except ImportError:
        return []

    cls_map = {
        "concept": luxy.Concepts,
        "place": luxy.Places,
        "agent": luxy.PeopleGroups,
        "item": luxy.Objects,
        "work": luxy.Works,
    }
    factory = cls_map.get(endpoint)
    if not factory:
        return []

    try:
        client = factory()
        res = client.filter(name=label).get()
        items = res.json.get("orderedItems", [])[:limit]
        out = []
        for it in items:
            uri = it.get("id")
            if not uri:
                continue
            # Try to get detailed label, fallback to item or label
            lbl = label
            desc = it.get("type", endpoint)
            try:
                detailed = res.get_item_data(it)
                lbl = detailed.get("_label") or lbl
                desc = detailed.get("type") or desc
            except Exception:
                pass

            out.append({
                "uri": uri,
                "label": lbl,
                "source": "lux",
                "description": desc,
                "confidence": 0.85,
            })
        return out
    except Exception:
        return []


def _http_search(label: str, endpoint: str, limit: int = 5, timeout: int = 10) -> List[Dict[str, Any]]:
    """Native HTTP fallback querying the Yale LUX Search REST API."""
    query_obj = {"AND": [{"name": label}]}
    params = {"q": json.dumps(query_obj)}
    url = f"{LUX_SEARCH_API}{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "heritage-rdf-skills/0.1",
            "Accept": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.load(r)
    ordered = payload.get("orderedItems", [])[:limit]
    out = []
    for it in ordered:
        uri = it.get("id")
        if not uri:
            continue
        out.append({
            "uri": uri,
            "label": it.get("_label") or label,
            "source": "lux",
            "description": it.get("type", endpoint),
            "confidence": 0.85,
        })
    return out


def query_lux(label: str, kind: str = "concept", limit: int = 5, timeout: int = 10) -> List[Dict[str, Any]]:
    """Query Yale LUX for candidates matching label and entity kind."""
    endpoint = LUX_ENDPOINT_MAP.get(kind.lower(), "concept")
    # Try luxy wrapper first
    hits = _luxy_search(label, endpoint=endpoint, limit=limit, timeout=timeout)
    if hits:
        return hits
    # Fallback to direct HTTP search
    try:
        return _http_search(label, endpoint=endpoint, limit=limit, timeout=timeout)
    except Exception as e:
        return []


def main():
    ap = argparse.ArgumentParser(description="Query Yale LUX Search API for candidate heritage records.")
    ap.add_argument("label", help="Search label or name")
    ap.add_argument("--kind", default="concept", choices=list(LUX_ENDPOINT_MAP.keys()), help="Entity kind")
    ap.add_argument("--limit", type=int, default=5, help="Max candidates")
    args = ap.parse_args()

    candidates = query_lux(args.label, kind=args.kind, limit=args.limit)
    print(json.dumps(candidates, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
