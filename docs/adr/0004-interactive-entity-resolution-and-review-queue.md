# ADR-0004: Interactive Human-in-the-Loop Entity Resolution and Staged Review Queue

## Status
Accepted

## Context
In Stage 2 of the transformation pipeline (`skills/02_heritage-entity-resolution`), extracted heritage entities (`01_extracted.json`) are grounded into authoritative URIs.

However:
1. **Domain Complexity in Cultural Heritage**: In Nepal and Himalayan heritage, automated scrapers and naive string matching frequently struggle with homonyms (e.g., dozens of *Radha Krishna* or *Narayan* temples), diacritic variations, syncretic deity names (*Rato Machhindranath* vs. *Bungadyah*), and local *Guthi* institutions not cataloged in global authorities.
2. **Batch Pipeline Blocking vs. Automation Drift**: Halting terminal execution synchronously in non-interactive batch runs freezes automated CI and agent workflows. Conversely, completely automating with local minting without a review mechanism risks never surfacing ambiguous entities to human experts.
3. **Missing Feedback Loop**: When a human curator manually resolves an entity once, there was no automated mechanism to save that confirmed resolution into the project's gazetteers for future runs.

## Decision
1. **Interactive CLI Mode (`--interactive` / `-i`)**:
   - `skills/02_heritage-entity-resolution/scripts/resolve_entities.py` supports an `--interactive` flag.
   - For unlinked or ambiguous entities, it dynamically queries candidate lookups (Wikidata API, Getty SPARQL, internal gazetteers) and prompts the curator to accept a candidate, mint a local URI, enter a custom URI, or skip.
   - Curator decisions are stamped with `"source": "human-curator"` and `"confidence": 1.0`.

2. **Staged Review Queue (`02_review_queue.json`) for Non-Interactive Runs**:
   - When run non-interactively (without `--interactive`), the tool produces `02_resolved.json` with safe fallback local URIs to ensure pipeline continuity.
   - Simultaneously, all entities flagged as `ambiguous` or falling back to `local` minting are staged in `02_review_queue.json` within the run directory.
   - Manifest tracks `"needs_human_review": true/false` and `"review_queue_count"`.
   - A curator can review the run at any later time by running `resolve_entities.py --run-dir <DIR> --interactive`.

3. **Curated Gazetteer Feedback Loop (`curated-links.csv`)**:
   - In interactive mode, approved human resolutions can be appended directly to `assets/gazetteers/curated-links.csv`.
   - Subsequent runs automatically load `curated-links.csv` alongside default gazetteers, allowing human expertise to compound permanently across all future datasets.

## Consequences
- **Zero Pipeline Stalls**: Non-interactive executions complete cleanly while flagging unresolved items.
- **High Data Quality**: Complex living heritage and ambiguous monuments can be vetted by domain experts before final graph ingestion.
- **Compounding Knowledge**: Human curation actively enriches the project's internal gazetteer asset over time.
