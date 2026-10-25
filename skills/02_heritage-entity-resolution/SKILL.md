---
name: heritage-entity-resolution
description: >-
  Reconcile extracted heritage entities against gazetteers, Getty vocabularies, and Wikidata.
  Stage 2 of the heritage-to-rdf pipeline, appending confidence scores and authoritative URIs.
disable-model-invocation: true
---

# Heritage Entity Resolution (Stage 2)

Input: `01_extracted.json` from stage 1 (or run workspace).  
Output: `02_resolved.json`, preserving all source records with an attached `resolution` object on every entity, along with `02_review_queue.json` containing candidates for unlinked or ambiguous entities.

**Core Principle**: A wrong link is worse than no link. An incorrect link silently corrupts the knowledge graph with false assertions. When evidence is ambiguous or confidence is below threshold, mint a predictable local URI and stage the entity into the Review Queue. Never synthesize or hallucinate external URIs from memory.

## Execution Modes

Stage 2 supports two execution flows:

1. **Automated / Batch Mode (Non-interactive - Default)**:
   ```bash
   python skills/02_heritage-entity-resolution/scripts/resolve_entities.py --run-dir runs/<run_id>
   ```
   - Matches against local gazetteers (`assets/gazetteers/` + `assets/gazetteers/curated-links.csv`).
   - For unresolved entities, mints predictable local URIs (`https://cair-nepal.org/heritagegraph/<kind>/<slug>`) so downstream triplification and SHACL validation are never blocked.
   - Aggregates external candidate matches (Wikidata, Getty, local gazetteers) and stages them into `02_review_queue.json`.
   - Records `needs_human_review: true` in `manifest.json`.

2. **Interactive Review Mode (Human-in-the-Loop)**:
   ```bash
   # Standalone Stage 2 review
   python skills/02_heritage-entity-resolution/scripts/resolve_entities.py --run-dir runs/<run_id> --interactive

   # Or end-to-end pipeline with interactive Stage 2 review
   python skills/00_heritage-to-rdf/scripts/run_pipeline.py --run-dir runs/<run_id> --interactive
   ```
   - Prompts the curator for each item in the review queue with numbered candidates, default local URI, custom URI input, or skip.
   - Updates `02_resolved.json` with curator decisions (`source: "human-curator"`, `confidence: 1.0`).
   - **Compounding Curated Gazetteer**: Asks the curator if confirmed links should be saved to `assets/gazetteers/curated-links.csv`. Once saved, future pipeline runs automatically resolve identical entities deterministically!
   - Updates `manifest.json` with curator decision counts and clears `needs_human_review` if queue is resolved.

## Workflow

1. **Deterministic Gazetteer Matching**:
   Runs against local project gazetteers:
   - `assets/gazetteers/monuments.csv`
   - `assets/gazetteers/places.csv`
   - `assets/gazetteers/curated-links.csv` (human curator decisions)
2. **Candidate Aggregation**:
   For mentions without an exact local match, queries candidate endpoints:
   - Getty (AAT / ULAN / TGN) via `scripts/lookup_getty.py`
   - Wikidata via `scripts/lookup_wikidata.py`
   - Use `--no-network` in offline or test environments to prevent outbound network calls.
3. **Interactive Curation or Review Queue Staging**:
   - If `--interactive` is enabled, opens the terminal review session.
   - Otherwise, serializes candidate rankings into `02_review_queue.json` for later inspection or review.
4. **Deterministic Local Minting**:
   Any unlinked entity receives a predictable local URI:
   `<base_uri>/<kind>/<slugified-label>` (default base: `https://cair-nepal.org/heritagegraph/`).
5. **Output & Provenance**:
   Writes `02_resolved.json`, `02_review_queue.json`, and stamps stage metrics in `manifest.json`.

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
