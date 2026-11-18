#!/usr/bin/env python3
"""Unified CLI facade for HeritageGraph skills and transformation pipeline (hg).

Commands:
  hg sync    : Anonymously fetch ontology artifacts and KG snapshots from S3 Open Data
  hg doctor  : Non-blocking diagnostic checks for environment, dependencies, and network
  hg run     : End-to-end transformation from raw documents to validated graph & bundle
  hg diff    : Compare generated graph against local KG mirror (Stage 05)
  hg bundle  : Package validated run into contribution bundle (Stage 06)
"""
import argparse
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"
SRC_DIR = REPO_ROOT / "src"
COMMON_DIR = SKILLS_DIR / "common"

for d in (SRC_DIR, COMMON_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))


def cmd_sync(args: argparse.Namespace) -> int:
    from hg.sync import S3SyncManager, sync_assets

    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    bucket_url = args.bucket if hasattr(args, "bucket") and args.bucket else None

    target = "all"
    if getattr(args, "ontology_only", False):
        target = "ontology"
    elif getattr(args, "snapshots_only", False):
        target = "snapshot"

    try:
        results = sync_assets(
            cache_dir=cache_dir,
            target=target,
            offline=args.offline,
            bucket=bucket_url if bucket_url else "cair-nepal-heritagegraph-opendata",
        )
        print("Sync completed successfully.")
        return 0
    except Exception as exc:
        print(f"Error during sync: {exc}", file=sys.stderr)
        return 1


def cmd_doctor(args: argparse.Namespace) -> int:
    from hg.doctor import run_doctor

    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    rep = run_doctor(cache_dir=cache_dir, check_network=not args.no_network, verbose=True)
    return 0 if rep["healthy"] else 1


def cmd_diff(args: argparse.Namespace) -> int:
    diff_script = SKILLS_DIR / "05_heritage-diff" / "scripts" / "diff_graph.py"
    if str(diff_script.parent) not in sys.path:
        sys.path.insert(0, str(diff_script.parent))

    from diff_graph import main as diff_main

    argv = []
    if args.graph:
        argv.append(args.graph)
    if args.run_dir:
        argv.extend(["--run-dir", args.run_dir])
    if args.mirror:
        argv.extend(["--mirror", args.mirror])
    if args.out:
        argv.extend(["--out", args.out])
    if args.no_fail:
        argv.append("--no-fail-on-duplicates")

    return diff_main(argv)


def cmd_bundle(args: argparse.Namespace) -> int:
    bundle_script = SKILLS_DIR / "06_heritage-contribute" / "scripts" / "package_bundle.py"
    if str(bundle_script.parent) not in sys.path:
        sys.path.insert(0, str(bundle_script.parent))

    from package_bundle import main as bundle_main

    argv = []
    if args.run_dir:
        argv.append(args.run_dir)
    if args.out:
        argv.extend(["--out", args.out])
    if args.run_id:
        argv.extend(["--run-id", args.run_id])

    return bundle_main(argv)


