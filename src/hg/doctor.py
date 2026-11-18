"""Diagnostic health checks for HeritageGraph environment (hg doctor).

Follows the REA principle: lightweight, non-blocking diagnostic checks
run on-demand or when something fails. Checks:
  - Python version (>= 3.10)
  - Core package dependencies (pyoxigraph, rdflib, pyshacl, requests, linkml)
  - Local cache status (ontology artifacts, latest KG snapshot)
  - External network reachability (AWS Open Data S3, Wikidata, Getty, Yale LUX)

Returns 0 if all required components are operational, 1 if critical components fail.
"""
import importlib
import json
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.request

REQUIRED_PACKAGES = [
    ("pyoxigraph", "pyoxigraph"),
    ("rdflib", "rdflib"),
    ("pyshacl", "pyshacl"),
    ("requests", "requests"),
    ("linkml", "linkml"),
]

OPTIONAL_PACKAGES = [
    ("boto3", "boto3"),
    ("luxy", "luxy"),
    ("pypdf", "pypdf"),
    ("openpyxl", "openpyxl"),
]

ENDPOINTS = [
    ("Wikidata SPARQL", "https://query.wikidata.org/sparql"),
    ("Getty Vocabularies", "http://vocab.getty.edu/aat/300000000.json"),
    ("Yale LUX API", "https://lux.collections.yale.edu/api/search/concepts"),
    ("AWS Open Data S3", "https://cair-nepal-heritagegraph.s3.amazonaws.com/"),
]


def check_python_version() -> Tuple[bool, str]:
    """Check if Python is at least 3.10."""
    v = sys.version_info
    v_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 10):
        return True, f"Python {v_str} (>= 3.10 required)"
    return False, f"Python {v_str} is below required 3.10"


def check_packages(packages: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """Check importability and versions of python packages."""
    results = []
    for pkg_name, import_name in packages:
        try:
            mod = importlib.import_module(import_name)
            ver = getattr(mod, "__version__", "installed")
            results.append({"name": pkg_name, "installed": True, "version": str(ver)})
        except ImportError:
            results.append({"name": pkg_name, "installed": False, "version": None})
    return results


def check_cache(cache_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Check status of local HeritageGraph cache."""
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "heritagegraph"
        if not cache_dir.exists():
            cache_dir = Path(".cache/heritagegraph")

    exists = cache_dir.exists()
    ontology_present = False
    snapshots_present = False
    snapshot_files: List[str] = []

    if exists:
        onto_dir = cache_dir / "ontology"
        if onto_dir.exists():
            ontology_present = any(onto_dir.glob("*.yaml")) or any(onto_dir.glob("*.ttl"))
        snap_dir = cache_dir / "snapshots"
        if snap_dir.exists():
            files = list(snap_dir.glob("*.nt")) + list(snap_dir.glob("*.ttl"))
            snapshots_present = len(files) > 0
            snapshot_files = [f.name for f in files]

    return {
        "cache_dir": str(cache_dir),
        "exists": exists,
        "ontology_cached": ontology_present,
        "snapshots_cached": snapshots_present,
        "snapshot_files": snapshot_files,
    }


def check_endpoint(name: str, url: str, timeout: float = 2.0) -> Tuple[bool, str]:
    """Check connectivity to an external endpoint."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hg-doctor/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except Exception as exc:
        return False, str(exc)


def run_doctor(
    cache_dir: Optional[Path] = None,
    check_network: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Execute all diagnostic checks and print a structured report."""
    report: Dict[str, Any] = {
        "healthy": True,
        "warnings": [],
        "errors": [],
    }

    # 1. Python version
    py_ok, py_msg = check_python_version()
    report["python"] = {"ok": py_ok, "message": py_msg}
    if not py_ok:
        report["healthy"] = False
        report["errors"].append(py_msg)

    # 2. Required Packages
    req_pkgs = check_packages(REQUIRED_PACKAGES)
    report["required_packages"] = req_pkgs
    for p in req_pkgs:
        if not p["installed"]:
            report["healthy"] = False
            report["errors"].append(f"Missing required package: {p['name']} (install via pip)")

    # 3. Optional Packages
    opt_pkgs = check_packages(OPTIONAL_PACKAGES)
    report["optional_packages"] = opt_pkgs
    for p in opt_pkgs:
        if not p["installed"]:
            report["warnings"].append(f"Optional package not installed: {p['name']}")

    # 4. Cache status
    cache_info = check_cache(cache_dir)
    report["cache"] = cache_info
    if not cache_info["exists"] or not cache_info["snapshots_cached"]:
        report["warnings"].append(
            "Local KG mirror snapshot not cached. Run 'hg sync' to download latest snapshot."
        )

    # 5. Network reachability
    report["network"] = {}
    if check_network:
        for name, url in ENDPOINTS:
            ok, status = check_endpoint(name, url)
            report["network"][name] = {"ok": ok, "status": status}
            if not ok:
                report["warnings"].append(f"Endpoint unreachable: {name} ({status})")

    if verbose:
        print("=== HeritageGraph Doctor (hg doctor) ===")
        print(f"[{'OK' if py_ok else 'FAIL'}] {py_msg}")
        print("\nRequired Packages:")
        for p in req_pkgs:
            mark = "OK" if p["installed"] else "MISSING"
            print(f"  [{mark:7}] {p['name']:15} {p['version'] or ''}")
        print("\nOptional Packages:")
        for p in opt_pkgs:
            mark = "OK" if p["installed"] else "OPTIONAL"
            print(f"  [{mark:8}] {p['name']:15} {p['version'] or ''}")
        print(f"\nLocal Cache: {cache_info['cache_dir']}")
        print(f"  Ontology cached  : {'Yes' if cache_info['ontology_cached'] else 'No'}")
        print(f"  Snapshots cached : {'Yes' if cache_info['snapshots_cached'] else 'No'} ({len(cache_info['snapshot_files'])} file(s))")

        if check_network:
            print("\nNetwork Connectivity:")
            for name, n_info in report["network"].items():
                mark = "OK" if n_info["ok"] else "UNREACHABLE"
                print(f"  [{mark:11}] {name:20} ({n_info['status']})")

        print("\nSummary:")
        if report["healthy"]:
            print("  Environment is HEALTHY.")
            if report["warnings"]:
                print(f"  {len(report['warnings'])} non-critical warning(s):")
                for w in report["warnings"]:
                    print(f"    - {w}")
        else:
            print("  Environment has CRITICAL ISSUES:")
            for e in report["errors"]:
                print(f"    - {e}")

    return report


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="HeritageGraph environment diagnostics.")
    ap.add_argument("--cache-dir", default=None, help="Path to cache directory")
    ap.add_argument("--no-network", action="store_true", help="Skip remote endpoint connectivity checks")
    args = ap.parse_args(argv)

    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    rep = run_doctor(cache_dir=cache_dir, check_network=not args.no_network, verbose=True)
    return 0 if rep["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
