---
name: heritage-entity-resolution
description: >-
  Reconcile extracted heritage entities against gazetteers, Getty vocabularies, and Wikidata.
  Stage 2 of the heritage-to-rdf pipeline, appending confidence scores and authoritative URIs.
disable-model-invocation: true
---

# Heritage Entity Resolution (Stage 2)

Input: `extracted.json` from stage 1.  
Output: `resolved.json`, preserving all source records with an attached `resolution` object on every `mention`.

**Core Principle**: A wrong link is worse than no link. An incorrect link silently corrupts the knowledge graph with false assertions. When evidence is ambiguous or confidence is below threshold, mint a predictable local URI. Never synthesize or hallucinate external URIs from memory.

## Workflow

1. **Deterministic Gazetteer Matching**:
   Run the local matching script against project gazetteers:
   ```bash
   python scripts/gazetteer_match.py extracted.json assets/gazetteers/ --out matches.json
   ```
   Inspect `matches.json`. Treat `exact` and `context_match` as strong candidates; treat `ambiguous` or `none` as unresolved.
2. **Query Public Vocabularies**:
   For mentions with `status: "none"` or `ambiguous`, query authoritative endpoints following the **Source Priority Matrix**:
   - Getty (AAT / ULAN / TGN): `python scripts/lookup_getty.py "<label>" --vocab <aat|ulan|tgn>`
   - Wikidata: `python scripts/lookup_wikidata.py "<label>"`
   *(For endpoint rules, SPARQL quirks, and transliteration handling, consult [references/vocabularies.md](references/vocabularies.md))*.
   If network access is blocked, notify the user rather than guessing URIs.
3. **Disambiguate & Score**:
   Compare context, object production dates, place names, and roles:
   - **High Confidence ($\ge 0.85$)**: Direct name match with strong contextual agreement $\rightarrow$ `status: "linked"`.
   - **Partial / Conflicted Evidence**: $\rightarrow$ `status: "ambiguous"` (surface to user).
   - **No Credible Candidate**: $\rightarrow$ `status: "local"`.
4. **Mint Local URIs**:
   For `status: "local"` or unresolved entities, construct deterministic local URIs:
   `<base_uri>/<kind>/<slugified-label>` (default base: `https://cair-nepal.org/heritagegraph/`).
   The same `label` and `kind` must always produce the identical URI.
5. **Output & Validate**:
   Write `resolved.json`.
   **Completion Gate**: Verify that every `mention` in `resolved.json` has a `resolution` block with required fields (`uri`, `source`, `confidence`, `status`, `rationale`).
6. **Report**: Summarize resolution metrics following the **Reporting Format**.

## Reference: Resolution Schema

Each mention in `resolved.json` is augmented with a `resolution` block:

```json
{
  "label": "Rembrandt van Rijn",
  "kind": "person",
  "context": "Dutch painter, 17th c.",
  "resolution": {
    "uri": "http://vocab.getty.edu/ulan/500011051",
    "source": "getty-ulan",
    "confidence": 0.95,
    "status": "linked",
    "rationale": "Name and 'Dutch painter, 17th c.' match; production date fits life dates."
  }
}
```

* `status`: `linked` (external URI found), `local` (deterministic local URI minted), or `ambiguous` (multiple plausible candidates requiring human review).
* `rationale`: One concise sentence explaining the match or why it fell back to local.

## Source Priority Matrix

| `kind` | Lookup Sequence |
|---|---|
| `person`, `group` | Internal gazetteer $\rightarrow$ Getty ULAN $\rightarrow$ Wikidata |
| `place` | Internal gazetteer $\rightarrow$ Wikidata $\rightarrow$ Getty TGN |
| `material`, `technique`, `concept` | Getty AAT $\rightarrow$ Wikidata |
| `other` | Internal gazetteer $\rightarrow$ Wikidata |

## Reporting Format

Conclude the run with:
1. Total mentions processed.
2. Resolution breakdown: `linked` count, `local` count, `ambiguous` count.
3. Formatted list of all `ambiguous` entities with their candidate URIs for human review.