def cmd_run(args: argparse.Namespace) -> int:
    pipeline_script = SKILLS_DIR / "00_heritage-to-rdf" / "scripts" / "run_pipeline.py"
    if str(pipeline_script.parent) not in sys.path:
        sys.path.insert(0, str(pipeline_script.parent))

    from run_pipeline import run_pipeline

    # Resolve mirror snapshot if not explicitly provided
    mirror_path = args.mirror
    if not mirror_path:
        # Check default cache for latest snapshot
        cache_dir = Path(args.cache_dir) if args.cache_dir else Path.home() / ".cache" / "heritagegraph"
        if not cache_dir.exists():
            cache_dir = Path(".cache/heritagegraph")
        snap_dir = cache_dir / "snapshots"
        if snap_dir.exists():
            snaps = sorted(list(snap_dir.glob("*.nt")) + list(snap_dir.glob("*.ttl")), reverse=True)
            if snaps:
                mirror_path = str(snaps[0])

    rc = run_pipeline(
        input_path=args.input,
        run_dir=args.run_dir,
        ontology=args.ontology,
        base_uri=args.base,
        shapes=args.shapes,
        interactive=args.interactive,
    )
    if rc != 0:
        return rc

    # Determine run workspace directory
    run_path = None
    if args.run_dir:
        run_path = Path(args.run_dir)
    elif args.input:
        p = Path(args.input)
        run_path = p if p.is_dir() else None

    if not run_path:
        # Find latest run in runs/
        runs_root = REPO_ROOT / "runs"
        if runs_root.exists():
            all_runs = sorted([d for d in runs_root.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
            if all_runs:
                run_path = all_runs[0]

    # Run Stage 5 (diff) if mirror is available
    if run_path and mirror_path:
        diff_script = SKILLS_DIR / "05_heritage-diff" / "scripts" / "diff_graph.py"
        if str(diff_script.parent) not in sys.path:
            sys.path.insert(0, str(diff_script.parent))
        from diff_graph import main as diff_main

        diff_rc = diff_main([
            "--run-dir", str(run_path),
            "--mirror", mirror_path,
        ])
        if diff_rc != 0:
            print("Stage 05 Diff Gate failed: duplicate entities detected.", file=sys.stderr)
            return diff_rc

    # Run Stage 6 (bundle) if run_path exists
    if run_path:
        bundle_script = SKILLS_DIR / "06_heritage-contribute" / "scripts" / "package_bundle.py"
        if str(bundle_script.parent) not in sys.path:
            sys.path.insert(0, str(bundle_script.parent))
        from package_bundle import main as bundle_main

        bundle_rc = bundle_main([str(run_path)])
        if bundle_rc != 0:
            return bundle_rc

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hg",
        description="HeritageGraph CLI - transform, validate, diff, and contribute cultural heritage data.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # hg sync
    p_sync = subparsers.add_parser("sync", help="Synchronize ontology assets and KG snapshot from S3")
    p_sync.add_argument("--cache-dir", default=None, help="Cache directory (default: ~/.cache/heritagegraph)")
    p_sync.add_argument("--offline", action="store_true", help="Use local cache without querying remote S3")
    p_sync.add_argument("--ontology-only", action="store_true", help="Sync only ontology schemas and shapes")
    p_sync.add_argument("--snapshots-only", action="store_true", help="Sync only latest knowledge graph snapshot")
    p_sync.add_argument("--bucket", default=None, help="Custom S3 bucket base URL")
    p_sync.set_defaults(func=cmd_sync)

    # hg doctor
    p_doc = subparsers.add_parser("doctor", help="Check environment, dependencies, cache, and connectivity")
    p_doc.add_argument("--cache-dir", default=None, help="Cache directory to inspect")
    p_doc.add_argument("--no-network", action="store_true", help="Skip remote endpoint connectivity checks")
    p_doc.set_defaults(func=cmd_doctor)

    # hg run
    p_run = subparsers.add_parser("run", help="Run end-to-end transformation pipeline (Stages 01-06)")
    p_run.add_argument("input", nargs="?", default=None, help="Input source document (PDF, CSV, JSON) or run dir")
    p_run.add_argument("--run-dir", default=None, help="Existing pipeline run workspace directory")
    p_run.add_argument("--mirror", default=None, help="Path to local KG mirror snapshot (.nt/.ttl)")
    p_run.add_argument("--cache-dir", default=None, help="Cache directory holding snapshot")
    p_run.add_argument("--ontology", default="heritagegraph", help="Ontology mapping (default: heritagegraph)")
    p_run.add_argument("--base", default="https://cair-nepal.org/heritagegraph/", help="Base URI for local minting")
    p_run.add_argument("--shapes", default=None, help="Path to SHACL shapes file")
    p_run.add_argument("--interactive", "-i", action="store_true", help="Enable HITL interactive review in Stage 2")
    p_run.set_defaults(func=cmd_run)

    # hg diff
    p_diff = subparsers.add_parser("diff", help="Diff triplified graph against local KG mirror (Stage 05)")
    p_diff.add_argument("graph", nargs="?", default=None, help="Path to 03_graph.ttl or run directory")
    p_diff.add_argument("--run-dir", default=None, help="Pipeline run directory")
    p_diff.add_argument("--mirror", required=True, help="Path to local KG mirror snapshot (.nt/.ttl)")
    p_diff.add_argument("--out", default=None, help="Output diff report JSON path")
    p_diff.add_argument("--no-fail", action="store_true", help="Do not exit with error on suspected duplicates")
    p_diff.set_defaults(func=cmd_diff)

    # hg bundle
    p_bundle = subparsers.add_parser("bundle", help="Package a completed run into a contribution bundle (Stage 06)")
    p_bundle.add_argument("run_dir", nargs="?", default=None, help="Pipeline run directory")
    p_bundle.add_argument("--out", default=None, help="Output contribution bundle directory")
    p_bundle.add_argument("--run-id", default=None, help="Override contribution run ID")
    p_bundle.set_defaults(func=cmd_bundle)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
