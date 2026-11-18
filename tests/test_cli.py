"""Tests for Unified hg CLI Facade and Doctor Diagnostics (Ticket 6 / #42)."""
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

for d in (SRC_DIR,):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from hg.cli import build_parser, main as cli_main
from hg.doctor import check_python_version, check_packages, check_cache, run_doctor


def test_python_version_check():
    """Verify python version check detects Python >= 3.10."""
    ok, msg = check_python_version()
    assert ok is True
    assert "3." in msg


def test_packages_check():
    """Verify check_packages reports installed status."""
    pkgs = [("pyoxigraph", "pyoxigraph"), ("rdflib", "rdflib"), ("nonexistent_pkg_12345", "nonexistent_pkg_12345")]
    res = check_packages(pkgs)
    assert len(res) == 3
    assert res[0]["installed"] is True
    assert res[1]["installed"] is True
    assert res[2]["installed"] is False


def test_cache_check(tmp_path):
    """Verify check_cache detects empty vs populated cache directories."""
    # Empty cache
    empty_dir = tmp_path / "empty_cache"
    c_info = check_cache(empty_dir)
    assert c_info["exists"] is False
    assert c_info["ontology_cached"] is False

    # Populated cache
    pop_dir = tmp_path / "pop_cache"
    (pop_dir / "ontology").mkdir(parents=True)
    (pop_dir / "ontology" / "HeritageGraph.yaml").write_text("name: test", encoding="utf-8")
    (pop_dir / "snapshots").mkdir(parents=True)
    (pop_dir / "snapshots" / "kg-2026-11-18.nt").write_text("<http://a> <http://b> <http://c> .", encoding="utf-8")

    c_info_pop = check_cache(pop_dir)
    assert c_info_pop["exists"] is True
    assert c_info_pop["ontology_cached"] is True
    assert c_info_pop["snapshots_cached"] is True
    assert "kg-2026-11-18.nt" in c_info_pop["snapshot_files"]


def test_doctor_execution(tmp_path):
    """Verify run_doctor returns healthy status with mocked/local cache."""
    report = run_doctor(cache_dir=tmp_path, check_network=False, verbose=False)
    assert "healthy" in report
    assert "python" in report
    assert "required_packages" in report
    assert report["healthy"] is True


def test_cli_parser_commands():
    """Verify CLI parser has all expected subcommands."""
    parser = build_parser()
    subparsers_actions = [
        action for action in parser._actions if isinstance(action, type(parser._subparsers._actions[0]))
    ]
    choices = parser._subparsers._actions[1].choices
    assert "sync" in choices
    assert "doctor" in choices
    assert "run" in choices
    assert "diff" in choices
    assert "bundle" in choices


def test_cli_doctor_command():
    """Verify 'hg doctor --no-network' exits with code 0."""
    rc = cli_main(["doctor", "--no-network"])
    assert rc == 0


def test_cli_sync_offline_mode(tmp_path):
    """Verify 'hg sync --offline --snapshots-only' passes arguments to sync manager."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "snapshots").mkdir()
    import hashlib
    content = b"<http://s> <http://p> <http://o> ."
    content_sha = hashlib.sha256(content).hexdigest()
    (cache_dir / "snapshots" / "kg-test.nt").write_bytes(content)
    (cache_dir / "snapshots" / "latest-manifest.json").write_text(json.dumps({
        "timestamp": "2026-11-18T00:00:00Z",
        "entity_count": 1,
        "checksum": content_sha,
        "snapshot_file": "kg-test.nt",
    }), encoding="utf-8")

    rc = cli_main(["sync", "--offline", "--snapshots-only", "--cache-dir", str(cache_dir)])
    assert rc == 0


def test_cli_bundle_command(tmp_path):
    """Verify 'hg bundle' packages a run directory."""
    run_dir = tmp_path / "run-cli-test"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": "test"}), encoding="utf-8")
    (run_dir / "03_graph.ttl").write_text(
        "<https://cair-nepal.org/heritagegraph/test> <http://www.w3.org/2000/01/rdf-schema#label> \"Test\" .",
        encoding="utf-8",
    )
    bundle_out = tmp_path / "bundle-cli-out"

    rc = cli_main(["bundle", str(run_dir), "--out", str(bundle_out)])
    assert rc == 0
    assert (bundle_out / "bundle.json").exists()
    assert (bundle_out / "contribution-graph.nq").exists()
