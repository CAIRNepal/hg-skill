#!/usr/bin/env python3
"""Living heritage & controlled terminology scanner for Stage 1 extraction.

Extracts candidate mentions for:
- Guthi functional types (GuthiType LinkML enum)
- Architectural styles (ArchitecturalStyle LinkML enum)
- Indigenous calendar systems (NS, VS, ŚS) and Common Era years, with ISO bounds
- Historical eras (Licchavi, Malla, Shah)
- Religious traditions

Guthi types and architectural styles are loaded from schemas/HeritageGraph.yaml
(override the location with the HG_SCHEMA environment variable), so new enum values
added upstream are picked up without code changes. The YAML defines no calendar, era
or tradition enums, so those vocabularies are local to this file.

Every candidate shares one base shape: category, matched_text, span, context,
target_collection, plus category-specific keys (enum_value, calendar_system,
numeric_year, iso_bounds, tradition, era).

Emits structured hints for the in-IDE extraction agent to populate LinkML Container instances.
"""
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Tuple

import yaml

DEFAULT_SCHEMA = Path(__file__).resolve().parents[3] / "schemas" / "HeritageGraph.yaml"

# Additive spelling variants per enum value. Values absent from this table fall back to the
# term derived from the enum name itself, so new schema values still work.
GUTHI_PREFIX_ALIASES = {
    "SiGuthi": ["see", "sii"],
    "RajGuthi": ["raja"],
    "PujaGuthi": ["pooja"],
    "TempleGuthi": ["mandir", "devalaya"],
    "NashaGuthi": ["nasa"],
    "SanaGuthi": ["sanah"],
}

STYLE_ALIASES = {
    "Pagoda": [r"multi[- ]tiered", r"tiered[- ]roof(?:ed)?", r"dega", r"degah"],
    "Shikhara": [r"sikhara", r"spire[- ]shaped"],
    "Chaitya": [r"chibha", r"chiba"],
    "Stupa": [r"reliquary mound", r"mahachaitya"],
    "Dome": [r"domed", r"gumbaz", r"neo[- ]classical"],
}

# Styles whose presence in a sentence suppresses a "Dome" tag: stupas and chaityas are
# domed by definition, so tagging both would be a false positive.
DOME_SUPPRESSORS = ("Stupa", "Chaitya")

ENV_SCHEMA = "HG_SCHEMA"

NAME_STOPWORDS = {"The", "A", "An", "This", "That"}
GENERIC_GUTHI = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+[Gg]uthi\b")
NAME_BEFORE = re.compile(r"((?:[A-Z][a-z]+\s+){1,2})$")

# Abbreviations (NS, VS, CE...) are case-sensitive to avoid matching ordinary words;
# spelled-out names are case-insensitive via scoped (?i:...) groups.
CALENDAR_PATTERNS: List[Tuple[str, Pattern]] = [
    ("NepalSambat", re.compile(
        r"(?:\b(?:NS|N\.S\.)|(?i:\bnepal(?:a)?\s+sam[bv]at))\s*[:.]?\s*(\d{1,4})\b")),
    ("BikramSambat", re.compile(
        r"(?:\b(?:VS|V\.S\.|BS|B\.S\.)|(?i:\b(?:bikram|vikram|vikrama)\s+sam[bv]at))\s*[:.]?\s*(\d{1,4})\b")),
    ("ShakaSambat", re.compile(
        r"(?:\b(?:ŚS|Ś\.S\.)|(?i:\b[sś]h?aka(?:\s+sam[bv]at)?\b))\s*[:.]?\s*(\d{1,4})\b")),
    ("CommonEra", re.compile(r"\b(\d{3,4})\s*(?:CE|AD|C\.E\.|A\.D\.)(?!\w)")),
    ("BeforeCommonEra", re.compile(r"\b(\d{1,4})\s*(?:BCE|BC|B\.C\.E\.|B\.C\.)(?!\w)")),
]
SAMBAT_SYSTEMS = {"NepalSambat", "BikramSambat", "ShakaSambat"}
# A Sambat year is paired with a Common Era year only when the text itself states both,
# e.g. "NS 822 (1702 CE)". The gap between them may hold only these characters.
PAIR_GAP = re.compile(r"^[\s(=,/]{0,6}$")

ERA_PATTERNS: List[Tuple[str, Pattern]] = [
    ("Licchavi", re.compile(r"\b(?:Licchavi|Lichhavi|Lichchhavi)\b")),
    ("Malla", re.compile(r"\bMalla\b")),
    ("Shah", re.compile(r"\bShah\b")),
]

