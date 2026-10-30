#!/usr/bin/env python3
"""Match mentions in extracted.json against internal gazetteer CSVs.

Gazetteer CSV columns: uri,label,alt_labels,kind,context  (alt_labels pipe-separated)

Usage: gazetteer_match.py extracted.json GAZETTEER_DIR_OR_CSV [--out matches.json]
Prints JSON: one entry per mention with exact matches and candidates.
Matching is case-insensitive and diacritic-folded; the original label is preserved.
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path


def fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def load_gazetteers(path):
    p = Path(path)
    files = sorted(p.glob("*.csv")) if p.is_dir() else [p]
    index = {}
    for f in files:
        with open(f, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                labels = [row["label"]] + [a for a in (row.get("alt_labels") or "").split("|") if a]
                match_type = row.get("match_type") or "exact"
                for lab in labels:
                    index.setdefault(fold(lab), []).append(
                        {"uri": row["uri"], "label": row["label"], "kind": row.get("kind", ""),
                         "context": row.get("context", ""), "gazetteer": f.name,
                         "match_type": match_type})
    return index


def mentions(data):
    if "records" in data and isinstance(data["records"], list):
        for rec in data["records"]:
            rid = rec["id"]
            groups = [("materials", rec.get("materials", [])), ("creators", rec.get("creators", []))]
            prod = rec.get("production") or {}
            if prod.get("place"):
                groups.append(("production.place", [prod["place"]]))
            if rec.get("current_location"):
                groups.append(("current_location", [rec["current_location"]]))
            for prov in rec.get("provenance", []):
                if prov.get("agent"):
                    groups.append(("provenance.agent", [prov["agent"]]))
            for field, items in groups:
                for m in items:
                    yield rid, field, m
        return

    # LinkML Container format
    kind_map = {
        "places": "place", "persons": "person", "actors": "group",
        "guthis": "group", "festivals": "event", "ritual_events": "event",
        "materials": "material", "techniques": "technique", "deities": "concept",
        "structures": "structure", "human_made_objects": "object", "iconographic_objects": "object"
    }
    for col, default_kind in kind_map.items():
        items = data.get(col, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    iid = item.get("id", "unnamed")
                    label = item.get("name") or item.get("label")
                    if label:
                        context = item.get("note") or item.get("description") or ""
                        yield iid, col, {"label": label, "kind": default_kind, "context": context}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("extracted")
    ap.add_argument("gazetteers")
    ap.add_argument("--out")
    args = ap.parse_args()

    data = json.load(open(args.extracted, encoding="utf-8"))
    index = load_gazetteers(args.gazetteers)
    results = []
    for rid, field, m in mentions(data):
        hits = index.get(fold(m["label"]), [])
        kind = m.get("kind")
        same_kind = [dict(h) for h in hits if not kind or not h["kind"] or h["kind"] == kind]  # copies: the index is shared across mentions
        # Context overlap: shared words between the mention's context and each candidate's.
        words = set(re.findall(r"\w+", fold(m.get("context") or "")))
        for h in same_kind:
            h["context_overlap"] = len(words & set(re.findall(r"\w+", fold(h["context"]))))
        if len(same_kind) == 1:
            status = "exact"
        elif len(same_kind) > 1:
            top = max(h["context_overlap"] for h in same_kind)
            leaders = [h for h in same_kind if h["context_overlap"] == top]
            # Only a unique, non-zero leader counts; a tie or no context stays ambiguous for the agent to judge.
            status = "context_match" if top > 0 and len(leaders) == 1 else "ambiguous"
        else:
            status = "none"
        results.append({"record": rid, "field": field, "label": m["label"], "kind": kind,
                        "context": m.get("context"), "status": status, "candidates": same_kind})
    out = json.dumps(results, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
