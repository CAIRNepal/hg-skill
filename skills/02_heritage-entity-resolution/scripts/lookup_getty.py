#!/usr/bin/env python3
"""Look up candidate Getty URIs (AAT, ULAN, TGN) for a label via the Getty SPARQL endpoint.

Usage: lookup_getty.py "gilt bronze" --vocab aat [--limit 5]
Prints a JSON list of {uri, label, vocab}. Needs network access to vocab.getty.edu;
if the request fails it exits 2 with a message, so callers never fall back to guessing URIs.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

ENDPOINT = "https://vocab.getty.edu/sparql.json"
VOCABS = {"aat": "aat", "ulan": "ulan", "tgn": "tgn"}


def query(label, vocab, limit):
    safe = label.replace("\\", "\\\\").replace('"', '\\"')
    return f"""
PREFIX luc: <http://www.ontotext.com/owlim/lucene#>
PREFIX gvp: <http://vocab.getty.edu/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?s ?label WHERE {{
  ?s luc:term "{safe}" ;
     a gvp:Subject ;
     skos:inScheme <http://vocab.getty.edu/{VOCABS[vocab]}/> ;
     gvp:prefLabelGVP/skos:prefLabel ?label .
}} LIMIT {int(limit)}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--vocab", choices=VOCABS, default="aat")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": query(args.label, args.vocab, args.limit)})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/sparql-results+json"}), timeout=20) as r:
            rows = json.load(r)["results"]["bindings"]
    except Exception as e:  # network blocked, timeout, endpoint change
        print(f"lookup failed: {e}", file=sys.stderr)
        return 2
    out = [{"uri": b["s"]["value"], "label": b["label"]["value"], "vocab": args.vocab} for b in rows]
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
