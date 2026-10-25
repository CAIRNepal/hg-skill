#!/usr/bin/env python3
"""Validate an RDF graph against SHACL shapes with pySHACL.

Usage:
  validate.py [graph.ttl] [--run-dir DIR] --shapes SHAPES.ttl [--report report.json]
Exit code 0 = conforms, 1 = violations, 2 = could not run (bad input).
"""
import argparse
import json
import sys
from pathlib import Path

from pyshacl import validate
from rdflib import Graph, Namespace, RDF

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMON_DIR = REPO_ROOT / "skills" / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

try:
    from run_workspace import RunWorkspace
except ImportError:
    RunWorkspace = None

SH = Namespace("http://www.w3.org/ns/shacl#")


def short(term):
    s = str(term)
    for sep in ("#", "/"):
        if sep in s:
            return s.rsplit(sep, 1)[-1]
    return s


def main():
    ap = argparse.ArgumentParser(description="Validate an RDF graph against SHACL shapes.")
    ap.add_argument("graph", nargs="?", default=None, help="Path to graph Turtle file or run directory")
    ap.add_argument("--run-dir", default=None, help="Pipeline run directory")
    ap.add_argument("--shapes", default=None, help="Path to SHACL shapes file")
    ap.add_argument("--report", default=None, help="Path to output validation JSON report")
    args = ap.parse_args()

    ws = None
    graph_path = None
    report_path = None

    if args.run_dir or (args.graph and Path(args.graph).is_dir()):
        run_path = Path(args.run_dir if args.run_dir else args.graph)
        if RunWorkspace:
            try:
                ws = RunWorkspace.find(run_path)
            except Exception:
                ws = RunWorkspace(run_path)
            graph_path = ws.artifact_path(3)
            report_path = ws.artifact_path(4)
        else:
            graph_path = run_path / "03_graph.ttl"
            report_path = run_path / "04_shacl_report.json"
    elif args.graph:
        graph_path = Path(args.graph)
    else:
        ap.error("Must provide either graph file path or --run-dir")

    if args.report:
        report_path = Path(args.report)

    shapes_path = args.shapes
    if not shapes_path:
        default_shape = Path(__file__).resolve().parent.parent / "assets" / "shapes" / "HeritageGraph.shacl.ttl"
        if not default_shape.exists():
            default_shape = Path(__file__).resolve().parent.parent / "assets" / "shapes" / "cidoc-crm.shacl.ttl"
        if not default_shape.exists():
            default_shape = REPO_ROOT / "schemas" / "HeritageGraph.shacl.ttl"
        if default_shape.exists():
            shapes_path = str(default_shape)
        else:
            ap.error("the following arguments are required: --shapes")

    if not graph_path.exists():
        print(f"could not find graph file: {graph_path}", file=sys.stderr)
        return 2

    if ws:
        ws.record_stage_start(4, "validate", {"shapes": str(shapes_path), "graph": str(graph_path)})

    try:
        data = Graph().parse(str(graph_path), format="turtle")
        shapes = Graph().parse(str(shapes_path), format="turtle")
    except Exception as e:
        if ws:
            ws.record_stage_finish(4, "validate", status="failed", error=str(e))
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
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False)

    if ws:
        ws.record_stage_finish(
            4, "validate",
            status="success" if conforms else "violations",
            metrics={
                "conforms": bool(conforms),
                "triples": len(data),
                "violations_count": len(violations)
            }
        )

    if conforms:
        print(f"CONFORMS ({len(data)} triples checked)")
        return 0
    print(f"FAILS: {len(violations)} violation(s)")
    for v in violations:
        print(f"  - {v['focusNode']}  [{v['constraint']}]  {v['message']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
