#!/usr/bin/env python3
"""Deterministically map resolved heritage records to RDF using a YAML mapping.

Usage:
  map_to_rdf.py resolved.json --mapping MAPPING.yaml --base https://example.org/heritage/ --out graph.ttl [--strict]

Same input + same mapping + same base always gives the same triples: node URIs are derived
from record ids and node names, never from random ids or blank-node labels.
Prints a JSON report (records, triples, entity counts, unmapped fields).
With --strict, exits 1 if any non-empty record field is not covered by a rule.
"""
import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path

import yaml
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, SKOS, XSD

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMON_DIR = REPO_ROOT / "skills" / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

try:
    from run_workspace import RunWorkspace
except ImportError:
    RunWorkspace = None

BUILTIN_PREFIXES = {
    "rdf": str(RDF), "rdfs": str(RDFS), "xsd": str(XSD), "skos": str(SKOS), "dcterms": str(DCTERMS),
}


def slugify(text):
    """Stable, URI-safe slug that keeps non-Latin scripts (letters, marks, numbers only)."""
    text = unicodedata.normalize("NFC", str(text)).casefold().strip()
    kept = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch.isspace():
            kept.append("-")
        elif cat[0] in "LMN" or ch == "-":
            kept.append(ch)
    slug = re.sub(r"-+", "-", "".join(kept)).strip("-")
    return urllib.parse.quote(slug or "unnamed", safe="-")


