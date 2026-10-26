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
HG_NS = "https://cair-nepal.org/heritagegraph/"


def short(term):
    s = str(term)
    for sep in ("#", "/"):
        if sep in s:
            return s.rsplit(sep, 1)[-1]
    return s


def shape_coverage(data, shapes):
    """How many data nodes each targetClass shape actually matched. A shape that matches nothing
    validated nothing, so coverage is what makes a CONFORMS verdict meaningful."""
    typed = {}
    for s, o in data.subject_objects(RDF.type):
        typed.setdefault(o, set()).add(s)
    targets = {}
    for shape, cls in shapes.subject_objects(SH.targetClass):
        targets.setdefault(shape, set()).update(typed.get(cls, set()))
    matched = {short(shape): len(nodes) for shape, nodes in targets.items() if nodes}
    return {
        "shapes_total": len(targets),
        "shapes_matched": len(matched),
        "matched": dict(sorted(matched.items())),
    }


def main():
    ap = argparse.ArgumentParser(description="Validate an RDF graph against SHACL shapes.")
    ap.add_argument("graph", nargs="?", default=None, help="Path to graph Turtle file or run directory")
    ap.add_argument("--run-dir", default=None, help="Pipeline run directory")
    ap.add_argument("--shapes", default=None, help="Path to SHACL shapes file")
    ap.add_argument("--report", default=None, help="Path to output validation JSON report")
    ap.add_argument("--allow-crm-only", action="store_true",
                    help="Accept a graph with no heritageGraph: instances (CIDOC-CRM alternate mapping)")
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

    coverage = shape_coverage(data, shapes)
    hg_instances = sum(1 for _, o in data.subject_objects(RDF.type) if str(o).startswith(HG_NS))
    vacuous = coverage["shapes_matched"] == 0 or (hg_instances == 0 and not args.allow_crm_only)
    conforms = bool(conforms) and not vacuous

    summary = {
        "conforms": conforms, "vacuous": vacuous, "triples": len(data),
        "heritagegraph_instances": hg_instances, "shape_coverage": coverage,
        "violations": violations,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False)

    if ws:
        ws.record_stage_finish(
            4, "validate",
            status="success" if conforms else "violations",
            metrics={
                "conforms": conforms,
                "vacuous": vacuous,
                "triples": len(data),
                "violations_count": len(violations),
                "shapes_matched": coverage["shapes_matched"],
            }
        )

    if conforms:
        print(f"CONFORMS ({len(data)} triples checked, {coverage['shapes_matched']} shapes matched)")
        return 0
    if vacuous:
        print("FAILS: vacuous graph - no heritageGraph: instances matched any shape; "
              "nothing was validated (use --allow-crm-only for the CIDOC-CRM alternate mapping)")
        return 1
    print(f"FAILS: {len(violations)} violation(s)")
    for v in violations:
        print(f"  - {v['focusNode']}  [{v['constraint']}]  {v['message']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
