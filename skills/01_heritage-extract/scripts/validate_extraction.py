#!/usr/bin/env python3
"""Validate stage-1 output against extraction.schema.json plus semantic checks.

Supports both LinkML Container structures (collections of heritage entities)
and legacy record-list structures.

Usage: validate_extraction.py extracted.json [--schema PATH]
Exit code 0 = valid, 1 = errors found.
"""
import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

DEFAULT_SCHEMA = Path(__file__).resolve().parent.parent / "assets" / "extraction.schema.json"

COLLECTION_NAMES = [
    "structures", "architectural_elements", "human_made_objects", "iconographic_objects",
    "places", "persons", "actors", "guthis", "festivals", "ritual_events",
    "production_events", "consecration_events", "enshrinement_events",
    "custody_events", "historical_events", "kumari_lifecycle_events",
    "kumari_roles", "kumari_tenures", "deities", "caste_groups", "assertions",
    "materials", "techniques", "time_spans", "data_custodians", "data_sources"
]


def extract_entities(data):
    """Yield (collection_name, index, entity_dict) across all collections."""
    if "records" in data and isinstance(data["records"], list):
        for i, rec in enumerate(data["records"]):
            yield "records", i, rec
        return

    for col in COLLECTION_NAMES:
        items = data.get(col)
        if isinstance(items, list):
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    yield col, i, item


def semantic_errors(data):
    errs = []
    seen_ids = set()
    all_declared_ids = set()

    # Pass 1: Collect all declared entity IDs
    for col, idx, ent in extract_entities(data):
        eid = ent.get("id")
        if eid:
            if eid in seen_ids:
                errs.append(f"{col}[{idx}]: duplicate id '{eid}'")
            seen_ids.add(eid)
            all_declared_ids.add(eid)

    # Pass 2: Semantic validations
    for col, idx, ent in extract_entities(data):
        eid = ent.get("id", f"#{idx}")
        # Primary entities should have a name or note/description
        if col in ("structures", "human_made_objects", "iconographic_objects", "places", "guthis", "festivals"):
            has_name = bool(str(ent.get("name", "")).strip())
            has_note = bool(str(ent.get("note", "") or ent.get("description", "")).strip())
            if not has_name and not has_note:
                errs.append(f"{col}[{idx}] ({eid}): entity missing both 'name' and 'note/description'")

        # Referential integrity checks for known reference fields
        ref_fields = [
            "has_current_location", "hypothesized_location", "was_produced_by_event",
            "destruction_event", "was_documented_by"
        ]
        for f in ref_fields:
            target = ent.get(f)
            if target and isinstance(target, str):
                # If target looks like a local CURIE or ID within this container, verify it exists
                if target.startswith("heritageGraph:") or target.startswith("hg:"):
                    if target not in all_declared_ids:
                        errs.append(f"{col}[{idx}] ({eid}): reference '{f}' points to undeclared entity '{target}'")

        # Multi-value reference checks
        multi_ref_fields = ["managed_by_guthi", "participates_in_ritual", "has_component", "has_assertion"]
        for mf in multi_ref_fields:
            targets = ent.get(mf, [])
            if isinstance(targets, list):
                for target in targets:
                    if isinstance(target, str) and (target.startswith("heritageGraph:") or target.startswith("hg:")):
                        if target not in all_declared_ids:
                            errs.append(f"{col}[{idx}] ({eid}): reference '{mf}' contains undeclared entity '{target}'")

    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="Path to extracted JSON file")
    ap.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Path to JSON Schema")
    args = ap.parse_args()

    data = json.load(open(args.path, encoding="utf-8"))
    schema = json.load(open(args.schema, encoding="utf-8"))

    validator = Draft202012Validator(schema)
    schema_errors = [
        f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    ]
    sem_errors = semantic_errors(data)
    all_errors = schema_errors + sem_errors

    if all_errors:
        print(f"INVALID: {len(all_errors)} problem(s)")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    entity_count = sum(1 for _ in extract_entities(data))
    print(f"OK: {entity_count} entity/record(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
