#!/usr/bin/env python3
"""Validate an RDF graph against SHACL shapes with pySHACL.

Usage: validate.py graph.ttl --shapes SHAPES.ttl [--report report.json]
Exit code 0 = conforms, 1 = violations, 2 = could not run (bad input).
"""
import argparse
import json
import sys

from pyshacl import validate
from rdflib import Graph, Namespace, RDF

SH = Namespace("http://www.w3.org/ns/shacl#")


def short(term):
    s = str(term)
    for sep in ("#", "/"):
        if sep in s:
            return s.rsplit(sep, 1)[-1]
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("--shapes", required=True)
    ap.add_argument("--report")
    args = ap.parse_args()

    try:
        data = Graph().parse(args.graph, format="turtle")
        shapes = Graph().parse(args.shapes, format="turtle")
    except Exception as e:
        print(f"could not parse input: {e}", file=sys.stderr)
        return 2

    conforms, report_graph, _ = validate(data, shacl_graph=shapes, inference="none", advanced=True)

    violations = []
    for r in report_graph.subjects(RDF.type, SH.ValidationResult):
        def one(p):
            return next(report_graph.objects(r, p), None)
        violations.append({
            "focusNode": str(one(SH.focusNode)),
            "path": str(one(SH.resultPath)) if one(SH.resultPath) else None,
            "constraint": short(one(SH.sourceConstraintComponent)),
            "message": str(one(SH.resultMessage)) if one(SH.resultMessage) else None,
        })
    violations.sort(key=lambda v: (v["focusNode"], v["path"] or "", v["constraint"]))

    summary = {"conforms": bool(conforms), "triples": len(data), "violations": violations}
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False)

    if conforms:
        print(f"CONFORMS ({len(data)} triples checked)")
        return 0
    print(f"FAILS: {len(violations)} violation(s)")
    for v in violations:
        print(f"  - {v['focusNode']}  [{v['constraint']}]  {v['message']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
