#!/usr/bin/env python3
"""Run the deterministic stages (3: map, 4: validate) on a resolved.json.

Stages 1 and 2 are performed by the AI agent (see 01_heritage-extract and 02_heritage-entity-resolution);
this script picks up from their output.

Usage: run_pipeline.py resolved.json [--ontology cidoc-crm] [--base URI] [--out graph.ttl]
Exit code: 0 conforms, 1 validation failed (graph is still written, but must not be shipped as final).
"""
import argparse
import subprocess
import sys
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]


def find_skill_dir(base_name: str) -> Path:
    """Find skill directory with or without numeric prefix."""
    for path in SKILLS.iterdir():
        if path.is_dir() and (path.name == base_name or path.name.endswith(f"_{base_name}")):
            return path
    return SKILLS / base_name


def run(cmd):
    print("$", " ".join(map(str, cmd)))
    return subprocess.run([str(c) for c in cmd]).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("resolved")
    ap.add_argument("--ontology", default="cidoc-crm")
    ap.add_argument("--base", default="https://cair-nepal.org/heritagegraph/")
    ap.add_argument("--shapes", default=None, help="Path to SHACL shapes file (defaults to HeritageGraph.shacl.ttl)")
    ap.add_argument("--out", default="graph.ttl")
    args = ap.parse_args()

    mapper_dir = find_skill_dir("heritage-rdf-mapper")
    validator_dir = find_skill_dir("heritage-shacl-validate")

    rc = run([sys.executable, mapper_dir / "scripts/map_to_rdf.py", args.resolved,
              "--mapping", mapper_dir / f"assets/mappings/{args.ontology}.yaml",
              "--base", args.base, "--out", args.out])
    if rc != 0:
        print("mapping failed; not validating", file=sys.stderr)
        return rc

    shapes_path = Path(args.shapes) if args.shapes else validator_dir / "assets/shapes/HeritageGraph.shacl.ttl"
    if not shapes_path.exists():
        shapes_path = validator_dir / f"assets/shapes/{args.ontology}.shacl.ttl"

    return run([sys.executable, validator_dir / "scripts/validate.py", args.out,
                "--shapes", shapes_path,
                "--report", Path(args.out).with_suffix(".validation.json")])


if __name__ == "__main__":
    sys.exit(main())
