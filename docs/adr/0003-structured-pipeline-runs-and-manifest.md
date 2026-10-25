# ADR-0003: Structured Pipeline Runs, Stage-Prefixed Artifacts, and Provenance Manifest

## Status
Accepted

## Context
Previously, skills (`01_heritage-extract`, `02_heritage-entity-resolution`, `03_heritage-rdf-mapper`, `04_heritage-shacl-validate`) wrote raw outputs (`preprocessed.json`, `extracted.json`, `resolved.json`, `graph.ttl`, `graph.validation.json`) directly into the repository root or current working directory.

This caused:
1. **Root Pollution & Collisions**: Ingesting multiple source documents (e.g., PDF surveys, DANAM CSV dumps) overwrote intermediate artifacts.
2. **Missing Provenance**: No machine-readable metadata linked the final RDF graph back to the exact source file hash, LinkML container schema version, or tool run metrics.
3. **Ambiguous Stage Ordering**: Downstream tools could not cleanly determine whether an artifact was preliminary or fully resolved.

## Decision
1. **Isolated Run Directory (`runs/<run_id>/`)**:
   - Every transformation execution operates in its own directory under `runs/<run_id>/` (e.g., `runs/2026-10-25_idjmss-patan/`).
   - When no `--run-dir` is passed, scripts automatically generate a run directory based on the ISO date and source file slug.

2. **Standardized Stage-Prefixed Artifact Names**:
   Within each run directory, artifacts follow an ordered numbering scheme:
   - `00_preprocessed.json`: Raw normalized text chunks & OCR metadata from ingestion.
   - `01_extracted.json`: Schema-validated LinkML Container instance.
   - `02_resolved.json`: Reconciled entities with external (Getty/Wikidata) or locally minted URIs.
   - `03_graph.ttl`: Triplified CIDOC-CRM / PROV-O RDF Turtle graph.
   - `04_shacl_report.json`: SHACL validation results and constraint violation details.

3. **Provenance Manifest (`manifest.json`)**:
   - Each run directory contains a `manifest.json` tracking:
     - Input source path, file size, SHA-256 hash.
     - Schema references: `HeritageGraph.yaml` version, commit SHA, and SHACL shape references.
     - Execution records per stage: timestamp, tool name/command, execution duration, and entity statistics.
     - Validation summary: JSON schema validity and SHACL conformity status.

4. **CLI Argument Standardization**:
   - All pipeline tools support a unified `--run-dir` flag, eliminating implicit writes to the repository root while preserving backwards compatibility through optional overrides.

## Consequences
- **Reproducibility**: Any generated knowledge graph can be traced directly back to its source document, tool versions, and extraction parameters.
- **Multi-Batch Concurrency**: Multiple document transformations can run independently without artifact collisions.
- **Deterministic Pipeline Handoffs**: Orchestrator scripts (`run_pipeline.py`) can validate pre-conditions by inspecting the run directory and its manifest.