class Mapper:
    def __init__(self, mapping, base, language=None):
        self.m = mapping
        self.base = base if base.endswith("/") else base + "/"
        self.language = language
        self.g = Graph()
        self.prefixes = {**BUILTIN_PREFIXES, **mapping.get("prefixes", {})}
        for p, ns in self.prefixes.items():
            self.g.bind(p, Namespace(ns))
        self.counts = {"linked": 0, "local": 0, "ambiguous": 0}

    # -- helpers ---------------------------------------------------------
    def q(self, qname):
        prefix, _, local = qname.partition(":")
        if prefix not in self.prefixes:
            raise KeyError(f"unknown prefix '{prefix}' in '{qname}'")
        return URIRef(self.prefixes[prefix] + local)

    def local_uri(self, kind, label):
        return URIRef(f"{self.base}{kind or 'other'}/{slugify(label)}")

    def entity(self, mention):
        """Return the URI node for a mention and add its type/label triples."""
        res = mention.get("resolution") or {}
        status = res.get("status") or ("linked" if res.get("uri") else "local")
        kind = mention.get("kind") or "other"
        if status == "linked" and res.get("uri"):
            node = URIRef(res["uri"])
        else:
            node = self.local_uri(kind, mention["label"])
            status = "ambiguous" if status == "ambiguous" else "local"
        self.counts[status] += 1
        classes = self.m.get("entity_classes", {})
        cls = classes.get(kind) or classes.get("other")
        if cls:
            self.g.add((node, RDF.type, self.q(cls)))
        label_prop = self.m.get("entity_label", "rdfs:label")
        self.g.add((node, self.q(label_prop), Literal(mention["label"], lang=self.language) if self.language else Literal(mention["label"])))
        if status == "ambiguous":
            self.g.add((node, RDFS.comment, Literal("Entity resolution was ambiguous; needs human review.")))
        return node

    def literal(self, value, step):
        dt = step.get("datatype")
        if dt == "auto":
            s = str(value)
            if re.fullmatch(r"-?\d{4}", s):
                return Literal(s, datatype=XSD.gYear)
            if re.fullmatch(r"-?\d{4}-\d{2}", s):
                return Literal(s, datatype=XSD.gYearMonth)
            if re.fullmatch(r"-?\d{4}-\d{2}-\d{2}", s):
                return Literal(s, datatype=XSD.date)
            return Literal(s)
        if dt:
            return Literal(str(value), datatype=self.q(dt))
        if step.get("lang") == "source" and self.language:
            return Literal(str(value), lang=self.language)
        return Literal(str(value))

    def node(self, rid, step, idx, value):
        name = step["node"]
        if step.get("global"):
            return URIRef(f"{self.base}{name}/{slugify(value)}")
        suffix = f"-{idx}" if step.get("per_item") else ""
        return URIRef(f"{self.base}node/{slugify(rid)}/{name}{suffix}")

    @staticmethod
    def values(rec, path):
        """Return [(value, idx)]. idx is the position in the first list met along the path
        (0 for non-lists), so rules over different subfields of one list item agree on idx."""
        vals = [(rec, None)]
        for part in path.split("."):
            nxt = []
            for v, idx in vals:
                if isinstance(v, dict) and v.get(part) is not None:
                    x = v[part]
                    if isinstance(x, list):
                        for i, item in enumerate(x):
                            nxt.append((item, i if idx is None else idx))
                    else:
                        nxt.append((x, idx))
            vals = nxt
        return [(v, 0 if idx is None else idx) for v, idx in vals]

    # -- main ------------------------------------------------------------
    def map_record(self, rec):
        rid = rec["id"]
        cfg = self.m["object"]
        obj = URIRef(self.base + cfg["uri"].format(id=slugify(rid)))
        self.g.add((obj, RDF.type, self.q(cfg["class"])))
        for comp in cfg.get("companions", []):
            c = URIRef(self.base + comp["uri"].format(id=slugify(rid)))
            self.g.add((c, RDF.type, self.q(comp["class"])))
            self.g.add((c, self.q(comp["p"]), obj))
        for rule in self.m.get("rules", []):
            for val, idx in self.values(rec, rule["field"]):
                if rule.get("value") and isinstance(val, dict):
                    val = val.get(rule["value"])
                if val is None or val == "":
                    continue
                subj = obj
                for step in rule["steps"]:
                    p = self.q(step["p"])
                    if step.get("literal"):
                        self.g.add((subj, p, self.literal(val, step)))
                    elif step.get("entity"):
                        self.g.add((subj, p, self.entity(val)))
                    else:
                        n = self.node(rid, step, idx, val)
                        self.g.add((subj, p, n))
                        if step.get("class"):
                            self.g.add((n, RDF.type, self.q(step["class"])))
                        subj = n

    # -- container mode (HeritageGraph-native) ---------------------------
    def expand(self, ident):
        """CURIE, absolute IRI or bare id -> URIRef (bare ids are minted under --base)."""
        s = str(ident)
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", s):
            return URIRef(s)
        prefix, _, local = s.partition(":")
        if local and prefix in self.prefixes:
            return URIRef(self.prefixes[prefix] + local)
        return URIRef(self.base + slugify(s))

    def container_literal(self, value, slot):
        dt = slot.get("datatype")
        if isinstance(value, bool):
            value = "true" if value else "false"
        # No language tags: HeritageGraph shapes demand xsd:string, and rdf:langString fails them.
        return Literal(str(value), datatype=self.q(dt)) if dt else Literal(str(value))

    def container_values(self, item, key):
        v = item.get(key)
        if v is None or v == "":
            return []
        return v if isinstance(v, list) else [v]

    def map_container(self, data):
        """Walk the Container's collections in mapping order. Returns the mapped items."""
        mapped = []
        collections = self.m["container"]["collections"]
        for col, cfg in collections.items():
            items = data.get(col)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                mapped.append((col, item))
                subj = self.expand(item["id"])
                self.g.add((subj, RDF.type, self.q(cfg["class"])))
                for key, slot in cfg.get("slots", {}).items():
                    p = self.q(slot["p"])
                    for val in self.container_values(item, key):
                        if key == "id":
                            val = str(subj)
                        if slot.get("ref"):
                            ref = val.get("id") if isinstance(val, dict) else val
                            if ref:
                                self.g.add((subj, p, self.expand(ref)))
                        elif slot.get("enum"):
                            self.g.add((subj, p, URIRef(f"{self.q(slot['enum'])}#{val}")))
                        else:
                            self.g.add((subj, p, self.container_literal(val, slot)))
        return mapped

    def container_unmapped(self, data):
        """Non-empty collection fields that no slot consumes, as 'collection.field' counts."""
        counts = {}
        for col, cfg in self.m["container"]["collections"].items():
            items = data.get(col)
            if not isinstance(items, list):
                continue
            covered = set(cfg.get("slots", {}))
            for item in items:
                if not isinstance(item, dict):
                    continue
                for path in self.leaves({k: v for k, v in item.items() if k not in ("resolution", "evidence")}):
                    if path.split(".")[0] in covered:
                        continue
                    key = f"{col}.{path}"
                    counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def leaves(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield from Mapper.leaves(v, f"{prefix}.{k}" if prefix else k)
        elif isinstance(obj, list):
            for v in obj:
                yield from Mapper.leaves(v, prefix)
        elif obj not in (None, ""):
            yield prefix

    def unmapped(self, records):
        """Non-empty field paths that no rule consumes, with counts. Silent data loss is the
        main risk of a declarative mapping, so every dropped field is reported."""
        covered = set()
        for r in self.m.get("rules", []):
            f = r["field"]
            if r["steps"][-1].get("entity"):
                covered.update({f + ".label", f + ".kind", f + ".context"})
            elif r.get("value"):
                covered.add(f + "." + r["value"])
            else:
                covered.add(f)
        counts = {}
        for rec in records:
            for path in self.leaves({k: v for k, v in rec.items() if k not in ("id", "evidence")}):
                if path in covered or ".resolution." in "." + path:
                    continue
                counts[path] = counts.get(path, 0) + 1
        return counts


def main():
    ap = argparse.ArgumentParser(description="Map resolved or extracted heritage records to RDF Turtle.")
    ap.add_argument("resolved", nargs="?", default=None, help="Path to resolved or extracted JSON file")
    ap.add_argument("--run-dir", default=None, help="Pipeline run directory")
    ap.add_argument("--mapping", default=None, help="Path to YAML mapping rules")
    ap.add_argument("--base", default="https://example.org/heritage/")
    ap.add_argument("--out", default=None, help="Path to output Turtle file (.ttl)")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    ws = None
    resolved_path = None
    out_path = None

    if args.run_dir or (args.resolved and Path(args.resolved).is_dir()):
        run_path = Path(args.run_dir if args.run_dir else args.resolved)
        if RunWorkspace:
            try:
                ws = RunWorkspace.find(run_path)
            except Exception:
                ws = RunWorkspace(run_path)
            p2 = ws.artifact_path(2)
            p1 = ws.artifact_path(1)
            resolved_path = p2 if p2.exists() else p1
            out_path = ws.artifact_path(3)
        else:
            p2 = run_path / "02_resolved.json"
            p1 = run_path / "01_extracted.json"
            resolved_path = p2 if p2.exists() else p1
            out_path = run_path / "03_graph.ttl"
    elif args.resolved:
        resolved_path = Path(args.resolved)
    else:
        ap.error("Must provide either input JSON path or --run-dir")

    if args.out:
        out_path = Path(args.out)
    elif not out_path:
        ap.error("the following arguments are required: --out (or specify --run-dir)")

    mapping_path = args.mapping
    if not mapping_path:
        default_map = Path(__file__).resolve().parent.parent / "assets" / "mappings" / "cidoc-crm.yaml"
        if default_map.exists():
            mapping_path = str(default_map)
        else:
            ap.error("the following arguments are required: --mapping")

    if not resolved_path.exists():
        print(f"Error: Input file not found: {resolved_path}", file=sys.stderr)
        return 1

    if ws:
        ws.record_stage_start(3, "map", {"mapping": str(mapping_path), "base": args.base, "input": str(resolved_path)})

    data = json.load(open(resolved_path, encoding="utf-8"))
    mapping = yaml.safe_load(open(mapping_path, encoding="utf-8"))
    language = (data.get("source") or {}).get("language")
    mapper = Mapper(mapping, args.base, language)
    if "container" in mapping:
        records = [item for _, item in mapper.map_container(data)]
        unmapped = mapper.container_unmapped(data)
    else:
        records = data.get("records")
        if records is None:
            records = []
            for col in [
                "structures", "human_made_objects", "iconographic_objects",
                "places", "guthis", "festivals", "ritual_events"
            ]:
                items = data.get(col, [])
                if isinstance(items, list):
                    records.extend(items)
        for rec in records:
            if isinstance(rec, dict) and "id" in rec:
                mapper.map_record(rec)
        unmapped = mapper.unmapped(records)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    mapper.g.serialize(destination=str(out_path), format="turtle")
    report = {
        "records": len(records),
        "triples": len(mapper.g),
        "entities": mapper.counts,
        "unmapped_fields": unmapped,
        "out": str(out_path)
    }
    if ws:
        ws.record_stage_finish(3, "map", status="success", metrics=report)

    print(json.dumps(report, indent=2))
    return 1 if (args.strict and unmapped) else 0


if __name__ == "__main__":
    sys.exit(main())
