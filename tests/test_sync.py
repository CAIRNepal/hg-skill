"""Tests for Anonymous S3 Synchronization and Local Cache Manager (Ticket 1 / #37).

Tests cover:
- Anonymous fetch (no signing, unsigned requests equivalent to AWS Open Data / --no-sign-request).
- Local caching (cache miss downloads and stores with ETag and SHA-256, cache hit verifies/avoids re-download).
- Offline mode (offline=True returns cached artifacts without network, raises FileNotFoundError if missing).
- Manifest validation (validates timestamp, entity_count, checksum, snapshot_file).
- Snapshot and ontology artifact synchronization.
"""
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from hg.sync import (
    OfflineCacheMissError,
    S3SyncManager,
    compute_sha256,
    sync_assets,
    validate_manifest,
)


@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def mock_snapshot_content():
    return b"<http://example.org/s> <http://example.org/p> <http://example.org/o> .\n"


@pytest.fixture
def mock_snapshot_sha256(mock_snapshot_content):
    return hashlib.sha256(mock_snapshot_content).hexdigest()


@pytest.fixture
def mock_manifest_data(mock_snapshot_sha256):
    return {
        "timestamp": "2026-11-01T00:00:00Z",
        "entity_count": 142050,
        "checksum": f"sha256:{mock_snapshot_sha256}",
        "snapshot_file": "heritagegraph-snapshot-2026-11-01.nt",
        "schema_version": "1.0.1",
    }


def test_anonymous_fetch_no_sign_request(cache_dir, mock_snapshot_content):
    """Anonymous fetch must NOT send AWS auth headers or tokens (equivalent to --no-sign-request)."""
    manager = S3SyncManager(cache_dir=cache_dir, bucket="cair-nepal-heritagegraph-opendata")
    
    intercepted_headers = {}

    def mock_get(url, headers=None, stream=False, timeout=None):
        nonlocal intercepted_headers
        intercepted_headers = headers or {}
        resp = requests.Response()
        resp.status_code = 200
        resp.raw = io.BytesIO(mock_snapshot_content)
        resp.headers["ETag"] = '"test-etag-1234"'
        resp.headers["Content-Length"] = str(len(mock_snapshot_content))
        return resp

    with patch("requests.get", side_effect=mock_get):
        dest = manager.fetch_asset("snapshots/test.nt")
        assert dest.exists()
        assert dest.read_bytes() == mock_snapshot_content

    # Verify no Authorization or AWS signature tokens were sent
    for h in intercepted_headers:
        assert not h.lower().startswith("authorization")
        assert not h.lower().startswith("x-amz-security-token")
        assert "aws4" not in intercepted_headers[h].lower()


def test_cache_miss_downloads_and_saves_metadata(cache_dir, mock_snapshot_content, mock_snapshot_sha256):
    """Cache miss downloads the asset and writes metadata with ETag and SHA-256."""
    manager = S3SyncManager(cache_dir=cache_dir)
    
    def mock_get(url, headers=None, stream=False, timeout=None):
        resp = requests.Response()
        resp.status_code = 200
        resp.raw = io.BytesIO(mock_snapshot_content)
        resp.headers["ETag"] = '"etag-abc-999"'
        resp.headers["Last-Modified"] = "Sun, 01 Nov 2026 00:00:00 GMT"
        return resp

    with patch("requests.get", side_effect=mock_get):
        dest = manager.fetch_asset("snapshots/test.nt")
        assert dest.exists()
        assert dest.read_bytes() == mock_snapshot_content

        meta_path = manager.get_metadata_path(dest)
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["etag"] == "etag-abc-999"
        assert meta["sha256"] == mock_snapshot_sha256
        assert meta["size"] == len(mock_snapshot_content)


def test_cache_hit_conditional_request_304(cache_dir, mock_snapshot_content, mock_snapshot_sha256):
    """Cache hit performs conditional HTTP GET with If-None-Match; 304 avoids re-download."""
    manager = S3SyncManager(cache_dir=cache_dir)

    # Prime the cache
    asset_path = manager.get_cache_path("snapshots/test.nt")
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(mock_snapshot_content)
    meta_path = manager.get_metadata_path(asset_path)
    meta_path.write_text(json.dumps({
        "etag": "etag-abc-999",
        "sha256": mock_snapshot_sha256,
        "size": len(mock_snapshot_content)
    }), encoding="utf-8")

    sent_headers = {}

    def mock_get(url, headers=None, stream=False, timeout=None):
        nonlocal sent_headers
        sent_headers = headers or {}
        resp = requests.Response()
        resp.status_code = 304  # Not Modified
        return resp

    with patch("requests.get", side_effect=mock_get):
        dest = manager.fetch_asset("snapshots/test.nt")
        assert dest == asset_path
        assert dest.read_bytes() == mock_snapshot_content
        assert sent_headers.get("If-None-Match") == '"etag-abc-999"'


