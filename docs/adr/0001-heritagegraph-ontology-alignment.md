# ADR-0001: Adoption of HeritageGraph Ontology & CIDOC-CRM Alignment

## Status
Accepted

## Context
The goal of `hg-skill` is to extract, resolve, and transform unstructured and tabular cultural heritage records into validated RDF Turtle (`.ttl`) graphs for contribution to the **HeritageGraph** platform operated by CAIR-Nepal.

Previous scaffolding included generic or alternate models (such as Europeana Data Model - EDM). However, the authoritative domain schema for HeritageGraph is defined in [HeritageGraph.ttl](file:///c:/Users/nabin/Desktop/myall/hg-skill/schemas/HeritageGraph.ttl) and its associated SHACL shapes [HeritageGraph.shacl.ttl](file:///c:/Users/nabin/Desktop/myall/hg-skill/schemas/HeritageGraph.shacl.ttl), which extend CIDOC-CRM (ISO 21127), CRMinf, and PROV-O.

## Decision
1. **Target Ontology**: Standardize exclusively on the CAIR-Nepal Cultural Heritage Ontology (`heritageGraph:` namespace `https://cair-nepal.org/heritagegraph/`) and its foundational CIDOC-CRM mapping. Remove EDM.
2. **Quality Gate**: Use pySHACL to validate all emitted Turtle graphs against `schemas/HeritageGraph.shacl.ttl`.
3. **Pipeline Stages**: Enforce the 4-stage pipeline:
   - Stage 1: Extraction & Structuring (`extracted.json`)
   - Stage 2: Entity Resolution (`resolved.json`)
   - Stage 3: Deterministic RDF Mapping (`graph.ttl`)
   - Stage 4: SHACL Validation (`validation-report.json`)

## Consequences
- Data contributions conform directly to HeritageGraph ingest criteria.
- Downstream triplication and validation scripts share consistent namespaces and shapes.
