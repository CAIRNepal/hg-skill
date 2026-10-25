#!/usr/bin/env python3
"""Validate stage-1 output against extraction.schema.json plus semantic referential checks.

Derived directly from the LinkML Container schema definition:
- Validates structural conformity using Draft202012Validator.
- Dynamically discovers all Container collections from the schema properties.
- Checks unique entity CURIEs (enforcing canonical 'heritageGraph:' prefix).
- Verifies referential integrity across single and multi-valued entity links.

Usage: validate_extraction.py extracted.json [--schema PATH]
Exit code 0 = valid, 1 = errors found.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Set, Tuple

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMON_DIR = REPO_ROOT / "skills" / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

try:
    from run_workspace import RunWorkspace
except ImportError:
    RunWorkspace = None

DEFAULT_SCHEMA = Path(__file__).resolve().parent.parent / "assets" / "extraction.schema.json"


def get_schema_collections(schema: Dict[str, Any]) -> List[str]:
    """Dynamically discover collection slot names from Container schema properties."""
    collections = []
    for prop_name, prop_spec in schema.get("properties", {}).items():
        if isinstance(prop_spec, dict):
            ptype = prop_spec.get("type", [])
            if "array" in ptype or ptype == "array":
                collections.append(prop_name)
    return sorted(collections)


def extract_entities(data: Dict[str, Any], collection_names: List[str]) -> Iterator[Tuple[str, int, Dict[str, Any]]]:
    """Yield (collection_name, index, entity_dict) across all declared collections."""
    for col in collection_names:
        items = data.get(col)
        if isinstance(items, list):
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    yield col, i, item


def semantic_errors(data: Dict[str, Any], collection_names: List[str]) -> List[str]:
    """Perform semantic integrity checks: ID uniqueness, prefix validity, and referential links."""
    errs = []
    seen_ids: Set[str] = set()
    all_declared_ids: Set[str] = set()

    # Pass 1: Collect and validate all declared entity IDs
    for col, idx, ent in extract_entities(data, collection_names):
        eid = ent.get("id")
        if not eid:
            errs.append(f"{col}[{idx}]: entity missing required 'id'")
            continue

        if not str(eid).startswith("heritageGraph:"):
            errs.append(
                f"{col}[{idx}] ({eid}): non-canonical CURIE prefix; "
                "must use authoritative 'heritageGraph:' prefix"
            )

        if eid in seen_ids:
            errs.append(f"{col}[{idx}]: duplicate id '{eid}'")
        seen_ids.add(eid)
        all_declared_ids.add(eid)

    # Pass 2: Semantic validations across primary entities and references
    for col, idx, ent in extract_entities(data, collection_names):
        eid = ent.get("id", f"#{idx}")

        # Primary physical & living entities should have a label, name, or note
        if col in ("structures", "human_made_objects", "iconographic_objects", "places", "guthis", "festivals"):
            has_name = bool(str(ent.get("name", "") or ent.get("label", "")).strip())
            has_note = bool(str(ent.get("note", "") or ent.get("description", "")).strip())
            if not has_name and not has_note:
                errs.append(f"{col}[{idx}] ({eid}): entity missing both 'name/label' and 'note/description'")

        # Referential integrity checks for known single-reference fields
        single_ref_fields = [
            "has_current_location", "hypothesized_location", "was_produced_by_event",
            "destruction_event", "was_documented_by", "enshrined_deity", "enshrined_in_structure"
        ]
        for f in single_ref_fields:
            target = ent.get(f)
            if target and isinstance(target, str):
                if target.startswith("heritageGraph:"):
                    if target not in all_declared_ids:
                        errs.append(f"{col}[{idx}] ({eid}): reference '{f}' points to undeclared entity '{target}'")

        # Referential integrity checks for multi-reference fields
        multi_ref_fields = [
            "managed_by_guthi", "participates_in_ritual", "has_component", "has_assertion"
        ]
        for mf in multi_ref_fields:
            targets = ent.get(mf, [])
            if isinstance(targets, list):
                for target in targets:
                    if isinstance(target, str) and target.startswith("heritageGraph:"):
                        if target not in all_declared_ids:
                            errs.append(f"{col}[{idx}] ({eid}): reference '{mf}' contains undeclared entity '{target}'")

    return errs


def main():
    ap = argparse.ArgumentParser(description="Validate stage-1 extracted JSON against LinkML schema.")
    ap.add_argument("path", nargs="?", default=None, help="Path to extracted JSON file or run directory")
    ap.add_argument("--run-dir", default=None, help="Path to pipeline run directory (validates 01_extracted.json)")
    ap.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Path to JSON Schema")
    args = ap.parse_args()

    run_dir = args.run_dir
    target_file = None
    ws = None

    if not run_dir and args.path and Path(args.path).is_dir():
        run_dir = args.path

    if run_dir:
        run_path = Path(run_dir)
        if RunWorkspace:
            try:
                ws = RunWorkspace.find(run_path)
            except Exception:
                ws = RunWorkspace(run_path)
            target_file = ws.artifact_path(1)
        else:
            target_file = run_path / "01_extracted.json"
    elif args.path:
        target_file = Path(args.path)
    else:
        ap.error("Must provide either a JSON file path or --run-dir")

    if not target_file.exists():
        print(f"Error: Target file not found: {target_file}", file=sys.stderr)
        return 1

    if ws:
        ws.record_stage_start(1, "extract", {"validator": "validate_extraction.py", "file": str(target_file)})

    data = json.load(open(target_file, encoding="utf-8"))
    schema = json.load(open(args.schema, encoding="utf-8"))

    validator = Draft202012Validator(schema)
    schema_errors = [
        f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    ]

    collections = get_schema_collections(schema)
    sem_errors = semantic_errors(data, collections)
    all_errors = schema_errors + sem_errors

    if all_errors:
        if ws:
            ws.record_stage_finish(
                1, "extract", status="failed", error=f"{len(all_errors)} validation errors",
                metrics={"error_count": len(all_errors)}
            )
        print(f"INVALID: {len(all_errors)} problem(s)")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    entity_count = sum(1 for _ in extract_entities(data, collections))
    col_counts = {
        col: len(data.get(col, []))
        for col in collections
        if isinstance(data.get(col), list) and len(data.get(col)) > 0
    }
    if ws:
        ws.record_stage_finish(
            1, "extract", status="success",
            metrics={"total_entities": entity_count, "collections": col_counts}
        )
    print(f"OK: {entity_count} entity/record(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