TRADITION_PATTERNS: List[Tuple[str, Pattern]] = [
    ("Buddhist", re.compile(r"\b(?:buddhist|buddhism|vajrayana|mahayana|theravada|vihara|baha|bahi)\b", re.I)),
    ("Shaiva", re.compile(r"\b(?:shaiva|saiva|shiva|shaivism|pashupata|nath|linga)\b", re.I)),
    ("Vaishnava", re.compile(r"\b(?:vaishnava|vaisnava|vishnu|vaishnavism|narayan|krishna|rama)\b", re.I)),
    ("Shakta", re.compile(r"\b(?:shakta|sakta|devi|durga|kali|bhagavati|bhavani|tantric|matrika)\b", re.I)),
    ("Syncretic", re.compile(r"\b(?:syncretic|hindu[- ]buddhist|buddhist[- ]hindu)\b", re.I)),
]


def load_schema_enums(schema_path: Optional[Path] = None) -> Dict[str, Dict[str, str]]:
    """Return {enum_name: {value: description}} from the LinkML schema."""
    path = Path(schema_path or os.environ.get(ENV_SCHEMA) or DEFAULT_SCHEMA)
    if not path.exists():
        raise FileNotFoundError(
            f"HeritageGraph schema not found at {path}. Run scripts/update_ontology.py "
            f"or set {ENV_SCHEMA}.")
    enums = yaml.safe_load(path.read_text(encoding="utf-8")).get("enums", {})
    return {
        name: {v: (meta or {}).get("description", "") for v, meta in (spec.get("permissible_values") or {}).items()}
        for name, spec in enums.items()
    }


def _split_camel(value: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)


def build_guthi_patterns(values: Dict[str, str]) -> List[Tuple[str, Pattern, str]]:
    patterns = []
    for value, desc in values.items():
        prefix = _split_camel(value).lower().removesuffix(" guthi").replace(" ", r"\s*")
        alts = [prefix] + GUTHI_PREFIX_ALIASES.get(value, [])
        patterns.append((value, re.compile(rf"\b(?:{'|'.join(alts)})\s*guthi\b", re.I), desc))
    return patterns


def build_style_patterns(values: Dict[str, str]) -> List[Tuple[str, Pattern, str]]:
    patterns = []
    for value, desc in values.items():
        alts = [re.escape(value.lower())] + STYLE_ALIASES.get(value, [])
        patterns.append((value, re.compile(rf"\b(?:{'|'.join(alts)})\b", re.I), desc))
    return patterns


_ENUMS = load_schema_enums()
GUTHI_PATTERNS = build_guthi_patterns(_ENUMS.get("GuthiType", {}))
ARCHITECTURAL_STYLE_PATTERNS = build_style_patterns(_ENUMS.get("ArchitecturalStyle", {}))


def _context(text: str, start: int, end: int, window: int) -> str:
    return text[max(0, start - window):min(len(text), end + window)].strip()


def _candidate(text: str, category: str, match: re.Match, window: int, target: Optional[str] = None,
               span: Optional[Tuple[int, int]] = None, **extra: Any) -> Dict[str, Any]:
    start, end = span or match.span()
    return {
        "category": category,
        "matched_text": text[start:end].strip(),
        "target_collection": target,
        "span": [start, end],
        "context": _context(text, start, end, window),
        **extra,
    }


def _overlaps(span: Tuple[int, int], covered: List[Tuple[int, int]]) -> bool:
    return any(max(s, span[0]) < min(e, span[1]) for s, e in covered)


def _sentence_bounds(text: str, pos: int) -> Tuple[int, int]:
    starts = [m.end() for m in re.finditer(r"[.!?\n]", text[:pos])]
    ends = [pos + m.start() for m in re.finditer(r"[.!?\n]", text[pos:])]
    return (starts[-1] if starts else 0, ends[0] if ends else len(text))


def _strip_stopword(name: str) -> Tuple[str, int]:
    """Drop a leading article from a capitalized name; return (name, characters removed)."""
    first, _, rest = name.partition(" ")
    if first in NAME_STOPWORDS and rest:
        return rest.lstrip(), len(name) - len(rest.lstrip())
    return name, 0


