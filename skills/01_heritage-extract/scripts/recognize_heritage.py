#!/usr/bin/env python3
"""Living heritage & controlled terminology scanner for Stage 1 extraction.

Extracts candidate mentions for:
- Guthi functional types (GuthiType LinkML enum)
- Architectural styles (ArchitecturalStyle LinkML enum)
- Indigenous calendar systems and eras (NS, VS, ŚS)
- Religious traditions

Emits structured hints for the in-IDE extraction agent to populate LinkML Container instances.
"""
import re
from typing import Any, Dict, List

GUTHI_PATTERNS = [
    (r"\b(?:si|see|sii)\s*guthi\b", "SiGuthi", "Funeral and death-care trust"),
    (r"\b(?:raj|raja)\s*guthi\b", "RajGuthi", "Royal and state endowment trust"),
    (r"\b(?:jatra)\s*guthi\b", "JatraGuthi", "Festival organization trust"),
    (r"\b(?:puja|pooja)\s*guthi\b", "PujaGuthi", "Daily worship and offering trust"),
    (r"\b(?:temple|mandir|devalaya)\s*guthi\b", "TempleGuthi", "Temple maintenance and administration trust"),
    (r"\b(?:nasha|nasa)\s*guthi\b", "NashaGuthi", "Sacred music, hymn, and dance trust"),
    (r"\b(?:sana|sanah)\s*guthi\b", "SanaGuthi", "Social and mutual aid cooperative trust"),
    (r"\b(?:san)\s*guthi\b", "SanGuthi", "Life-cycle ritual trust"),
    (r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+guthi\b", "Guthi", "General Guthi trust")
]

ARCHITECTURAL_STYLE_PATTERNS = [
    (r"\b(?:pagoda|multi[- ]tiered|tiered[- ]roof(?:ed)?|dega|degah)\b", "Pagoda", "Multi-tiered indigenous Nepalese pagoda style"),
    (r"\b(?:shikhara|sikhara|spire[- ]shaped)\b", "Shikhara", "North Indian curvilinear spire tower style"),
    (r"\b(?:chaitya|chibha|chiba)\b", "Chaitya", "Buddhist votive shrine style"),
    (r"\b(?:stupa|reliquary mound|mahachaitya)\b", "Stupa", "Buddhist hemispherical reliquary dome style"),
    (r"\b(?:dome|domed|gumbaz|neo[- ]classical)\b", "Dome", "Dome or Mughal/Neo-classical influenced style")
]

CALENDAR_PATTERNS = [
    (r"\b(?:NS|N\.S\.|Nepal\s+Sambat|Nepala\s+Samvat)\s*[:.]?\s*(\d{1,4})\b", "NepalSambat"),
    (r"\b(?:VS|V\.S\.|BS|B\.S\.|Bikram\s+Sambat|Vikrama\s+Samvat)\s*[:.]?\s*(\d{1,4})\b", "BikramSambat"),
    (r"\b(?:ŚS|SS|Saka\s+Sambat|Shaka\s+Samvat)\s*[:.]?\s*(\d{1,4})\b", "ShakaSambat"),
    (r"\b(\d{3,4})\s*(?:CE|AD)\b", "CommonEra"),
    (r"\b(\d{1,4})\s*(?:BCE|BC)\b", "BeforeCommonEra")
]

TRADITION_PATTERNS = [
    (r"\b(?:buddhist|buddhism|vajrayana|mahayana|theravada|vihara|baha|bahi)\b", "Buddhist"),
    (r"\b(?:shaiva|saiva|shiva|shaivism|pashupata|nath|linga)\b", "Shaiva"),
    (r"\b(?:vaishnava|vaisnava|vishnu|vaishnavism|narayan|krishna|rama)\b", "Vaishnava"),
    (r"\b(?:shakta|sakta|devi|durga|kali|bhagavati|bhavani|tantric|matrika)\b", "Shakta"),
    (r"\b(?:syncretic|hindu[- ]buddhist|buddhist[- ]hindu)\b", "Syncretic")
]


def tag_guthi_mentions(text: str) -> List[Dict[str, Any]]:
    """Detect Guthi mentions and map to LinkML GuthiType enums."""
    results = []
    covered_spans = []

    for pattern, enum_val, desc in GUTHI_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            start, end = m.span()
            # If this span overlaps with an already matched specific guthi, skip
            if any(max(s, start) < min(e, end) for s, e in covered_spans):
                continue
            covered_spans.append((start, end))
            matched_text = m.group(0).strip()
            context = text[max(0, start - 40):min(len(text), end + 40)].strip()
            results.append({
                "matched_text": matched_text,
                "enum_value": enum_val,
                "target_collection": "guthis",
                "description": desc,
                "span": [start, end],
                "context": context
            })
    return results


def tag_architectural_styles(text: str) -> List[Dict[str, Any]]:
    """Detect architectural style descriptions and map to LinkML ArchitecturalStyle enums."""
    results = []
    seen = set()

    for pattern, enum_val, desc in ARCHITECTURAL_STYLE_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            matched_text = m.group(0).strip()
            if enum_val not in seen:
                seen.add(enum_val)
                start, end = m.span()
                context = text[max(0, start - 30):min(len(text), end + 30)].strip()
                results.append({
                    "matched_text": matched_text,
                    "enum_value": enum_val,
                    "description": desc,
                    "span": [start, end],
                    "context": context
                })
    return results


def tag_calendar_dates(text: str) -> List[Dict[str, Any]]:
    """Detect indigenous calendar systems (NS, VS, ŚS) and year numbers."""
    results = []

    for pattern, cal_sys in CALENDAR_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            year_str = m.group(1)
            start, end = m.span()
            results.append({
                "matched_text": m.group(0).strip(),
                "calendar_system": cal_sys,
                "numeric_year": int(year_str),
                "span": [start, end],
                "context": text[max(0, start - 30):min(len(text), end + 30)].strip()
            })
    return sorted(results, key=lambda x: x["span"][0])


def tag_religious_traditions(text: str) -> List[Dict[str, Any]]:
    """Detect religious and ritual tradition mentions."""
    results = []
    seen = set()

    for pattern, tradition in TRADITION_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            if tradition not in seen:
                seen.add(tradition)
                results.append({
                    "matched_text": m.group(0).strip(),
                    "tradition": tradition,
                    "span": list(m.span())
                })
    return results


def scan_text_for_heritage_entities(text: str) -> Dict[str, Any]:
    """Perform full vocabulary scanning across text and return candidate entity tags."""
    return {
        "guthis": tag_guthi_mentions(text),
        "architectural_styles": tag_architectural_styles(text),
        "dates": tag_calendar_dates(text),
        "traditions": tag_religious_traditions(text)
    }
