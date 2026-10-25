---
name: heritage-extract
description: >-
  Extract structured records from raw cultural-heritage material into schema-validated JSON.
  Stage 1 of the heritage-to-rdf pipeline, capturing objects, structures, living heritage, and provenance.
disable-model-invocation: true
---

# Heritage Extraction (Stage 1)

Transform unstructured text, field notes, inscriptions, or tabular heritage records into `extracted.json` conforming to `assets/extraction.schema.json` (compiled natively from `schemas/HeritageGraph.yaml`).

Accuracy takes absolute precedence over completeness: downstream stages mint URIs and triples directly from this output, so unverified inferences permanently corrupt the knowledge graph.

## Workflow

1. **Ingest & Preprocess**: Run the ingestion CLI to parse raw inputs (.pdf, .csv, .tsv, .xlsx, .json), clean OCR noise, and discover living heritage candidate tags:
   ```bash
   python skills/01_heritage-extract/scripts/ingest_raw.py raw_input.pdf --out preprocessed.json
   ```
2. **Extract Entities**: Guided by `preprocessed.json` and its candidate tags, structure records into typed collections within the LinkML `Container` following the **Extraction Rules** below. Output to `extracted.json`.
3. **Validate**: Run the quality gate script.
   ```bash
   python skills/01_heritage-extract/scripts/validate_extraction.py extracted.json
   ```
   **Completion Gate**: Must exit with code `0` (`OK: N entity/record(s) valid`). Remediate all schema and referential errors in `extracted.json`; never loosen the schema.
4. **Report**: Summarize results using the **Reporting Format**.

## Extraction Rules

- **Container Structure**: Output a single JSON object representing the LinkML `Container` with an `id` (e.g., `heritageGraph:batch-<name>`) and typed entity arrays (`structures`, `human_made_objects`, `iconographic_objects`, `places`, `persons`, `actors`, `guthis`, `festivals`, `ritual_events`, `production_events`, `assertions`).
- **Entity Identification**: Every entity must have a unique CURIE `id` with prefix `heritageGraph:` (e.g., `heritageGraph:struct-nyatapola`, `heritageGraph:place-bhaktapur`).
- **Living Heritage Modeling**: Explicitly capture living cultural heritage:
  - **Guthis**: Extract social/religious trusts into `guthis` with `guthi_type` (`SiGuthi`, `JatraGuthi`, `PujaGuthi`, `TempleGuthi`, `NashaGuthi`, `SanaGuthi`, `SanGuthi`, `RajGuthi`).
  - **Festivals & Rituals**: Extract Jatras and rites into `festivals` or `ritual_events` and link structures via `participates_in_ritual`.
  - **Architectural Style**: Assign controlled values to `has_architectural_style` (`Pagoda`, `Shikhara`, `Dome`, `Chaitya`, `Stupa`).
- **Verbatim Fidelity**: Copy names and labels exactly as written. Disambiguating text (century, role, caste, context) goes into `note` or `description`. Never normalize or translate indigenous terms.
- **Dual Date Representation**:
  - `text` / `note`: Date string as written (e.g., `"c. 1702 CE"`, `"NS 822"`).
  - Conservative ISO bounds (`YYYY`, `YYYY-MM`, `YYYY-MM-DD`, negative for BCE). Populate only when verifiable from the source text.
- **Referential Integrity**: Cross-references (e.g. `has_current_location`, `managed_by_guthi`, `was_produced_by_event`) must resolve to declared entity IDs within the container or canonical URIs.
- **Edge Cases**: For OCR noise, complex attribution language, lots, or conflicting records, consult [references/edge-cases.md](references/edge-cases.md).

## Output Template

```json
{
  "id": "heritageGraph:batch-bhaktapur-001",
  "structures": [
    {
      "id": "heritageGraph:struct-nyatapola",
      "name": "Nyatapola Temple",
      "note": "A five-tiered pagoda temple dedicated to Siddhi Lakshmi in Taumadhi Square, built by King Bhupatindra Malla.",
      "has_architectural_style": "Pagoda",
      "has_current_location": "heritageGraph:place-taumadhi",
      "managed_by_guthi": ["heritageGraph:guthi-siddhi-lakshmi"],
      "participates_in_ritual": ["heritageGraph:ritual-bisket-jatra"]
    }
  ],
  "places": [
    {
      "id": "heritageGraph:place-taumadhi",
      "name": "Taumadhi Square, Bhaktapur"
    }
  ],
  "guthis": [
    {
      "id": "heritageGraph:guthi-siddhi-lakshmi",
      "name": "Siddhi Lakshmi Guthi",
      "guthi_type": "SiGuthi"
    }
  ],
  "ritual_events": [
    {
      "id": "heritageGraph:ritual-bisket-jatra",
      "name": "Bisket Jatra Festival"
    }
  ]
}
```

## Reporting Format

Conclude the run with:
1. Total entities extracted and categorized by collection type.
2. Cross-references resolved and verified.
3. Summary of skipped, damaged, or unresolvable entries with explicit citations.
