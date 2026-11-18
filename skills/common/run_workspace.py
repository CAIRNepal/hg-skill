#!/usr/bin/env python3
"""RunWorkspace and provenance manifest engine for the HeritageGraph pipeline.

Standardizes run directory lifecycle, stage-prefixed artifacts, and manifest.json
provenance tracking across skills 00_heritage-to-rdf through 04_heritage-shacl-validate.
Aligned with ADR-0003 and GLOSSARY.md.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_DIR = REPO_ROOT / "runs"

STAGE_ARTIFACTS = {
    0: "00_preprocessed.json",
    1: "01_extracted.json",
    2: "02_resolved.json",
    3: "03_graph.ttl",
    4: "04_shacl_report.json",
}

STAGE_NAMES = {
    0: "ingest",
    1: "extract",
    2: "resolve",
    3: "map",
    4: "validate",
}


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


def slugify(text: str) -> str:
    """Normalize a string to a clean filesystem slug."""
    text = Path(text).stem
    # Replace non-alphanumeric characters with hyphens
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:40] or "source"


def generate_run_id(source_name: str) -> str:
    """Generate a chronological run ID combining ISO date and normalized source slug."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = slugify(source_name)
    return f"{today}_{slug}"


def resolve_run_dir(
    source_path: Union[str, Path],
    run_dir: Optional[Union[str, Path]] = None,
    base_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """Resolve an isolated run directory.

    If run_dir is provided, ensures it exists and returns it.
    Otherwise creates a new folder under base_dir (default: REPO_ROOT/runs).
    """
    if run_dir:
        p = Path(run_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    base = Path(base_dir) if base_dir else DEFAULT_RUNS_DIR
    base.mkdir(parents=True, exist_ok=True)

    src_name = Path(source_path).name if source_path else "batch"
    run_id = generate_run_id(src_name)
    target = base / run_id

    # If run_id already exists, append incremental suffix
    counter = 1
    while target.exists() and any(target.iterdir()):
        target = base / f"{run_id}_{counter:02d}"
        counter += 1

    target.mkdir(parents=True, exist_ok=True)
    return target


def get_git_commit() -> Optional[str]:
    """Attempt to resolve the current git commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


class RunWorkspace:
    """Manages an isolated pipeline run directory and its manifest.json."""

    def __init__(self, run_dir: Union[str, Path]):
        self.run_dir = Path(run_dir).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.run_dir / "manifest.json"

    @classmethod
    def init(
        cls,
        source_path: Union[str, Path],
        run_dir: Optional[Union[str, Path]] = None,
        base_dir: Optional[Union[str, Path]] = None,
        schema_version: str = "1.0.1",
    ) -> "RunWorkspace":
        """Initialize a new RunWorkspace with a fresh manifest.json."""
        resolved = resolve_run_dir(source_path, run_dir=run_dir, base_dir=base_dir)
        ws = cls(resolved)

        src = Path(source_path).resolve() if source_path else None
        now_iso = datetime.now(timezone.utc).isoformat()

        source_info = {}
        if src and src.exists():
            source_info = {
                "file_path": str(src),
                "file_name": src.name,
                "byte_size": src.stat().st_size,
                "sha256": compute_sha256(src),
            }
        elif source_path:
            source_info = {
                "file_path": str(source_path),
                "file_name": Path(source_path).name,
            }

        manifest = {
            "run_id": resolved.name,
            "created_at": now_iso,
            "updated_at": now_iso,
            "status": "in_progress",
            "source": source_info,
            "environment": {
                "schema_version": schema_version,
                "git_commit": get_git_commit(),
                "python_version": sys.version.split()[0],
            },
            "stages": {},
            "summary": {},
        }
        ws.save_manifest(manifest)
        return ws

    @classmethod
    def find(cls, run_dir: Union[str, Path]) -> "RunWorkspace":
        """Load an existing RunWorkspace from an existing directory."""
        p = Path(run_dir).resolve()
        if not p.is_dir():
            raise FileNotFoundError(f"Run directory does not exist: {run_dir}")
        return cls(p)

    def load_manifest(self) -> Dict[str, Any]:
        """Load manifest.json data, returning empty dict if missing."""
        if not self.manifest_path.exists():
            return {}
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_manifest(self, data: Dict[str, Any]) -> None:
        """Atomically persist manifest.json."""
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp_path = self.manifest_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_path.replace(self.manifest_path)

    def artifact_path(self, stage_idx: int) -> Path:
        """Return the canonical file path for a stage artifact."""
        filename = STAGE_ARTIFACTS.get(stage_idx)
        if not filename:
            raise ValueError(f"Unknown stage index: {stage_idx}")
        return self.run_dir / filename

    def record_stage_start(
        self, stage_idx: int, stage_name: Optional[str] = None, meta: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record the start of a pipeline stage in manifest.json."""
        m = self.load_manifest()
        name = stage_name or STAGE_NAMES.get(stage_idx, f"stage_{stage_idx:02d}")
        key = f"stage_{stage_idx:02d}_{name}"

        stage_data = {
            "stage_index": stage_idx,
            "stage_name": name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "in_progress",
            "metadata": meta or {},
            "_start_perf": time.perf_counter(),
        }
        m.setdefault("stages", {})[key] = stage_data
        self.save_manifest(m)

    def record_stage_finish(
        self,
        stage_idx: int,
        stage_name: Optional[str] = None,
        status: str = "success",
        metrics: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Record completion of a pipeline stage in manifest.json."""
        m = self.load_manifest()
        name = stage_name or STAGE_NAMES.get(stage_idx, f"stage_{stage_idx:02d}")
        key = f"stage_{stage_idx:02d}_{name}"

        stage_data = m.get("stages", {}).get(key, {})
        start_perf = stage_data.pop("_start_perf", None)
        duration = round(time.perf_counter() - start_perf, 3) if start_perf else None

        stage_data.update(
            {
                "status": status,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration,
                "metrics": metrics or {},
            }
        )
        if error:
            stage_data["error"] = error

        if metrics:
            if "evidence_spans_count" in metrics:
                m.setdefault("summary", {})["evidence_spans_count"] = metrics["evidence_spans_count"]
                m["evidence_spans_count"] = metrics["evidence_spans_count"]
            if "sensitivity_breakdown" in metrics:
                m.setdefault("summary", {})["sensitivity_breakdown"] = metrics["sensitivity_breakdown"]
                m["sensitivity_breakdown"] = metrics["sensitivity_breakdown"]
            if "restricted_distribution" in metrics:
                m.setdefault("summary", {})["restricted_distribution"] = metrics["restricted_distribution"]
                m["restricted_distribution"] = metrics["restricted_distribution"]

        m.setdefault("stages", {})[key] = stage_data
        self.save_manifest(m)

    def record_evidence_and_rights(
        self,
        items_or_summary: Union[List[Dict[str, Any]], Dict[str, Any]],
        stage_idx: int = 1,
    ) -> Dict[str, Any]:
        """Record evidence spans count and sensitivity breakdown into manifest.json.

        Flags runs with restricted-sacred or guthi-internal content for restricted distribution.
        """
        m = self.load_manifest()

        if isinstance(items_or_summary, list):
            items = items_or_summary
            spans_count = sum(1 for it in items if it.get("evidence_span"))
            breakdown = {
                "public": sum(1 for it in items if it.get("sensitivity", "public") == "public"),
                "restricted-sacred": sum(1 for it in items if it.get("sensitivity") == "restricted-sacred"),
                "guthi-internal": sum(1 for it in items if it.get("sensitivity") == "guthi-internal"),
            }
            has_restricted = (
                breakdown["restricted-sacred"] > 0 or breakdown["guthi-internal"] > 0
            )
        elif isinstance(items_or_summary, dict):
            spans_count = items_or_summary.get(
                "evidence_spans_count",
                items_or_summary.get("total_evidence_spans", 0),
            )
            breakdown = items_or_summary.get(
                "sensitivity_breakdown",
                {
                    "public": items_or_summary.get("public", 0),
                    "restricted-sacred": items_or_summary.get("restricted-sacred", 0),
                    "guthi-internal": items_or_summary.get("guthi-internal", 0),
                },
            )
            has_restricted = items_or_summary.get(
                "restricted_distribution",
                (breakdown.get("restricted-sacred", 0) > 0 or breakdown.get("guthi-internal", 0) > 0),
            )
        else:
            raise TypeError("items_or_summary must be a list of records or a summary dict")

        summary_data = {
            "evidence_spans_count": spans_count,
            "sensitivity_breakdown": breakdown,
            "restricted_distribution": has_restricted,
        }

        m.setdefault("summary", {}).update(summary_data)
        m["evidence_spans_count"] = spans_count
        m["sensitivity_breakdown"] = breakdown
        m["restricted_distribution"] = has_restricted

        stage_name = STAGE_NAMES.get(stage_idx, f"stage_{stage_idx:02d}")
        key = f"stage_{stage_idx:02d}_{stage_name}"
        if key in m.get("stages", {}):
            m["stages"][key].setdefault("metrics", {}).update(summary_data)

        self.save_manifest(m)
        return summary_data

    def finalize(
        self, status: str = "completed", summary: Optional[Dict[str, Any]] = None
    ) -> None:
        """Mark the overall pipeline run as completed or failed."""
        m = self.load_manifest()
        m["status"] = status
        m["completed_at"] = datetime.now(timezone.utc).isoformat()
        if summary:
            m.setdefault("summary", {}).update(summary)
            for k in ("evidence_spans_count", "sensitivity_breakdown", "restricted_distribution"):
                if k in summary:
                    m[k] = summary[k]
        self.save_manifest(m)
