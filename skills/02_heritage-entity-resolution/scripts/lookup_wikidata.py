#!/usr/bin/env python3
"""Look up candidate Wikidata entities for a label.

Usage: lookup_wikidata.py "Patan" [--lang en] [--limit 5]
Prints a JSON list of {uri, label, description}. Needs network access to wikidata.org;
on failure exits 2 so callers do not fall back to remembered (possibly invented) ids.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

API = "https://www.wikidata.org/w/api.php"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()
    params = {"action": "wbsearchentities", "search": args.label, "language": args.lang,
              "limit": args.limit, "format": "json"}
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "heritage-rdf-skills/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            hits = json.load(r).get("search", [])
    except Exception as e:
        print(f"lookup failed: {e}", file=sys.stderr)
        return 2
    out = [{"uri": f"http://www.wikidata.org/entity/{h['id']}", "label": h.get("label"),
            "description": h.get("description")} for h in hits]
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
