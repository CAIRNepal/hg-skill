#!/usr/bin/env python3
"""Deterministic entity resolution runner for Stage 2 of HeritageGraph pipeline.

Reconciles entities from 01_extracted.json against gazetteers, attaches resolutions,
mints predictable local URIs when unlinked, and outputs 02_resolved.json into the
active RunWorkspace. Aligned with ADR-0003.
"""
import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMON_DIR = REPO_ROOT / "skills" / "common"
SCRIPTS_DIR = Path(__file__).resolve().parent

for d in (COMMON_DIR, SCRIPTS_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

try:
    from run_workspace import RunWorkspace
except ImportError:
    RunWorkspace = None

from gazetteer_match import fold, load_gazetteers


def slugify(text: str) -> str:
    """Stable, URI-safe slug."""
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


def resolve_container_entities(
    data: Dict[str, Any],
    gazetteers_dir: Optional[Path] = None,
    base_uri: str = "https://cair-nepal.org/heritagegraph/",
) -> Dict[str, Any]:
    """Attach resolutions to all entities across collections in Container format."""
    index = load_gazetteers(gazetteers_dir) if gazetteers_dir and gazetteers_dir.exists() else {}
    base = base_uri.rstrip("/") + "/"

    kind_map = {
        "places": "place", "persons": "person", "actors": "group",
        "guthis": "group", "festivals": "event", "ritual_events": "event",
        "materials": "material", "techniques": "technique", "deities": "concept",
        "structures": "structure", "human_made_objects": "object", "iconographic_objects": "object"
    }

    counts = {"linked": 0, "local": 0, "ambiguous": 0}

    for col, default_kind in kind_map.items():
        items = data.get(col)
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            label = item.get("name") or item.get("label") or item.get("id", "")
            folded_label = fold(label)
            context = str(item.get("note") or item.get("description") or "")

            hits = index.get(folded_label, [])
            same_kind = [h for h in hits if not h.get("kind") or h["kind"] == default_kind]

            if len(same_kind) == 1:
                item["resolution"] = {
                    "uri": same_kind[0]["uri"],
                    "source": same_kind[0].get("gazetteer", "gazetteer"),
                    "confidence": 0.95,
                    "status": "linked",
                    "rationale": f"Exact gazetteer match for '{label}'"
                }
                counts["linked"] += 1
            else:
                # Mint predictable local URI
                slug = slugify(label)
                local_uri = f"{base}{default_kind}/{slug}"
                item["resolution"] = {
                    "uri": local_uri,
                    "source": "local-mint",
                    "confidence": 1.0,
                    "status": "local",
                    "rationale": f"Minted local URI under project base for '{label}'"
                }
                counts["local"] += 1

    return {"data": data, "counts": counts}


def main():
    ap = argparse.ArgumentParser(description="Resolve entities from extracted.json into resolved.json.")
    ap.add_argument("extracted", nargs="?", default=None, help="Path to extracted.json file or run directory")
    ap.add_argument("--run-dir", default=None, help="Pipeline run directory")
    ap.add_argument("--gazetteers", default=None, help="Path to gazetteers directory")
    ap.add_argument("--out", default=None, help="Path to write resolved.json")
    ap.add_argument("--base", default="https://cair-nepal.org/heritagegraph/")
    args = ap.parse_args()

    ws = None
    extracted_path = None
    out_path = None

    if args.run_dir or (args.extracted and Path(args.extracted).is_dir()):
        run_path = Path(args.run_dir if args.run_dir else args.extracted)
        if RunWorkspace:
            try:
                ws = RunWorkspace.find(run_path)
            except Exception:
                ws = RunWorkspace(run_path)
            extracted_path = ws.artifact_path(1)
            out_path = ws.artifact_path(2)
        else:
            extracted_path = run_path / "01_extracted.json"
            out_path = run_path / "02_resolved.json"
    elif args.extracted:
        extracted_path = Path(args.extracted)
    else:
        ap.error("Must provide either extracted JSON path or --run-dir")

    if args.out:
        out_path = Path(args.out)
    elif not out_path:
        ap.error("the following arguments are required: --out (or specify --run-dir)")

    gazetteers_dir = (
        Path(args.gazetteers) if args.gazetteers
        else Path(__file__).resolve().parent.parent / "assets" / "gazetteers"
    )

    if not extracted_path.exists():
        print(f"Error: Input file not found: {extracted_path}", file=sys.stderr)
        return 1

    if ws:
        ws.record_stage_start(2, "resolve", {"input": str(extracted_path), "gazetteers": str(gazetteers_dir)})

    with open(extracted_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = resolve_container_entities(data, gazetteers_dir=gazetteers_dir, base_uri=args.base)
    resolved_data = result["data"]
    counts = result["counts"]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resolved_data, f, indent=2, ensure_ascii=False)

    if ws:
        ws.record_stage_finish(2, "resolve", status="success", metrics=counts)

    print(f"Resolved entities: {counts['linked']} linked, {counts['local']} local, {counts['ambiguous']} ambiguous.")
    print(f"Output saved to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
