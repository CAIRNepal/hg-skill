# Agent Guidelines: HeritageGraph Skills (`hg-skill`)

Repository containing agent skills for transforming unstructured, archival, and tabular cultural heritage records into validated, ontology-grounded RDF Turtle (`.ttl`) for contribution to the **HeritageGraph** platform by CAIR-Nepal.

## Agent skills

### Issue tracker

GitHub Issues on [CAIRNepal/hg-skill](https://github.com/CAIRNepal/hg-skill) using the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical roles (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repository using `GLOSSARY.md` and `docs/adr/`. See `docs/agents/domain.md`.

## Core Repository Architecture

The transformation pipeline comprises sequential stages orchestrated under `skills/`:

- `skills/00_heritage-to-rdf`: End-to-end pipeline orchestrator from ingestion to validated graph.
- `skills/01_heritage-extract`: Extracts raw inputs into schema-validated `extracted.json`.
- `skills/02_heritage-entity-resolution`: Reconciles entities with Getty vocabularies, Wikidata, and local gazetteers into `resolved.json`.
- `skills/03_heritage-rdf-mapper`: Deterministically triplifies records to `graph.ttl` using CIDOC-CRM mapping.
- `skills/04_heritage-shacl-validate`: Validates graph syntax and structural integrity against `schemas/HeritageGraph.shacl.ttl`.

## Authoritative Schemas & Sources

- **HeritageGraph LinkML YAML**: `schemas/HeritageGraph.yaml` (v1.0.1)
- **HeritageGraph Ontology TTL**: `schemas/HeritageGraph.ttl`
- **HeritageGraph SHACL Shapes**: `schemas/HeritageGraph.shacl.ttl`
- **Ontology Documentation**: [heritagegraphontology](https://cairnepal.github.io/heritagegraphontology/)
- **Upstream URLs & Version Management**: [schemas/SOURCES.md](schemas/SOURCES.md)
  - To fetch an alternate release or branch: `python scripts/update_ontology.py --ref <branch_or_tag>`
