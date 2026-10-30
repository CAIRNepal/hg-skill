#!/usr/bin/env python3
"""Deterministic and interactive entity resolution runner for Stage 2 of HeritageGraph pipeline.

Reconciles entities from 01_extracted.json against gazetteers and public authorities,
stages ambiguous or unlinked entities into 02_review_queue.json, supports interactive
human curation via --interactive, and writes 02_resolved.json into the active RunWorkspace.
Aligned with ADR-0003 and ADR-0004.
"""
import argparse
import csv
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


def fetch_candidates(
    label: str,
    kind: str,
    context: str = "",
    gazetteers_dir: Optional[Path] = None,
    query_network: bool = True,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Fetch and deduplicate candidate URIs from gazetteers, Wikidata, and Getty."""
    candidates = []
    seen_uris = set()

    # 1. Check local gazetteers
    if gazetteers_dir and gazetteers_dir.exists():
        index = load_gazetteers(gazetteers_dir)
        folded = fold(label)
        hits = index.get(folded, [])
        for h in hits:
            uri = h.get("uri")
            if uri and uri not in seen_uris:
                candidates.append({
                    "uri": uri,
                    "label": h.get("label", label),
                    "source": h.get("gazetteer", "local-gazetteer"),
                    "description": h.get("context", ""),
                    "confidence": 0.95 if not h.get("kind") or h["kind"] == kind else 0.80,
                })
                seen_uris.add(uri)

    if not query_network:
        return candidates

    # 2. Query Wikidata
    try:
        from lookup_wikidata import query_wikidata
        wiki_hits = query_wikidata(label, limit=limit, timeout=4)
        for h in wiki_hits:
            uri = h["uri"]
            if uri not in seen_uris:
                candidates.append({
                    "uri": uri,
                    "label": h.get("label", label),
                    "source": "wikidata",
                    "description": h.get("description", ""),
                    "confidence": 0.85,
                })
                seen_uris.add(uri)
    except Exception:
        pass

    # 3. Query Getty
    if kind in ("material", "technique", "concept", "structure", "person", "place"):
        vocab = "aat" if kind in ("material", "technique", "concept") else ("ulan" if kind == "person" else "tgn")
        try:
            from lookup_getty import query_getty
            getty_hits = query_getty(label, vocab=vocab, limit=limit, timeout=4)
            for b in getty_hits:
                uri = b["uri"]
                if uri not in seen_uris:
                    candidates.append({
                        "uri": uri,
                        "label": b.get("label", label),
                        "source": f"getty-{vocab}",
                        "description": "",
                        "confidence": 0.85,
                    })
                    seen_uris.add(uri)
        except Exception:
            pass

    # 4. Query Yale LUX
    try:
        from lookup_lux import query_lux
        lux_hits = query_lux(label, kind=kind, limit=limit, timeout=4)
        for h in lux_hits:
            uri = h["uri"]
            if uri not in seen_uris:
                candidates.append({
                    "uri": uri,
                    "label": h.get("label", label),
                    "source": "lux",
                    "description": h.get("description", ""),
                    "confidence": h.get("confidence", 0.85),
                })
                seen_uris.add(uri)
    except Exception:
        pass

    return candidates


def resolve_container_entities(
    data: Dict[str, Any],
    gazetteers_dir: Optional[Path] = None,
    base_uri: str = "https://cair-nepal.org/heritagegraph/",
    query_network: bool = True,
) -> Dict[str, Any]:
    """Attach resolutions to all entities and compile review queue items for unlinked ones."""
    index = load_gazetteers(gazetteers_dir) if gazetteers_dir and gazetteers_dir.exists() else {}
    base = base_uri.rstrip("/") + "/"

    kind_map = {
        "places": "place", "persons": "person", "actors": "group",
        "guthis": "group", "festivals": "event", "ritual_events": "event",
        "materials": "material", "techniques": "technique", "deities": "concept",
        "structures": "structure", "human_made_objects": "object", "iconographic_objects": "object"
    }

    counts = {"linked": 0, "local": 0, "ambiguous": 0}
    review_queue: List[Dict[str, Any]] = []

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
                    "match_type": same_kind[0].get("match_type", "exact"),
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

                # Compile candidate options for human review
                candidates = fetch_candidates(
                    label=label,
                    kind=default_kind,
                    context=context,
                    gazetteers_dir=gazetteers_dir,
                    query_network=query_network,
                )

                review_queue.append({
                    "id": item.get("id"),
                    "collection": col,
                    "label": label,
                    "kind": default_kind,
                    "context": context,
                    "current_uri": local_uri,
                    "status": "local",
                    "candidates": candidates
                })

    return {"data": data, "counts": counts, "review_queue": review_queue}


def append_to_curated_gazetteer(
    curated_csv_path: Path,
    uri: str,
    label: str,
    kind: str,
    context: str = "",
    alt_labels: str = "",
) -> None:
    """Append a human-confirmed mapping into the curated links gazetteer CSV."""
    curated_csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not curated_csv_path.exists() or curated_csv_path.stat().st_size == 0
    with open(curated_csv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["uri", "label", "alt_labels", "kind", "context"])
        writer.writerow([uri, label, alt_labels, kind, context])


def interactive_review_session(
    review_queue: List[Dict[str, Any]],
    resolved_data: Dict[str, Any],
    curated_csv_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Conduct interactive terminal review for unlinked or ambiguous entities."""
    if not review_queue:
        print("Review Queue is empty: all entities resolved.")
        return {"data": resolved_data, "curator_decisions": 0}

    print("\n" + "=" * 60)
    print(f"Human-in-the-Loop Review Queue: {len(review_queue)} item(s) to verify")
    print("=" * 60)

    curator_decisions = 0
    resolved_ids = set()

    # Build index of items by ID for quick updating
    id_map = {}
    for col, items in resolved_data.items():
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and "id" in it:
                    id_map[it["id"]] = it

    for idx, item in enumerate(review_queue, 1):
        print(f"\n[{idx}/{len(review_queue)}] {item['kind'].upper()}: '{item['label']}'")
        if item.get("context"):
            print(f"    Context: {item['context']}")
        print(f"    Default Minted URI: {item['current_uri']}")

        candidates = item.get("candidates", [])
        option_idx = 1
        options_map = {}

        if candidates:
            print("    Candidate Matches:")
            for c in candidates:
                desc = f" ({c['description']})" if c.get("description") else ""
                print(f"      [{option_idx}] {c['uri']}{desc} [{c['source']}]")
                options_map[str(option_idx)] = c
                option_idx += 1

        mint_opt = str(option_idx)
        print(f"      [{mint_opt}] Keep Minted Local URI ({item['current_uri']})")
        custom_opt = "c"
        print("      [c] Enter Custom External URI")
        skip_opt = "s"
        print("      [s] Skip for now")

        try:
            choice = input(f"    Choice [1-{option_idx}/c/s]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nInteractive review aborted by user.")
            break

        selected_uri = None
        selected_source = "human-curator"

        if choice in options_map:
            cand = options_map[choice]
            selected_uri = cand["uri"]
            selected_source = f"human-curator ({cand['source']})"
        elif choice == mint_opt or choice == "m":
            selected_uri = item["current_uri"]
            selected_source = "human-curator (minted)"
        elif choice == "c":
            selected_uri = input("      Enter Custom URI: ").strip()
            if not selected_uri:
                print("      No URI entered; skipping.")
                continue
            selected_source = "human-curator (custom)"
        elif choice == "s" or not choice:
            print("      Skipped.")
            continue
        else:
            print("      Unrecognized choice; skipped.")
            continue

        # Apply choice to resolved data
        target_entity = id_map.get(item["id"])
        if target_entity:
            target_entity["resolution"] = {
                "uri": selected_uri,
                "source": selected_source,
                "confidence": 1.0,
                "status": "linked" if "cair-nepal.org" not in selected_uri else "local",
                "rationale": f"Verified by human curator for '{item['label']}'",
            }
            curator_decisions += 1
            resolved_ids.add(item["id"])
            print(f"      -> Resolved to: {selected_uri}")

            # Offer to save into curated-links.csv
            if curated_csv_path and selected_uri != item["current_uri"]:
                try:
                    save_gaz = input("      Save this mapping into curated-links.csv? [Y/n]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    save_gaz = "y"
                if save_gaz != "n":
                    append_to_curated_gazetteer(
                        curated_csv_path=curated_csv_path,
                        uri=selected_uri,
                        label=item["label"],
                        kind=item["kind"],
                        context=item.get("context", ""),
                    )
                    print(f"      -> Saved to {curated_csv_path.name}")

    return {
        "data": resolved_data,
        "curator_decisions": curator_decisions,
        "resolved_ids": resolved_ids,
    }


def main():
    ap = argparse.ArgumentParser(description="Resolve entities from extracted.json into resolved.json with HITL review.")
    ap.add_argument("extracted", nargs="?", default=None, help="Path to extracted.json file or run directory")
    ap.add_argument("--run-dir", default=None, help="Pipeline run directory")
    ap.add_argument("--interactive", "-i", action="store_true", help="Launch interactive human review prompt")
    ap.add_argument("--gazetteers", default=None, help="Path to gazetteers directory")
    ap.add_argument("--out", default=None, help="Path to write resolved.json")
    ap.add_argument("--base", default="https://cair-nepal.org/heritagegraph/")
    ap.add_argument("--no-network", action="store_true", help="Disable external network queries for candidates")
    args = ap.parse_args()

    ws = None
    extracted_path = None
    out_path = None
    review_queue_path = None

    if args.run_dir or (args.extracted and Path(args.extracted).is_dir()):
        run_path = Path(args.run_dir if args.run_dir else args.extracted)
        if RunWorkspace:
            try:
                ws = RunWorkspace.find(run_path)
            except Exception:
                ws = RunWorkspace(run_path)
            extracted_path = ws.artifact_path(1)
            out_path = ws.artifact_path(2)
            review_queue_path = ws.run_dir / "02_review_queue.json"
        else:
            extracted_path = run_path / "01_extracted.json"
            out_path = run_path / "02_resolved.json"
            review_queue_path = run_path / "02_review_queue.json"
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
    curated_csv_path = gazetteers_dir / "curated-links.csv"

    if not extracted_path.exists():
        print(f"Error: Input file not found: {extracted_path}", file=sys.stderr)
        return 1

    if ws:
        ws.record_stage_start(
            2, "resolve",
            {"input": str(extracted_path), "interactive": args.interactive, "gazetteers": str(gazetteers_dir)}
        )

    with open(extracted_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = resolve_container_entities(
        data,
        gazetteers_dir=gazetteers_dir,
        base_uri=args.base,
        query_network=not args.no_network,
    )
    resolved_data = result["data"]
    counts = result["counts"]
    review_queue = result["review_queue"]

    curator_decisions = 0
    if args.interactive and review_queue:
        review_result = interactive_review_session(
            review_queue=review_queue,
            resolved_data=resolved_data,
            curated_csv_path=curated_csv_path,
        )
        resolved_data = review_result["data"]
        curator_decisions = review_result["curator_decisions"]
        resolved_ids = review_result.get("resolved_ids", set())
        review_queue = [q for q in review_queue if q.get("id") not in resolved_ids]

    # Save 02_resolved.json
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resolved_data, f, indent=2, ensure_ascii=False)

    # Save 02_review_queue.json if review queue path is known; remove stale file if queue is empty
    if review_queue_path:
        if review_queue:
            with open(review_queue_path, "w", encoding="utf-8") as f:
                json.dump(review_queue, f, indent=2, ensure_ascii=False)
        elif review_queue_path.exists():
            try:
                review_queue_path.unlink()
            except OSError:
                pass

    metrics = {
        **counts,
        "needs_human_review": len(review_queue) > 0,
        "review_queue_count": len(review_queue),
        "curator_decisions": curator_decisions,
    }

    if ws:
        ws.record_stage_finish(2, "resolve", status="success", metrics=metrics)

    print(f"Resolved entities: {counts['linked']} linked, {counts['local']} local, {counts['ambiguous']} ambiguous.")
    if len(review_queue) > 0:
        print(f"NOTE: {len(review_queue)} item(s) staged in review queue ({review_queue_path.name if review_queue_path else 'review queue'}).")
        print("Run with '--interactive' to review choices.")
    print(f"Output saved to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
