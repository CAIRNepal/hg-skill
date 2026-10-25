#!/usr/bin/env python3
"""Fetch and update CAIR-Nepal HeritageGraph ontology artifacts for a given git reference.

Usage:
    python scripts/update_ontology.py [--ref main|v1.0.1|<tag>|<commit>]
"""
import argparse
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"
SHAPES_DIR = ROOT / "skills/04_heritage-shacl-validate/assets/shapes"

FILES = [
    "HeritageGraph.yaml",
    "HeritageGraph.ttl",
    "HeritageGraph.shacl.ttl",
]


def fetch_file(base_url: str, filename: str, dest_path: Path):
    url = f"{base_url}/{filename}"
    print(f"Downloading {filename} from {url} ...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hg-skill/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as out:
            out.write(resp.read())
        print(f"  ✓ Saved to {dest_path.relative_to(ROOT)} ({dest_path.stat().st_size:,} bytes)")
    except urllib.error.HTTPError as e:
        print(f"  ✗ HTTP Error {e.code} fetching {url}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"  ✗ Error fetching {url}: {e}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description="Update HeritageGraph ontology artifacts.")
    parser.add_argument("--ref", default="main", help="Git branch, release tag, or commit SHA (default: main)")
    args = parser.parse_args()

    SCHEMAS.mkdir(parents=True, exist_ok=True)
    SHAPES_DIR.mkdir(parents=True, exist_ok=True)

    base_url = f"https://raw.githubusercontent.com/CAIRNepal/heritagegraphontology/{args.ref}/ontology"
    print(f"Fetching HeritageGraph ontology artifacts (ref: {args.ref})")

    try:
        for fname in FILES:
            dest = SCHEMAS / fname
            fetch_file(base_url, fname, dest)

        # Sync SHACL shapes to Stage 4 validator assets
        shacl_src = SCHEMAS / "HeritageGraph.shacl.ttl"
        shacl_dest = SHAPES_DIR / "HeritageGraph.shacl.ttl"
        shutil.copy2(shacl_src, shacl_dest)
        print(f"  ✓ Synchronized shapes to {shacl_dest.relative_to(ROOT)}")
        print(f"\nSuccessfully updated all artifacts to ref '{args.ref}'.")
        return 0
    except Exception:
        print(f"\nFailed to update ontology artifacts for ref '{args.ref}'.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
