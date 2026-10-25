#!/usr/bin/env python3
"""Orchestrate the end-to-end transformation of cultural heritage data into a validated RDF knowledge graph.

Operates natively within an isolated RunWorkspace under runs/<run_id>/, tracking provenance
across stages 00_preprocessed.json through 04_shacl_report.json in manifest.json.
Aligned with ADR-0003 and GLOSSARY.md.

Usage:
  python run_pipeline.py [--run-dir DIR] [input_path] [--ontology cidoc-crm] [--base URI]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional, Union

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = Path(__file__).resolve().parents[1].parent
COMMON_DIR = SKILLS_DIR / "common"

for d in (COMMON_DIR,):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

try:
    from run_workspace import RunWorkspace
except ImportError:
    RunWorkspace = None


def find_skill_dir(base_name: str) -> Path:
    """Find skill directory with or without numeric prefix."""
    for path in SKILLS_DIR.iterdir():
        if path.is_dir() and (path.name == base_name or path.name.endswith(f"_{base_name}")):
            return path
    return SKILLS_DIR / base_name


def run_subcommand(cmd):
    print("$", " ".join(map(str, cmd)))
    return subprocess.run([str(c) for c in cmd]).returncode


def run_pipeline(
    input_path: Optional[Union[str, Path]] = None,
    run_dir: Optional[Union[str, Path]] = None,
    ontology: str = "cidoc-crm",
    base_uri: str = "https://cair-nepal.org/heritagegraph/",
    shapes: Optional[Union[str, Path]] = None,
    interactive: bool = False,
) -> int:
    """Run pipeline stages sequentially inside an isolated RunWorkspace."""
    ws = None
    inp = Path(input_path) if input_path else None

    if run_dir:
        ws = RunWorkspace(run_dir)
    elif inp and inp.is_dir():
        ws = RunWorkspace(inp)
    elif inp and inp.is_file():
        if inp.name in ("01_extracted.json", "02_resolved.json") and (inp.parent / "manifest.json").exists():
            ws = RunWorkspace(inp.parent)
        else:
            ws = RunWorkspace.init(inp)
    else:
        raise ValueError("Must provide either an input file or a --run-dir")

    extract_dir = find_skill_dir("heritage-extract")
    resolve_dir = find_skill_dir("heritage-entity-resolution")
    mapper_dir = find_skill_dir("heritage-rdf-mapper")
    validator_dir = find_skill_dir("heritage-shacl-validate")

    # Stage 0: Ingestion if raw file exists and 00_preprocessed.json missing
    if inp and inp.is_file() and inp.suffix.lower() in (".pdf", ".csv", ".tsv", ".xlsx", ".json") and not ws.artifact_path(0).exists():
        rc = run_subcommand([
            sys.executable, extract_dir / "scripts" / "ingest_raw.py",
            str(inp), "--run-dir", str(ws.run_dir)
        ])
        if rc != 0:
            ws.finalize(status="failed", summary={"failed_stage": "stage_00_ingest"})
            return rc

    # Stage 1: Validate extraction if 01_extracted.json exists
    p1 = ws.artifact_path(1)
    if p1.exists():
        rc = run_subcommand([
            sys.executable, extract_dir / "scripts" / "validate_extraction.py",
            "--run-dir", str(ws.run_dir)
        ])
        if rc != 0:
            ws.finalize(status="failed", summary={"failed_stage": "stage_01_extract"})
            return rc

    # Stage 2: Entity resolution if 01_extracted.json exists and (02_resolved.json missing or interactive review requested)
    p2 = ws.artifact_path(2)
    if p1.exists() and (not p2.exists() or interactive):
        resolve_cmd = [
            sys.executable, resolve_dir / "scripts" / "resolve_entities.py",
            "--run-dir", str(ws.run_dir), "--base", base_uri
        ]
        if interactive:
            resolve_cmd.append("--interactive")
        rc = run_subcommand(resolve_cmd)
        if rc != 0:
            ws.finalize(status="failed", summary={"failed_stage": "stage_02_resolve"})
            return rc

    # Stage 3: Map to RDF
    mapping_file = mapper_dir / f"assets/mappings/{ontology}.yaml"
    rc = run_subcommand([
        sys.executable, mapper_dir / "scripts" / "map_to_rdf.py",
        "--run-dir", str(ws.run_dir),
        "--mapping", str(mapping_file),
        "--base", base_uri,
    ])
    if rc != 0:
        ws.finalize(status="failed", summary={"failed_stage": "stage_03_map"})
        return rc

    # Stage 4: SHACL Validation
    shapes_path = Path(shapes) if shapes else validator_dir / "assets" / "shapes" / "HeritageGraph.shacl.ttl"
    if not shapes_path.exists():
        shapes_path = validator_dir / f"assets/shapes/{ontology}.shacl.ttl"
    if not shapes_path.exists():
        shapes_path = REPO_ROOT / "schemas" / "HeritageGraph.shacl.ttl"

    rc = run_subcommand([
        sys.executable, validator_dir / "scripts" / "validate.py",
        "--run-dir", str(ws.run_dir),
        "--shapes", str(shapes_path)
    ])

    # Finalize workspace manifest
    p4 = ws.artifact_path(4)
    total_triples = 0
    if p4.exists():
        try:
            with open(p4, "r", encoding="utf-8") as f:
                rep = json.load(f)
                total_triples = rep.get("triples", 0)
        except Exception:
            pass

    ws.finalize(
        status="completed" if rc == 0 else "violations",
        summary={
            "shacl_conformant": rc == 0,
            "total_triples": total_triples,
            "ontology": ontology
        }
    )
    return rc


def main():
    ap = argparse.ArgumentParser(description="Orchestrate HeritageGraph transformation pipeline.")
    ap.add_argument("input", nargs="?", default=None, help="Input source file or run directory")
    ap.add_argument("--run-dir", default=None, help="Pipeline run directory")
    ap.add_argument("--ontology", default="cidoc-crm", help="Target ontology mapping (default: cidoc-crm)")
    ap.add_argument("--base", default="https://cair-nepal.org/heritagegraph/", help="Base URI for local minting")
    ap.add_argument("--shapes", default=None, help="Path to SHACL shapes file")
    ap.add_argument("--interactive", "-i", action="store_true", help="Launch interactive human review in Stage 2")
    args = ap.parse_args()

    return run_pipeline(
        input_path=args.input,
        run_dir=args.run_dir,
        ontology=args.ontology,
        base_uri=args.base,
        shapes=args.shapes,
        interactive=args.interactive,
    )


if __name__ == "__main__":
    sys.exit(main())
