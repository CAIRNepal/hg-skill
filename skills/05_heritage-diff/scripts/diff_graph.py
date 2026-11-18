#!/usr/bin/env python3
"""Stage 05 Diff & Deduplication Gate for HeritageGraph pipeline.

Compares a run's triplified graph (03_graph.ttl) against the local Oxigraph
mirror snapshot. Produces 05_diff_report.json categorizing:
  - new_entities: novel subjects minted in this run
  - existing_references: statements referencing existing mirror entities
  - suspected_duplicates: fuzzy label/type matches that were minted as new URIs

Returns exit code 1 if unreviewed suspected duplicates exist and --fail-on-duplicates
is set (default True).

Aligned with spec #36, closes #40.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pyoxigraph as ox

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMON_DIR = REPO_ROOT / "skills" / "common"
SRC_DIR = REPO_ROOT / "src"
STAGE2_DIR = REPO_ROOT / "skills" / "02_heritage-entity-resolution" / "scripts"

for d in (COMMON_DIR, SRC_DIR, STAGE2_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

try:
    from run_workspace import RunWorkspace
except ImportError:
    RunWorkspace = None

try:
    from hg.mirror import OxigraphMirror, load_mirror
except ImportError:
    from lookup_mirror import OxigraphMirror, load_mirror  # type: ignore

HG_BASE_URI = "https://cair-nepal.org/heritagegraph/"


def _load_run_graph(graph_path: Path) -> ox.Store:
    """Load a TTL/NT run graph into a pyoxigraph store."""
    store = ox.Store()
    ext = graph_path.suffix.lower()
    fmt_map = {
        ".ttl": ox.RdfFormat.TURTLE,
        ".nt": ox.RdfFormat.N_TRIPLES,
        ".nq": ox.RdfFormat.N_QUADS,
    }
    fmt = fmt_map.get(ext, ox.RdfFormat.TURTLE)
    store.load(path=str(graph_path), format=fmt)
    return store


def _get_hg_subjects(store: ox.Store) -> Set[str]:
    """Return the set of heritageGraph: subject URIs in a store."""
    subjects: Set[str] = set()
    for quad in store.quads_for_pattern(None, None, None):
        subj = quad.subject
        if isinstance(subj, ox.NamedNode) and subj.value.startswith(HG_BASE_URI):
            subjects.add(subj.value)
    return subjects


def _get_all_hg_object_refs(store: ox.Store) -> Set[str]:
    """Return heritageGraph: URIs appearing as objects in a store."""
    refs: Set[str] = set()
    for quad in store.quads_for_pattern(None, None, None):
        obj = quad.object
        if isinstance(obj, ox.NamedNode) and obj.value.startswith(HG_BASE_URI):
            refs.add(obj.value)
    return refs


def _get_label(store: ox.Store, uri: str) -> Optional[str]:
    """Get a label for a URI from the store (rdfs:label, skos:prefLabel, schema:name)."""
    label_preds = [
        "http://www.w3.org/2000/01/rdf-schema#label",
        "http://www.w3.org/2004/02/skos/core#prefLabel",
        "http://schema.org/name",
        f"{HG_BASE_URI}name",
    ]
    subject_node = ox.NamedNode(uri)
    for pred_uri in label_preds:
        pred_node = ox.NamedNode(pred_uri)
        for quad in store.quads_for_pattern(subject_node, pred_node, None):
            obj = quad.object
            if isinstance(obj, ox.Literal):
                return obj.value
    return None


def compute_diff(
    run_graph_path: Path,
    mirror: OxigraphMirror,
    resolved_json_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Compute the diff between a run's graph and the local KG mirror.

    Returns a dict with:
      - new_entities: list of URIs that are novel (not in mirror)
      - existing_references: list of URIs that exist in the mirror (reused/enriched)
      - suspected_duplicates: new URIs where a confident label match exists in mirror
      - counts: summary counts
    """
    if not run_graph_path.exists():
        raise FileNotFoundError(f"Run graph not found: {run_graph_path}")

    run_store = _load_run_graph(run_graph_path)
    run_subjects = _get_hg_subjects(run_store)
    run_obj_refs = _get_all_hg_object_refs(run_store)

    new_entities: List[Dict[str, Any]] = []
    existing_references: List[Dict[str, Any]] = []
    suspected_duplicates: List[Dict[str, Any]] = []

    # Classify each subject minted in this run
    for uri in sorted(run_subjects):
        if mirror.check_exact_uri(uri):
            existing_references.append({"uri": uri, "reason": "exact_uri_in_mirror"})
        else:
            label = _get_label(run_store, uri)
            new_entity_info: Dict[str, Any] = {"uri": uri, "label": label}

            # Check for fuzzy label match in mirror (suspected duplicate)
            if label:
                candidates = mirror.find_candidate_entities(label=label, limit=3)
                exact_cands = [c for c in candidates if c.get("match_type") == "exact"]
                close_cands = [c for c in candidates if c.get("score", 0) >= 0.85]

                if exact_cands or close_cands:
                    top_cands = (exact_cands or close_cands)[:3]
                    suspected_duplicates.append({
                        "uri": uri,
                        "label": label,
                        "candidates": top_cands,
                        "reason": "label_match_in_mirror",
                    })
                else:
                    new_entities.append(new_entity_info)
            else:
                new_entities.append(new_entity_info)

    # Also track object-level references to existing mirror entities
    for obj_uri in sorted(run_obj_refs - run_subjects):
        if mirror.check_exact_uri(obj_uri):
            existing_references.append({"uri": obj_uri, "reason": "object_ref_in_mirror"})

    # Deduplicate existing_references
    seen_existing: Set[str] = set()
    unique_existing: List[Dict[str, Any]] = []
    for ref in existing_references:
        if ref["uri"] not in seen_existing:
            unique_existing.append(ref)
            seen_existing.add(ref["uri"])

    return {
        "new_entities": new_entities,
        "existing_references": unique_existing,
        "suspected_duplicates": suspected_duplicates,
        "counts": {
            "new_entities": len(new_entities),
            "existing_references": len(unique_existing),
            "suspected_duplicates": len(suspected_duplicates),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stage 05: Diff run graph against local KG mirror snapshot."
    )
    ap.add_argument("graph", nargs="?", default=None, help="Path to 03_graph.ttl or run directory")
    ap.add_argument("--run-dir", default=None, help="Pipeline run directory")
    ap.add_argument("--mirror", required=True, help="Path to local KG mirror snapshot (.nt/.ttl) or store directory")
    ap.add_argument("--out", default=None, help="Path to write 05_diff_report.json")
    ap.add_argument(
        "--no-fail-on-duplicates",
        action="store_true",
        default=False,
        help="Do not exit with error code when suspected duplicates exist",
    )
    args = ap.parse_args(argv)

    # Resolve run directory and paths
    ws = None
    graph_path = None
    out_path = None
    resolved_path = None

    if args.run_dir or (args.graph and Path(args.graph).is_dir()):
        run_path = Path(args.run_dir if args.run_dir else args.graph)
        if RunWorkspace:
            try:
                ws = RunWorkspace.find(run_path)
            except Exception:
                ws = RunWorkspace(run_path)
            graph_path = ws.artifact_path(3)
            resolved_path = ws.artifact_path(2)
            out_path = ws.artifact_path(5) if hasattr(ws, "artifact_path") else run_path / "05_diff_report.json"
            # Fallback for artifact_path(5) if workspace only knows 4 stages
            try:
                ws.artifact_path(5)
            except Exception:
                out_path = run_path / "05_diff_report.json"
        else:
            graph_path = run_path / "03_graph.ttl"
            out_path = run_path / "05_diff_report.json"
    elif args.graph:
        graph_path = Path(args.graph)

    if not graph_path:
        ap.error("Must provide either 03_graph.ttl path or --run-dir")
    if args.out:
        out_path = Path(args.out)
    if not out_path:
        out_path = graph_path.parent / "05_diff_report.json"

    # Load mirror
    try:
        mirror = OxigraphMirror(args.mirror)
    except Exception as exc:
        print(f"Error loading mirror from {args.mirror}: {exc}", file=sys.stderr)
        return 1

    if ws:
        ws.record_stage_start(5, "diff", {"mirror": args.mirror, "graph": str(graph_path)})

    # Compute diff
    try:
        report = compute_diff(graph_path, mirror, resolved_json_path=resolved_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Write report
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    counts = report["counts"]
    print(
        f"Diff complete: {counts['new_entities']} new entities, "
        f"{counts['existing_references']} existing references, "
        f"{counts['suspected_duplicates']} suspected duplicates."
    )
    print(f"Report saved to: {out_path}")

    if ws:
        ws.record_stage_finish(5, "diff", status="success", metrics=counts)

    # Fail gate if unvetted duplicates exist
    n_dups = counts["suspected_duplicates"]
    if n_dups > 0 and not args.no_fail_on_duplicates:
        print(
            f"\nGATE FAILED: {n_dups} suspected duplicate(s) require human review "
            f"before contribution. Run with '--interactive' in Stage 2 to resolve them.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
