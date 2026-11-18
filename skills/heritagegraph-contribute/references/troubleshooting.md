# HeritageGraph Troubleshooting Guide

Common issues encountered when running `hg` and how to remediate them.

## 1. Missing Dependencies or Environment Warnings

**Symptoms**:
- `hg doctor` reports `MISSING` packages or Python version errors.

**Fix**:
Ensure Python 3.10+ is active, then install the core dependencies:
```bash
pip install pyoxigraph rdflib pyshacl requests linkml
```

## 2. Stage 05 Diff Gate Failure (Suspected Duplicates Detected)

**Symptoms**:
- `hg run` or `hg diff` fails with exit code 1:
  `GATE FAILED: N suspected duplicate(s) require human review before contribution.`

**Cause**:
The extraction process minted a new URI for an entity (e.g. `heritageGraph:struct-nyatapola-new`), but the local KG mirror found an existing entity with an identical or near-identical label (`Nyatapola Temple`).

**Fix**:
Re-run Stage 2 interactively to review and confirm entity links:
```bash
python -m hg.cli run <input_document> --interactive
```
The terminal prompt will allow you to link the extracted mention to the existing canonical URI, avoiding duplicate minting.

## 3. SHACL Shape Conformance Violations (Stage 04)

**Symptoms**:
- SHACL report outputs `violations` or `vacuous: true`.

**Fix**:
- **Vacuous Pass**: Check that entities are properly typed with `heritageGraph:` classes (e.g., `heritageGraph:ArchitecturalStructure`) rather than generic URIs.
- **Missing Required Properties**: Inspect `04_shacl_report.json` to find missing mandatory slots (such as `heritageGraph:name` or `rdfs:label`).

## 4. Offline Snapshot Unavailable

**Symptoms**:
- `hg sync --offline` fails with `OfflineCacheMissError`.

**Fix**:
You must perform an initial online sync to populate the local cache:
```bash
python -m hg.cli sync
```
Once completed, snapshots and schemas will be available in `~/.cache/heritagegraph/` for offline use.