def test_offline_mode_returns_cached_asset(cache_dir, mock_snapshot_content, mock_snapshot_sha256):
    """In offline mode, existing cached artifacts are returned without any network request."""
    manager = S3SyncManager(cache_dir=cache_dir, offline=True)

    # Pre-populate cache
    asset_path = manager.get_cache_path("snapshots/offline_test.nt")
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(mock_snapshot_content)
    meta_path = manager.get_metadata_path(asset_path)
    meta_path.write_text(json.dumps({
        "etag": "etag-123",
        "sha256": mock_snapshot_sha256,
        "size": len(mock_snapshot_content)
    }), encoding="utf-8")

    with patch("requests.get") as mock_req:
        dest = manager.fetch_asset("snapshots/offline_test.nt")
        assert dest == asset_path
        assert dest.read_bytes() == mock_snapshot_content
        mock_req.assert_not_called()


def test_offline_mode_missing_cache_raises_error(cache_dir):
    """In offline mode, if asset is not in cache, raise OfflineCacheMissError."""
    manager = S3SyncManager(cache_dir=cache_dir, offline=True)

    with patch("requests.get") as mock_req:
        with pytest.raises(OfflineCacheMissError) as exc_info:
            manager.fetch_asset("snapshots/non_existent.nt")
        assert "offline mode" in str(exc_info.value).lower()
        mock_req.assert_not_called()


def test_manifest_validation_success(mock_manifest_data):
    """Valid manifest must pass validation and return normalized dictionary."""
    validated = validate_manifest(mock_manifest_data)
    assert validated["timestamp"] == "2026-11-01T00:00:00Z"
    assert validated["entity_count"] == 142050
    assert validated["snapshot_file"] == "heritagegraph-snapshot-2026-11-01.nt"
    assert validated["checksum"].startswith("sha256:")


def test_manifest_validation_failures():
    """Missing or invalid manifest fields must raise ValueError with descriptive errors."""
    # Missing timestamp
    with pytest.raises(ValueError, match="timestamp"):
        validate_manifest({
            "entity_count": 100,
            "checksum": "sha256:abc",
            "snapshot_file": "snap.nt"
        })

    # Missing entity_count
    with pytest.raises(ValueError, match="entity_count"):
        validate_manifest({
            "timestamp": "2026-11-01T00:00:00Z",
            "checksum": "sha256:abc",
            "snapshot_file": "snap.nt"
        })

    # Negative entity_count
    with pytest.raises(ValueError, match="entity_count"):
        validate_manifest({
            "timestamp": "2026-11-01T00:00:00Z",
            "entity_count": -10,
            "checksum": "sha256:abc",
            "snapshot_file": "snap.nt"
        })

    # Missing checksum
    with pytest.raises(ValueError, match="checksum"):
        validate_manifest({
            "timestamp": "2026-11-01T00:00:00Z",
            "entity_count": 100,
            "snapshot_file": "snap.nt"
        })

    # Missing snapshot_file
    with pytest.raises(ValueError, match="snapshot_file"):
        validate_manifest({
            "timestamp": "2026-11-01T00:00:00Z",
            "entity_count": 100,
            "checksum": "sha256:abc"
        })


def test_checksum_mismatch_raises_error(cache_dir, mock_snapshot_content):
    """Fetching an asset with expected_sha256 mismatch raises ValueError and cleans up."""
    manager = S3SyncManager(cache_dir=cache_dir)

    def mock_get(url, headers=None, stream=False, timeout=None):
        resp = requests.Response()
        resp.status_code = 200
        resp.raw = io.BytesIO(mock_snapshot_content)
        resp.headers["ETag"] = '"etag-abc"'
        return resp

    wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"
    with patch("requests.get", side_effect=mock_get):
        with pytest.raises(ValueError, match="(?i)checksum mismatch"):
            manager.fetch_asset("snapshots/corrupt.nt", expected_sha256=wrong_hash)

    # Destination should not exist
    dest = manager.get_cache_path("snapshots/corrupt.nt")
    assert not dest.exists()


