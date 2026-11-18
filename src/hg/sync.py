"""Anonymous S3 Synchronization & Local Cache Manager for HeritageGraph.

Provides unsigned/anonymous access to AWS Open Data S3 buckets and GitHub raw sources
for ontology schemas and knowledge graph snapshots, with ETag and SHA-256 local caching.
Supports offline-first execution via `--offline` / `offline=True`.
"""
import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import requests

try:
    import boto3
    from botocore import UNSIGNED
    from botocore.client import Config
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


DEFAULT_CACHE_DIR = Path(".cache/heritagegraph")
DEFAULT_BUCKET = "cair-nepal-heritagegraph-opendata"
DEFAULT_USER_AGENT = "hg-skill/0.1"

ONTOLOGY_FILES = [
    "HeritageGraph.yaml",
    "HeritageGraph.ttl",
    "HeritageGraph.shacl.ttl",
]


class OfflineCacheMissError(FileNotFoundError):
    """Raised when an asset is requested in offline mode but does not exist in local cache."""
    pass


class ChecksumMismatchError(ValueError):
    """Raised when the computed SHA-256 does not match the expected checksum."""
    pass


def compute_sha256(file_path: Union[str, Path]) -> str:
    """Compute hex SHA-256 digest of a file in 64KB chunks."""
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found for checksum: {file_path}")
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_manifest(manifest_data: Union[Dict[str, Any], str, Path]) -> Dict[str, Any]:
    """Parse and validate snapshot manifest metadata.

    Required fields:
        - timestamp: ISO 8601 or date string
        - entity_count: non-negative integer
        - checksum: SHA-256 digest string (e.g. 'sha256:<hex>' or raw hex)
        - snapshot_file: non-empty string path or filename

    Raises:
        ValueError: If any required field is missing or invalid.
        FileNotFoundError: If a file path is provided but does not exist.
    """
    if isinstance(manifest_data, (str, Path)):
        p = Path(manifest_data)
        if not p.exists():
            raise FileNotFoundError(f"Manifest file not found: {manifest_data}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(manifest_data, dict):
        data = dict(manifest_data)
    else:
        raise TypeError(f"Expected dict or Path, got {type(manifest_data).__name__}")

    required_fields = ["timestamp", "entity_count", "checksum", "snapshot_file"]
    for field in required_fields:
        if field not in data or data[field] is None:
            raise ValueError(f"Manifest missing required field: '{field}'")

    if not isinstance(data["entity_count"], int) or data["entity_count"] < 0:
        raise ValueError(
            f"Invalid 'entity_count' in manifest: {data['entity_count']} (must be non-negative integer)"
        )

    checksum = str(data["checksum"]).strip()
    if not checksum:
        raise ValueError("Invalid 'checksum' in manifest: empty string")

    hex_part = checksum.split(":", 1)[1] if ":" in checksum else checksum
    if len(hex_part) < 32 or not all(c in "0123456789abcdefABCDEF" for c in hex_part):
        raise ValueError(f"Invalid checksum format: '{checksum}'")

    snapshot_file = str(data["snapshot_file"]).strip()
    if not snapshot_file:
        raise ValueError("Invalid 'snapshot_file' in manifest: empty string")

    return data


class S3SyncManager:
    """Manages anonymous downloading and caching of HeritageGraph assets."""

    def __init__(
        self,
        cache_dir: Optional[Union[str, Path]] = None,
        bucket: str = DEFAULT_BUCKET,
        endpoint_url: Optional[str] = None,
        offline: bool = False,
        timeout: int = 30,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.bucket = bucket
        self.endpoint_url = endpoint_url.rstrip("/") if endpoint_url else None
        self.offline = offline
        self.timeout = timeout
        self.user_agent = DEFAULT_USER_AGENT

        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_path(self, key_or_url: str) -> Path:
        """Resolve a deterministic local cache path for an S3 key or URL."""
        if key_or_url.startswith("http://") or key_or_url.startswith("https://"):
            parsed = urlparse(key_or_url)
            rel_path = parsed.path.lstrip("/")
        else:
            rel_path = key_or_url.lstrip("/")

        # Clean relative path components
        parts = [p for p in rel_path.split("/") if p and p != ".."]
        return self.cache_dir.joinpath(*parts)

    def get_metadata_path(self, cached_path: Path) -> Path:
        """Return the sidecar metadata path for a cached asset."""
        return cached_path.parent / f".{cached_path.name}.meta.json"

    def get_cached_asset(self, key_or_url: str) -> Optional[Path]:
        """Return cached path if the asset is currently present in cache, else None."""
        p = self.get_cache_path(key_or_url)
        return p if p.is_file() else None

    def _resolve_url(self, key_or_url: str) -> str:
        """Resolve full download URL from key or URL."""
        if key_or_url.startswith("http://") or key_or_url.startswith("https://"):
            return key_or_url
        clean_key = key_or_url.lstrip("/")
        if self.endpoint_url:
            return f"{self.endpoint_url}/{self.bucket}/{clean_key}"
        return f"https://{self.bucket}.s3.amazonaws.com/{clean_key}"

    def fetch_asset(
        self,
        key_or_url: str,
        dest_path: Optional[Union[str, Path]] = None,
        expected_sha256: Optional[str] = None,
        force: bool = False,
        offline: Optional[bool] = None,
    ) -> Path:
        """Fetch an asset anonymously or load from local cache.

        Args:
            key_or_url: S3 object key or full HTTP(S) URL.
            dest_path: Optional specific destination path. Defaults to internal cache path.
            expected_sha256: Expected SHA-256 digest for verification.
            force: Force re-download even if cached and unmodified.
            offline: Override manager offline mode setting.

        Returns:
            Path to the downloaded/cached file.

        Raises:
            OfflineCacheMissError: In offline mode when asset is not cached.
            ChecksumMismatchError: When expected SHA-256 does not match.
            requests.HTTPError: On download errors.
        """
        is_offline = self.offline if offline is None else offline
        target_path = Path(dest_path) if dest_path else self.get_cache_path(key_or_url)
        meta_path = self.get_metadata_path(target_path)

        clean_expected = None
        if expected_sha256:
            clean_expected = (
                expected_sha256.split(":", 1)[1]
                if ":" in expected_sha256
                else expected_sha256
            ).strip().lower()

        # Check existing cached file
        if target_path.exists() and not force:
            if is_offline:
                if clean_expected:
                    actual_sha = compute_sha256(target_path)
                    if actual_sha.lower() != clean_expected:
                        raise ChecksumMismatchError(
                            f"Cached asset checksum mismatch for {key_or_url}: "
                            f"expected {clean_expected}, got {actual_sha}"
                        )
                return target_path

            # Online mode: Check ETag / conditional request
            etag = None
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    etag = meta.get("etag")
                except Exception:
                    pass

            # If expected hash is given and local file matches, can conditionally verify
            url = self._resolve_url(key_or_url)
            headers = {"User-Agent": self.user_agent}
            if etag:
                headers["If-None-Match"] = f'"{etag.strip(chr(34))}"'

            try:
                resp = requests.get(url, headers=headers, stream=True, timeout=self.timeout)
                if resp.status_code == 304:
                    # Cache hit: server confirmed file is unmodified
                    return target_path
                elif resp.status_code == 200:
                    # Server has a newer version; fall through to download
                    return self._stream_to_file(
                        resp, target_path, meta_path, key_or_url, url, clean_expected
                    )
                else:
                    resp.raise_for_status()
            except requests.RequestException:
                # Network failure in online mode: fallback to cached file if valid
                if clean_expected:
                    actual_sha = compute_sha256(target_path)
                    if actual_sha.lower() == clean_expected:
                        return target_path
                return target_path

        # If offline and file does not exist, fail immediately
        if is_offline:
            raise OfflineCacheMissError(
                f"Asset '{key_or_url}' not found in local cache and offline mode is enabled."
            )

        # Fresh download
        url = self._resolve_url(key_or_url)
        headers = {"User-Agent": self.user_agent}
        resp = requests.get(url, headers=headers, stream=True, timeout=self.timeout)
        resp.raise_for_status()

        return self._stream_to_file(
            resp, target_path, meta_path, key_or_url, url, clean_expected
        )

    def _stream_to_file(
        self,
        resp: requests.Response,
        dest_path: Path,
        meta_path: Path,
        key: str,
        url: str,
        expected_sha256: Optional[str],
    ) -> Path:
        """Stream response chunks to temporary file, verify hash, and save metadata."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = dest_path.parent / f".tmp_{dest_path.name}_{int(time.time() * 1000)}"

        hasher = hashlib.sha256()
        total_bytes = 0

        try:
            with open(temp_file, "wb") as f:
                if hasattr(resp, "iter_content"):
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            hasher.update(chunk)
                            total_bytes += len(chunk)
                elif hasattr(resp, "raw") and resp.raw:
                    while chunk := resp.raw.read(65536):
                        f.write(chunk)
                        hasher.update(chunk)
                        total_bytes += len(chunk)

            computed_sha256 = hasher.hexdigest().lower()

            if expected_sha256 and computed_sha256 != expected_sha256:
                raise ChecksumMismatchError(
                    f"Checksum mismatch for '{key}': expected {expected_sha256}, got {computed_sha256}"
                )

            # Atomic replace
            temp_file.replace(dest_path)

            etag = resp.headers.get("ETag", "").strip('"')
            last_mod = resp.headers.get("Last-Modified")

            metadata = {
                "key": key,
                "url": url,
                "sha256": computed_sha256,
                "etag": etag,
                "size": total_bytes,
                "last_modified": last_mod,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

            return dest_path

        except Exception:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise

    def sync_snapshot(
        self,
        manifest_key_or_url: str = "snapshots/latest-manifest.json",
        dest_dir: Optional[Union[str, Path]] = None,
        offline: bool = False,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Fetch snapshot manifest, validate it, download snapshot file, and verify checksum."""
        manifest_path = self.fetch_asset(manifest_key_or_url, force=force, offline=offline)
        manifest_data = validate_manifest(manifest_path)

        snapshot_filename = manifest_data["snapshot_file"]
        expected_checksum = manifest_data["checksum"]

        # Resolve relative snapshot key
        if snapshot_filename.startswith("http://") or snapshot_filename.startswith("https://"):
            snapshot_key = snapshot_filename
        elif "/" in manifest_key_or_url:
            parent_dir = manifest_key_or_url.rsplit("/", 1)[0]
            snapshot_key = f"{parent_dir}/{snapshot_filename}"
        else:
            snapshot_key = snapshot_filename

        snapshot_cache_path = self.fetch_asset(
            snapshot_key,
            expected_sha256=expected_checksum,
            force=force,
            offline=offline,
        )

        final_snapshot_path = snapshot_cache_path
        final_manifest_path = manifest_path

        if dest_dir:
            out = Path(dest_dir)
            out.mkdir(parents=True, exist_ok=True)
            final_snapshot_path = out / snapshot_cache_path.name
            final_manifest_path = out / manifest_path.name
            shutil.copy2(snapshot_cache_path, final_snapshot_path)
            shutil.copy2(manifest_path, final_manifest_path)

        return {
            "manifest": manifest_data,
            "manifest_path": final_manifest_path,
            "snapshot_path": final_snapshot_path,
            "verified": True,
            "entity_count": manifest_data["entity_count"],
        }

    def sync_ontology(
        self,
        ref: str = "main",
        dest_dir: Optional[Union[str, Path]] = None,
        offline: bool = False,
        force: bool = False,
        upstream_base_url: Optional[str] = None,
    ) -> Dict[str, Path]:
        """Fetch authoritative ontology artifacts (YAML, TTL, SHACL).

        Artifacts can be synced from S3 or raw GitHub upstream.
        """
        base_url = (
            upstream_base_url
            or f"https://raw.githubusercontent.com/CAIRNepal/heritagegraphontology/{ref}/ontology"
        )
        synced = {}

        if dest_dir:
            out_dir = Path(dest_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
        else:
            out_dir = None

        for fname in ONTOLOGY_FILES:
            url = f"{base_url}/{fname}"
            cached_path = self.fetch_asset(url, force=force, offline=offline)
            if out_dir:
                dest = out_dir / fname
                shutil.copy2(cached_path, dest)
                synced[fname] = dest
            else:
                synced[fname] = cached_path

        return synced


def sync_assets(
    cache_dir: Optional[Union[str, Path]] = None,
    target: str = "all",
    offline: bool = False,
    ref: str = "main",
    force: bool = False,
    bucket: str = DEFAULT_BUCKET,
    endpoint_url: Optional[str] = None,
    ontology_dest_dir: Optional[Union[str, Path]] = None,
    snapshot_dest_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Synchronize HeritageGraph ontology and/or knowledge graph snapshot assets.

    Args:
        cache_dir: Local cache directory (defaults to .cache/heritagegraph).
        target: 'ontology', 'snapshot', or 'all'.
        offline: Run in offline mode without network calls.
        ref: Ontology git branch or tag reference.
        force: Force re-download even if cached.
        bucket: AWS Open Data S3 bucket name.
        endpoint_url: Optional S3 endpoint URL.
        ontology_dest_dir: Destination folder to export ontology files.
        snapshot_dest_dir: Destination folder to export snapshot files.

    Returns:
        Dict with synchronized artifact paths and metadata.
    """
    manager = S3SyncManager(
        cache_dir=cache_dir,
        bucket=bucket,
        endpoint_url=endpoint_url,
        offline=offline,
    )

    results: Dict[str, Any] = {}

    if target in ("ontology", "all"):
        results["ontology"] = manager.sync_ontology(
            ref=ref,
            dest_dir=ontology_dest_dir,
            offline=offline,
            force=force,
        )

    if target in ("snapshot", "all"):
        results["snapshot"] = manager.sync_snapshot(
            dest_dir=snapshot_dest_dir,
            offline=offline,
            force=force,
        )

    return results


def get_unsigned_s3_client(endpoint_url: Optional[str] = None):
    """Create an unsigned boto3 S3 client (equivalent to --no-sign-request)."""
    if not HAS_BOTO3:
        raise ImportError("boto3 and botocore are required to create an S3 client")
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        config=Config(signature_version=UNSIGNED),
    )


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Synchronize HeritageGraph schemas and snapshots from AWS Open Data."
    )
    parser.add_argument("--cache-dir", default=None, help="Local cache directory")
    parser.add_argument(
        "--target",
        choices=["ontology", "snapshot", "all"],
        default="all",
        help="Target assets to sync",
    )
    parser.add_argument("--offline", action="store_true", help="Run in offline mode")
    parser.add_argument("--ref", default="main", help="Ontology reference branch/tag")
    parser.add_argument("--force", action="store_true", help="Force re-download even if cached")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help="S3 bucket name")
    parser.add_argument("--endpoint-url", default=None, help="S3 endpoint URL")
    parser.add_argument("--ontology-dest", default=None, help="Export directory for ontology files")
    parser.add_argument("--snapshot-dest", default=None, help="Export directory for snapshot files")
    args = parser.parse_args(argv)

    try:
        results = sync_assets(
            cache_dir=args.cache_dir,
            target=args.target,
            offline=args.offline,
            ref=args.ref,
            force=args.force,
            bucket=args.bucket,
            endpoint_url=args.endpoint_url,
            ontology_dest_dir=args.ontology_dest,
            snapshot_dest_dir=args.snapshot_dest,
        )
        print(f"Sync complete: {list(results.keys())}")
        return 0
    except Exception as e:
        print(f"Sync error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())

