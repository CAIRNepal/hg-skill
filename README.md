# HeritageGraph Skills (`hg-skill`)

Repository containing agent skills for transforming unstructured texts, archival records, and tabular cultural heritage data into validated, ontology-grounded RDF Turtle (`.ttl`) for contribution to the **[HeritageGraph](https://cairnepal.github.io/heritagegraphontology/)** platform by **CAIR-Nepal**.

---

## Architecture & Transformation Pipeline

```mermaid
flowchart LR
    subgraph RawData["Raw Heritage Data"]
        direction TB
        R1["📄 Museum Logs<br/>(Unstructured Text)"]
        R2["📜 Historical Records"]
        R3["🗄️ Database Exports<br/>(CSV / JSON)"]
    end

    subgraph AISkills["AI: Skill Execution"]
        direction TB
        subgraph Stage1["1. Extract & Structure"]
            S1["Information Extraction<br/><i>(01_heritage-extract)</i>"]
            O1[/"extracted.json"/]
            S1 --> O1
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
        Final["🕸️ Semantic Node-Graph<br/><code>ex:monument_001 a crm:E22_Human-Made_Object ;<br/>&nbsp;&nbsp;crm:P14_carried_out_by ex:artisan_042 .</code>"]
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

| Stage | Skill | Description | Primary Output |
|---|---|---|---|
| **00** | [00_heritage-to-rdf](skills/00_heritage-to-rdf/SKILL.md) | End-to-end pipeline orchestrator managing stages 1 through 4. | `graph.ttl` |
| **01** | [01_heritage-extract](skills/01_heritage-extract/SKILL.md) | AI extraction from unstructured/tabular texts into schema-valid JSON. | `extracted.json` |
| **02** | [02_heritage-entity-resolution](skills/02_heritage-entity-resolution/SKILL.md) | Entity grounding and disambiguation via gazetteers, Getty, and Wikidata. | `resolved.json` |
| **03** | [03_heritage-rdf-mapper](skills/03_heritage-rdf-mapper/SKILL.md) | Deterministic triplification into RDF Turtle using declarative CIDOC-CRM mappings. | `graph.ttl` |
| **04** | [04_heritage-shacl-validate](skills/04_heritage-shacl-validate/SKILL.md) | Semantic and structural quality gate validating graphs with pySHACL against HeritageGraph shapes. | `validation-report.json` |

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
