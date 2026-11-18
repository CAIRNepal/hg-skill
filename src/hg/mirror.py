"""Embedded Oxigraph Store (pyoxigraph) and mirror resolution provider.

Provides local in-memory/on-disk RDF graph store querying and pre-flight entity
resolution against published HeritageGraph snapshots (ADR-0003, ADR-0004).
"""
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import pyoxigraph as ox

logger = logging.getLogger(__name__)

HG_BASE_URI = "https://cair-nepal.org/heritagegraph/"
HG_PREFIX = "heritageGraph:"


def fold(text: Optional[str]) -> str:
    """Normalize text by folding diacritics and converting to lowercase."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold().strip()


def _is_compatible_type(cand_type: Optional[str], requested_type: Optional[str]) -> bool:
    """Check if a candidate RDF type is compatible with requested type/kind."""
    if not requested_type or not cand_type:
        return True

    req = requested_type.strip().lower()
    cand = cand_type.strip().lower()

    if req in cand or cand in req:
        return True

    # Known class-kind semantic mappings
    kind_mappings = {
        "structure": ["monument", "architecturalstructure", "temple", "stupa", "chaitya", "resthouse", "dhungedhara", "pokhari"],
        "place": ["place", "administrativearea", "settlement"],
        "person": ["person", "actor"],
        "group": ["actor", "guthi", "castegroup", "organization"],
        "event": ["historicalevent", "ritualevent", "festival", "chariotfestival", "activity"],
        "object": ["humanmadeobject", "iconographicobject", "paubha", "murti"],
        "material": ["material"],
        "technique": ["technique"],
        "concept": ["deity", "religioustradition", "concept"],
    }
    for k, classes in kind_mappings.items():
        if req == k or any(c in req for c in classes):
            if any(c in cand for c in classes):
                return True
    return False


class OxigraphMirror:
    """Embedded Oxigraph local KG mirror for fast resolution and URI validation."""

    def __init__(
        self,
        path: Optional[Union[str, Path]] = None,
        store: Optional[ox.Store] = None,
    ) -> None:
        """Initialize store from an existing instance, snapshot file, or directory."""
        if store is not None:
            self.store = store
            self.source_path = path
        elif path is not None:
            self.source_path = Path(path)
            self.store = self._init_from_path(self.source_path)
        else:
            self.source_path = None
            self.store = ox.Store()

    def _init_from_path(self, path: Path) -> ox.Store:
        """Load from a file, an existing on-disk RocksDB directory, or directory of RDF files."""
        if not path.exists():
            raise FileNotFoundError(f"Snapshot path does not exist: {path}")

        if path.is_file():
            store = ox.Store()
            self._load_file_into(store, path)
            return store

        if path.is_dir():
            # Check if this is an on-disk RocksDB directory
            if (path / "CURRENT").exists():
                try:
                    return ox.Store.read_only(str(path))
                except Exception as exc:
                    logger.debug("Failed opening as RocksDB read-only, falling back to file scan: %s", exc)

            # Otherwise scan for RDF files
            store = ox.Store()
            loaded_any = False
            for ext in ("*.nt", "*.ttl", "*.nq", "*.trig"):
                for f in sorted(path.glob(ext)):
                    self._load_file_into(store, f)
                    loaded_any = True
            if not loaded_any:
                logger.warning("No RDF snapshot files found in directory: %s", path)
            return store

        raise ValueError(f"Unsupported path type: {path}")

    @staticmethod
    def _load_file_into(store: ox.Store, file_path: Path) -> None:
        """Load single RDF file into store guessing format by extension."""
        ext = file_path.suffix.lower()
        format_map = {
            ".nt": ox.RdfFormat.N_TRIPLES,
            ".ttl": ox.RdfFormat.TURTLE,
            ".nq": ox.RdfFormat.N_QUADS,
            ".trig": ox.RdfFormat.TRIG,
        }
        fmt = format_map.get(ext)
        if fmt is not None:
            store.load(path=str(file_path), format=fmt)
        else:
            store.load(path=str(file_path))

    def load_file(self, file_path: Union[str, Path]) -> None:
        """Load an additional RDF snapshot file into the active store."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        self._load_file_into(self.store, p)

    def load_text(self, content: str, format_name: str = "nt") -> None:
        """Load RDF content string into store."""
        format_map = {
            "nt": ox.RdfFormat.N_TRIPLES,
            "ttl": ox.RdfFormat.TURTLE,
            "turtle": ox.RdfFormat.TURTLE,
            "nq": ox.RdfFormat.N_QUADS,
            "trig": ox.RdfFormat.TRIG,
        }
        fmt = format_map.get(format_name.lower(), ox.RdfFormat.N_TRIPLES)
        self.store.load(input=content.encode("utf-8"), format=fmt)

    @staticmethod
    def expand_uri(uri: str) -> str:
        """Expand heritageGraph: prefix into canonical base URI."""
        if not uri or not isinstance(uri, str):
            return uri
        if uri.startswith(HG_PREFIX):
            return HG_BASE_URI + uri[len(HG_PREFIX):]
        return uri

    @staticmethod
    def compact_uri(uri: str) -> str:
        """Compact canonical base URI to heritageGraph: prefix."""
        if not uri or not isinstance(uri, str):
            return uri
        if uri.startswith(HG_BASE_URI):
            return HG_PREFIX + uri[len(HG_BASE_URI):]
        return uri

    def check_exact_uri(self, uri: str) -> bool:
        """Check if URI exists as subject or object in the mirror store.

        Supports both prefixed and full IRI forms.
        """
        if not uri or not isinstance(uri, str):
            return False

        candidates_to_check = [uri]
        if uri.startswith(HG_PREFIX):
            candidates_to_check.append(HG_BASE_URI + uri[len(HG_PREFIX):])
        elif uri.startswith(HG_BASE_URI):
            candidates_to_check.append(HG_PREFIX + uri[len(HG_BASE_URI):])

        for u in candidates_to_check:
            try:
                node = ox.NamedNode(u)
                for _ in self.store.quads_for_pattern(node, None, None):
                    return True
                for _ in self.store.quads_for_pattern(None, None, node):
                    return True
            except Exception:
                continue
        return False

    def get_canonical_uri(self, uri: str) -> str:
        """Return the exact URI form present in the store (expanding or compacting if needed)."""
        if not uri or not isinstance(uri, str):
            return uri

        # Prefer expanded form first, then original, then compact
        expanded = self.expand_uri(uri)
        compact = self.compact_uri(uri)
        checks = [expanded, uri, compact]

        for u in checks:
            try:
                node = ox.NamedNode(u)
                if list(self.store.quads_for_pattern(node, None, None)) or list(self.store.quads_for_pattern(None, None, node)):
                    return u
            except Exception:
                continue
        return expanded

    def find_candidate_entities(
        self,
        label: str,
        entity_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Run SPARQL 1.1 SELECT query on mirror to find candidate entities.

        Matches labels against skos:prefLabel, rdfs:label, schema:name, heritageGraph:name.
        Returns candidate dicts with:
        {uri, label, type, score, source: "kg_mirror", match_type: "exact"|"close"}
        """
        if not label or not label.strip():
            return []

        clean_label = label.strip()
        norm_label = fold(clean_label)

        # Extract search tokens, prioritizing distinctive words over generic stop words
        stop_words = {
            "temple", "mandir", "shrine", "devalaya", "monument", "stupa", "chaitya",
            "pati", "sattal", "dhungedhara", "pokhari", "the", "and", "for", "with",
            "square", "chowk", "complex", "building", "structure"
        }
        raw_words = re.findall(r"[\w]+", clean_label)
        all_words = [fold(w) for w in raw_words if len(w) >= 3]
        distinctive_words = [w for w in all_words if w not in stop_words]
        query_words = distinctive_words if distinctive_words else all_words

        # Escape strings for SPARQL query literal
        escaped_exact = clean_label.lower().replace("\\", "\\\\").replace('"', '\\"')

        filter_clauses = [f'LCASE(STR(?label)) = "{escaped_exact}"']
        for w in query_words[:4]:
            esc_w = w.replace("\\", "\\\\").replace('"', '\\"')
            filter_clauses.append(f'CONTAINS(LCASE(STR(?label)), "{esc_w}")')

        filter_expr = " || ".join(filter_clauses)

        sparql_query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX schema: <http://schema.org/>
        PREFIX schema_https: <https://schema.org/>
        PREFIX heritageGraph: <https://cair-nepal.org/heritagegraph/>
        PREFIX hg: <https://cair-nepal.org/heritagegraph/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

        SELECT DISTINCT ?uri ?label ?type WHERE {{
          ?uri ?p ?label .
          FILTER (?p IN (
            rdfs:label,
            skos:prefLabel,
            skos:altLabel,
            schema:name,
            schema_https:name,
            heritageGraph:name,
            hg:name
          ))
          OPTIONAL {{ ?uri rdf:type ?type }}
          FILTER ({filter_expr})
        }}
        """

        try:
            solutions = list(self.store.query(sparql_query))
        except Exception as exc:
            logger.warning("SPARQL mirror query failed: %s", exc)
            return []

        candidates_by_uri: Dict[str, Dict[str, Any]] = {}

        for sol in solutions:
            uri = sol["uri"].value
            cand_label = sol["label"].value
            cand_type = sol["type"].value if sol["type"] is not None else None

            cand_folded = fold(cand_label)

            # Score computation
            if cand_folded == norm_label:
                score = 1.0
                match_type = "exact"
            elif norm_label in cand_folded or cand_folded in norm_label:
                ratio = SequenceMatcher(None, norm_label, cand_folded).ratio()
                score = round(max(0.85, ratio), 3)
                match_type = "close"
            else:
                ratio = SequenceMatcher(None, norm_label, cand_folded).ratio()
                score = round(ratio, 3)
                match_type = "exact" if ratio >= 0.95 else "close"

            # Entity type compatibility adjustment
            if entity_type:
                if _is_compatible_type(cand_type, entity_type):
                    score = min(1.0, score + 0.05)
                else:
                    score = max(0.0, score - 0.15)

            if score < 0.6:
                continue

            # Deduplicate by URI, keeping highest score
            if uri not in candidates_by_uri or score > candidates_by_uri[uri]["score"]:
                candidates_by_uri[uri] = {
                    "uri": uri,
                    "label": cand_label,
                    "type": cand_type,
                    "score": score,
                    "source": "kg_mirror",
                    "match_type": match_type,
                }

        results = list(candidates_by_uri.values())
        if any(c["match_type"] == "exact" for c in results):
            results = [c for c in results if c["match_type"] == "exact" or c["score"] >= 0.85]
        results.sort(key=lambda c: (c["score"], c["match_type"] == "exact"), reverse=True)
        return results[:limit]


def load_mirror(
    path_or_store: Optional[Union[str, Path, OxigraphMirror, ox.Store]] = None,
) -> OxigraphMirror:
    """Convenience helper to obtain an OxigraphMirror instance."""
    if isinstance(path_or_store, OxigraphMirror):
        return path_or_store
    if isinstance(path_or_store, ox.Store):
        return OxigraphMirror(store=path_or_store)
    return OxigraphMirror(path=path_or_store)