def test_sync_snapshot(cache_dir, mock_manifest_data, mock_snapshot_content):
    """sync_snapshot fetches manifest, validates it, and fetches the snapshot file."""
    manager = S3SyncManager(cache_dir=cache_dir)

    manifest_bytes = json.dumps(mock_manifest_data).encode("utf-8")

    def mock_get(url, headers=None, stream=False, timeout=None):
        resp = requests.Response()
        resp.status_code = 200
        if "manifest" in url:
            resp.raw = io.BytesIO(manifest_bytes)
            resp.headers["ETag"] = '"manifest-etag"'
        else:
            resp.raw = io.BytesIO(mock_snapshot_content)
            resp.headers["ETag"] = '"snapshot-etag"'
        return resp

    with patch("requests.get", side_effect=mock_get):
        result = manager.sync_snapshot("snapshots/latest-manifest.json")
        assert result["verified"] is True
        assert result["entity_count"] == 142050
        assert Path(result["manifest_path"]).exists()
        assert Path(result["snapshot_path"]).exists()
        assert Path(result["snapshot_path"]).read_bytes() == mock_snapshot_content


def test_sync_ontology(cache_dir, tmp_path):
    """sync_ontology downloads LinkML schema, ontology TTL, and SHACL shapes."""
    dest_dir = tmp_path / "schemas_out"
    manager = S3SyncManager(cache_dir=cache_dir)

    def mock_get(url, headers=None, stream=False, timeout=None):
        resp = requests.Response()
        resp.status_code = 200
        resp.raw = io.BytesIO(b"# mock ontology file\n")
        resp.headers["ETag"] = '"ontology-etag"'
        return resp

    with patch("requests.get", side_effect=mock_get):
        synced = manager.sync_ontology(ref="v1.0.1", dest_dir=dest_dir)
        assert "HeritageGraph.yaml" in synced
        assert "HeritageGraph.ttl" in synced
        assert "HeritageGraph.shacl.ttl" in synced

        for fname, fpath in synced.items():
            assert Path(fpath).exists()
            assert Path(dest_dir / fname).exists()


def test_sync_assets_convenience_function(cache_dir, mock_manifest_data, mock_snapshot_content, tmp_path):
    """sync_assets convenience wrapper syncs ontology and snapshots."""
    manifest_bytes = json.dumps(mock_manifest_data).encode("utf-8")

    def mock_get(url, headers=None, stream=False, timeout=None):
        resp = requests.Response()
        resp.status_code = 200
        if "manifest" in url:
            resp.raw = io.BytesIO(manifest_bytes)
        elif "snapshot" in url:
            resp.raw = io.BytesIO(mock_snapshot_content)
        else:
            resp.raw = io.BytesIO(b"# mock schema\n")
        resp.headers["ETag"] = '"etag"'
        return resp

    with patch("requests.get", side_effect=mock_get):
        res = sync_assets(cache_dir=cache_dir, target="all", ontology_dest_dir=tmp_path / "schemas")
        assert "ontology" in res
        assert "snapshot" in res
        assert res["snapshot"]["verified"] is True


def test_get_cached_asset(cache_dir, mock_snapshot_content):
    """get_cached_asset returns Path if present, None if missing."""
    manager = S3SyncManager(cache_dir=cache_dir)
    assert manager.get_cached_asset("snapshots/test.nt") is None

    p = manager.get_cache_path("snapshots/test.nt")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(mock_snapshot_content)

    assert manager.get_cached_asset("snapshots/test.nt") == p


def test_validate_manifest_file_and_types(tmp_path, mock_manifest_data):
    """validate_manifest parses file on disk and validates types."""
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(mock_manifest_data), encoding="utf-8")

    parsed = validate_manifest(manifest_file)
    assert parsed["entity_count"] == 142050

    # Non-existent file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        validate_manifest(tmp_path / "does_not_exist.json")

    # Invalid input type raises TypeError
    with pytest.raises(TypeError):
        validate_manifest(12345)


def test_sync_cli_main(cache_dir, mock_manifest_data, mock_snapshot_content, tmp_path):
    """CLI main function exits 0 on successful sync."""
    from hg.sync import main

    manifest_bytes = json.dumps(mock_manifest_data).encode("utf-8")

    def mock_get(url, headers=None, stream=False, timeout=None):
        resp = requests.Response()
        resp.status_code = 200
        if "manifest" in url:
            resp.raw = io.BytesIO(manifest_bytes)
        elif "snapshot" in url:
            resp.raw = io.BytesIO(mock_snapshot_content)
        else:
            resp.raw = io.BytesIO(b"# mock\n")
        resp.headers["ETag"] = '"etag"'
        return resp

    with patch("requests.get", side_effect=mock_get):
        ret = main([
            "--cache-dir", str(cache_dir),
            "--target", "all",
            "--ontology-dest", str(tmp_path / "schemas"),
        ])
        assert ret == 0