def tag_guthi_mentions(text: str) -> List[Dict[str, Any]]:
    """Detect Guthi mentions and map them to LinkML GuthiType enums.

    Specific types win over the generic fallback. The generic fallback needs a capitalized
    name ("Siddhi Lakshmi Guthi") and carries enum_value None, since "Guthi" is a class,
    not a GuthiType value.
    """
    results: List[Dict[str, Any]] = []
    covered: List[Tuple[int, int]] = []

    for enum_val, pattern, desc in GUTHI_PATTERNS:
        for m in pattern.finditer(text):
            if _overlaps(m.span(), covered):
                continue
            covered.append(m.span())
            hint = NAME_BEFORE.search(text[:m.start()])
            name_hint = _strip_stopword(hint.group(1).strip())[0] if hint else None
            results.append(_candidate(text, "guthi", m, 40, "guthis", enum_value=enum_val,
                                      description=desc, name_hint=name_hint or None))

    for m in GENERIC_GUTHI.finditer(text):
        name, removed = _strip_stopword(m.group(1))
        span = (m.start(1) + removed, m.end())
        if not name or _overlaps(span, covered):
            continue
        covered.append(span)
        results.append(_candidate(text, "guthi", m, 40, "guthis", span=span, enum_value=None,
                                  description="Guthi trust of unspecified type", name_hint=name))
    return sorted(results, key=lambda r: r["span"][0])


def tag_architectural_styles(text: str) -> List[Dict[str, Any]]:
    """Detect every architectural style mention and map it to a LinkML ArchitecturalStyle enum."""
    hits = [(enum_val, m, desc) for enum_val, pattern, desc in ARCHITECTURAL_STYLE_PATTERNS
            for m in pattern.finditer(text)]
    suppress_spans = [_sentence_bounds(text, m.start()) for v, m, _ in hits if v in DOME_SUPPRESSORS]

    results = []
    for enum_val, m, desc in hits:
        if enum_val == "Dome" and any(s <= m.start() < e for s, e in suppress_spans):
            continue
        results.append(_candidate(text, "architectural_style", m, 30, "structures",
                                  enum_value=enum_val, description=desc))
    return sorted(results, key=lambda r: r["span"][0])


def _iso(year: int, system: str) -> str:
    return f"-{year:04d}" if system == "BeforeCommonEra" else f"{year:04d}"


def tag_calendar_dates(text: str) -> List[Dict[str, Any]]:
    """Detect NS, VS, ŚS and Common Era years.

    iso_bounds is filled for CE/BCE years, and for a Sambat year only when the text itself
    states the Common Era equivalent next to it. No conversion is ever computed.
    """
    results = []
    for system, pattern in CALENDAR_PATTERNS:
        for m in pattern.finditer(text):
            year = int(m.group(1))
            bounds = None
            if system not in SAMBAT_SYSTEMS:
                bounds = {"earliest": _iso(year, system), "latest": _iso(year, system)}
            results.append(_candidate(text, "date", m, 30, "time_spans", calendar_system=system,
                                      numeric_year=year, iso_bounds=bounds))
    results.sort(key=lambda r: r["span"][0])

    for i, rec in enumerate(results):
        if rec["calendar_system"] in SAMBAT_SYSTEMS:
            nxt = results[i + 1] if i + 1 < len(results) else None
            gap = text[rec["span"][1]:nxt["span"][0]] if nxt else ""
            if nxt and nxt["calendar_system"] == "CommonEra" and PAIR_GAP.match(gap):
                rec["iso_bounds"] = dict(nxt["iso_bounds"])
                rec["paired_common_era"] = nxt["numeric_year"]
    return results


def tag_eras(text: str) -> List[Dict[str, Any]]:
    """Detect historical era / dynasty names. Malla also appears inside royal names, so treat as a hint."""
    return [_candidate(text, "era", m, 30, "time_spans", era=name)
            for name, pattern in ERA_PATTERNS for m in pattern.finditer(text)]


def tag_religious_traditions(text: str) -> List[Dict[str, Any]]:
    """Detect religious and ritual tradition mentions (first mention per tradition)."""
    results = []
    for tradition, pattern in TRADITION_PATTERNS:
        m = pattern.search(text)
        if m:
            results.append(_candidate(text, "tradition", m, 30, None, tradition=tradition))
    return results


def scan_text_for_heritage_entities(text: str) -> Dict[str, Any]:
    """Perform full vocabulary scanning across text and return candidate entity tags."""
    return {
        "guthis": tag_guthi_mentions(text),
        "architectural_styles": tag_architectural_styles(text),
        "dates": tag_calendar_dates(text),
        "eras": tag_eras(text),
        "traditions": tag_religious_traditions(text),
    }
