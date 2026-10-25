# HeritageGraph Skills (`hg-skill`)

Repository containing agent skills for transforming unstructured texts, archival records, multi-page PDF survey reports, and tabular cultural heritage datasets into validated, ontology-grounded RDF Turtle (`.ttl`) for contribution to the **[HeritageGraph](https://cairnepal.github.io/heritagegraphontology/)** platform by **CAIR-Nepal**.

---

## Architecture & Transformation Pipeline

```mermaid
flowchart LR
    subgraph RawData["Raw Heritage Data"]
        direction TB
        R1["📄 Field Surveys & Reports<br/>(Multi-page PDF / OCR)"]
        R2["📜 Inscriptions & Field Notes<br/>(Unstructured Text)"]
        R3["🗄️ Inventories & Catalog Dumps<br/>(CSV / TSV / XLSX / JSON)"]
    end

    subgraph AISkills["AI: Skill Execution"]
        direction TB
        subgraph Stage1["1. Ingest, Preprocess & Extract"]
            direction TB
            Pre["Multi-Format Ingestion & OCR Cleaning<br/><i>(ingest_raw.py / pypdf)</i>"]
            Scan["Living Heritage Scanner<br/><i>(Guthi, Style, Calendar Tagger)</i>"]
            S1["Container Extraction<br/><i>(01_heritage-extract)</i>"]
            O1[/"extracted.json<br/>(LinkML Container)"/]
            Pre --> Scan --> S1 --> O1
        end

        subgraph Stage2["2. Entity Resolution"]
            S2["URI Grounding & Linking<br/><i>(02_heritage-entity-resolution)</i>"]
            O2[/"resolved.json"/]
            Vocab[("Getty (AAT, ULAN)<br/>Wikidata<br/>Internal Gazetteers")]
            Vocab -.-> S2
            S2 --> O2
        end
    end

    subgraph Deterministic["Deterministic Processing & Quality Gate"]
        direction TB
        subgraph Stage3["3. Deterministic Mapper"]
            S3["Triplification<br/><i>(03_heritage-rdf-mapper)</i><br/>RDFLib / Python"]
            Onto[("Ontology Mapping:<br/>CIDOC-CRM (ISO 21127)<br/>HeritageGraph")]
            Onto -.-> S3
            O3[/"graph.ttl"/]
            S3 --> O3
        end

        subgraph Stage4["4. Validation Gate"]
            S4["SHACL Shape Validation<br/><i>(04_heritage-shacl-validate)</i><br/>pySHACL"]
            Shapes[("HeritageGraph.shacl.ttl<br/>Quality Shapes")]
            Shapes -.-> S4
        end
    end

    subgraph OutputGraph["RDF (Turtle / TTL) Graph"]
        direction TB
        Final["🕸️ Semantic Knowledge Graph<br/><code>heritageGraph:struct-nyatapola a heritageGraph:ArchitecturalStructure ;<br/>&nbsp;&nbsp;heritageGraph:hasArchitecturalStyle 'Pagoda' ;<br/>&nbsp;&nbsp;heritageGraph:managedByGuthi heritageGraph:guthi-siddhi-lakshmi .</code>"]
    end

    RawData --> Stage1
    O1 --> Stage2
    O2 --> Stage3
    O3 --> Stage4
    Stage4 -->|CONFORMS| OutputGraph
    Stage4 -.->|Violations / Upstream Loop| Stage1
```

---

## Core Pipeline Stages

The transformation pipeline is organized under [`skills/`](skills/):

| Stage | Skill | Supported Raw Formats | Description | Primary Output |
|---|---|---|---|---|
| **00** | [00_heritage-to-rdf](skills/00_heritage-to-rdf/SKILL.md) | All | End-to-end pipeline orchestrator managing stages 1 through 4. | `graph.ttl` |
| **01** | [01_heritage-extract](skills/01_heritage-extract/SKILL.md) | **PDF**, **CSV**, **TSV**, **XLSX**, **JSON**, raw text | Ingests multi-page PDFs (with OCR line-repair), tabular sheets, and raw texts; scans living heritage; structures into LinkML `Container`. | `extracted.json` |
| **02** | [02_heritage-entity-resolution](skills/02_heritage-entity-resolution/SKILL.md) | `extracted.json` | Entity grounding and disambiguation via gazetteers, Getty (AAT, ULAN), and Wikidata. | `resolved.json` |
| **03** | [03_heritage-rdf-mapper](skills/03_heritage-rdf-mapper/SKILL.md) | `resolved.json` | Deterministic triplification into RDF Turtle using declarative CIDOC-CRM / HeritageGraph mappings. | `graph.ttl` |
| **04** | [04_heritage-shacl-validate](skills/04_heritage-shacl-validate/SKILL.md) | `graph.ttl` | Semantic and structural quality gate validating graphs with pySHACL against `HeritageGraph.shacl.ttl`. | `validation-report.json` |

---

## Stage 1 Ingestion & Preprocessing

Stage 1 provides a unified CLI to ingest and prepare heterogeneous raw heritage data before LLM extraction:

```bash
# Multi-page PDF survey report (extracts text, rejoins hyphenated OCR breaks, strips running page noise)
python skills/01_heritage-extract/scripts/ingest_raw.py survey_report.pdf --out preprocessed.json

# Tabular inventory spreadsheet (separates administrative columns from narrative prose)
python skills/01_heritage-extract/scripts/ingest_raw.py monuments.csv --out preprocessed.json
python skills/01_heritage-extract/scripts/ingest_raw.py monuments.xlsx --out preprocessed.json

# Museum or archival catalog JSON dump
python skills/01_heritage-extract/scripts/ingest_raw.py catalog.json --out preprocessed.json
```

### Living Heritage Candidate Recognition
The preprocessor automatically tags candidate mentions aligned to LinkML enums in `schemas/HeritageGraph.yaml`:
- **Guthi Types**: `SiGuthi`, `RajGuthi`, `JatraGuthi`, `PujaGuthi`, `TempleGuthi`, `NashaGuthi`, `SanaGuthi`, `SanGuthi`.
- **Architectural Styles**: `Pagoda`, `Shikhara`, `Chaitya`, `Stupa`, `Dome`.
- **Calendar Eras**: Nepal Sambat (`NS`), Bikram Sambat (`VS`), Shaka Sambat (`ŚS`), Common Era (`CE/BCE`).
- **Religious Traditions**: Buddhist, Shaiva, Vaishnava, Shakta, Newar syncretic.

---

## Schemas & Ontology Versioning

* **Documentation**: [https://cairnepal.github.io/heritagegraphontology/](https://cairnepal.github.io/heritagegraphontology/)
* **LinkML Source Schema**: [`schemas/HeritageGraph.yaml`](schemas/HeritageGraph.yaml)
* **Ontology TTL**: [`schemas/HeritageGraph.ttl`](schemas/HeritageGraph.ttl)
* **SHACL Quality Shapes**: [`schemas/HeritageGraph.shacl.ttl`](schemas/HeritageGraph.shacl.ttl)
* **Upstream Sources**: [`schemas/SOURCES.md`](schemas/SOURCES.md)

### Updating Ontology Artifacts

To fetch or update ontology artifacts to a specific release tag, branch, or commit:

```bash
# Fetch latest from main (default)
python scripts/update_ontology.py

# Fetch a specific tag or branch
python scripts/update_ontology.py --ref v1.0.1
```

---

## Quick Start: End-to-End Execution

Once stages 1 and 2 produce `resolved.json`, run the deterministic mapping and validation pipeline:

```bash
python skills/00_heritage-to-rdf/scripts/run_pipeline.py resolved.json
```
