#!/usr/bin/env python3
"""Oxigraph mirror lookup provider for Stage 2 entity resolution.

Implements fast embedded KG mirror lookups using pyoxigraph, checking for exact
URIs and candidate entity matches via SPARQL 1.1 SELECT queries.
"""
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from hg.mirror import OxigraphMirror, load_mirror

_GLOBAL_MIRROR: Optional[OxigraphMirror] = None


def get_mirror(path_or_store: Optional[Union[str, Path, OxigraphMirror]] = None) -> OxigraphMirror:
    """Return active or cached OxigraphMirror."""
    global _GLOBAL_MIRROR
    if path_or_store is not None:
        return load_mirror(path_or_store)
    if _GLOBAL_MIRROR is None:
        _GLOBAL_MIRROR = OxigraphMirror()
    return _GLOBAL_MIRROR


def check_exact_uri(uri: str, mirror: Optional[OxigraphMirror] = None) -> bool:
    """Check if URI exists as subject or object in the mirror."""
    m = mirror or get_mirror()
    return m.check_exact_uri(uri)


def find_candidate_entities(
    label: str,
    entity_type: Optional[str] = None,
    limit: int = 5,
    mirror: Optional[OxigraphMirror] = None,
) -> List[Dict[str, Any]]:
    """Query mirror for candidate entities matching label and optional type."""
    m = mirror or get_mirror()
    return m.find_candidate_entities(label=label, entity_type=entity_type, limit=limit)


__all__ = [
    "OxigraphMirror",
    "load_mirror",
    "get_mirror",
    "check_exact_uri",
    "find_candidate_entities",
]
