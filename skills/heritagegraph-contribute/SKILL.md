---
name: heritagegraph-contribute
description: "Transform and contribute Nepalese cultural heritage records (PDF, CSV, JSON) into validated HeritageGraph RDF Turtle. Automatically checks environment readiness, mirrors existing graph data via embedded Oxigraph, diffs entities to prevent duplicate minting, and packages PR-ready contribution bundles."
---

# HeritageGraph Contributor Skill (`hg`)

End-to-end transformation of archival documents, field surveys, and catalogs into validated, ontology-aligned RDF graphs for CAIR-Nepal's **HeritageGraph**.

## When to Use

Activate this skill when:
- The user provides cultural heritage files (monument surveys, temple catalogs, Guthi lists, festival calendars, inscriptions).
- The user wants to convert PDFs, CSVs, or JSON records into Linked Data / RDF Turtle.
- The user wants to check environment health (`hg doctor`), sync the latest graph snapshot (`hg sync`), or prepare a contribution pull request (`hg bundle`).

## Quick Workflow

1. **Check Readiness & Sync (Pre-flight)**:
   ```bash
   python -m hg.cli doctor
   python -m hg.cli sync
   ```
   Ensures schemas, SHACL shapes, and the published knowledge graph snapshot are cached locally.

2. **Run Transformation Pipeline (Stages 01–06)**:
   ```bash
   python -m hg.cli run <input_document> --interactive
   ```
   Orchestrates:
   - **01 Extract**: Ingests document, extracts entities with evidence spans (page/line/cell), scans Living Heritage (Guthi, styles, Nepal Sambat eras).
   - **02 Resolve**: Queries local `pyoxigraph` mirror *first* (exact URI check, label/type SPARQL search), then external LOD (Getty/Wikidata/LUX). Reuses existing URIs before minting.
   - **03 Map**: Generates native HeritageGraph RDF (`03_graph.ttl`).
   - **04 Validate**: Enforces non-vacuous SHACL conformance against `HeritageGraph.shacl.ttl`.
   - **05 Diff**: Compares against mirror snapshot, flagging duplicate candidates.
   - **06 Bundle**: Packages named graph N-Quads, PROV-O provenance, evidence spans, and rights metadata into `06_contribution_bundle/`.

3. **Inspect Output & Submit**:
   - Review `05_diff_report.json` for new vs. existing entities.
   - Verify `06_contribution_bundle/` contains complete provenance.
   - Submit bundle via pull request to the CAIR-Nepal contributions repository.

## Reference Guides

- **Setup & S3 Sync**: [setup-and-sync.md](references/setup-and-sync.md) — Anonymous S3 sync layout and offline modes.
- **URI Minting Policy**: [uri-policy.md](references/uri-policy.md) — Transliteration, slug rules, and reuse-before-mint mandates.
- **Contribution Format**: [contribution-format.md](references/contribution-format.md) — Bundle structure, PROV-O traces, and cultural sensitivity tiers.
- **Troubleshooting**: [troubleshooting.md](references/troubleshooting.md) — Diagnostic remediation and SHACL shape failures.
