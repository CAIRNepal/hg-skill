# ADR-0005: YARRRML / RML Interoperability and Pipeline Triplification Boundary

## Status
Accepted

## Context
When transforming tabular data (CSV/XLSX) into RDF Turtle (`.ttl`), standardized semantic web mapping languages such as RML (RDF Mapping Language) and its human-readable YAML syntax, [YARRRML](https://rml.io/yarrrml/), are widely recognized in the Linked Data community.

However, adopting direct CSV-to-TTL RML mapping introduces critical architectural tensions in the context of the Himalayan and Nepalese cultural heritage domain:
1. **Loss of Staged Domain Processing**: Direct CSV-to-TTL mapping via RML bypasses Stage 1 living heritage scanning, script normalization, and LinkML container validation, as well as Stage 2 entity resolution (linking to Wikidata, Getty, Yale LUX, local Guthis, and human-in-the-loop review).
2. **Heavy External Runtime Dependencies**: Standard RML execution engines rely on Java/JRE (`rmlmapper`) or Node.js (`@rmlio/yarrrml-parser`), introducing fragile non-Python runtime environments and CI overhead.
3. **Complex Dynamic Resolution Joins**: Multi-source reconciliation (graded SKOS matches, review flags, minted local URI preservation) is awkward and brittle when expressed as raw RML join conditions against live external APIs.

## Decision
1. **Preserve Staged Pipeline Architecture**:
   - Tabular sources (CSV/XLSX) must continue through Stage 1 (`01_extracted.json`) and Stage 2 (`02_resolved.json`) before triplification.
   - Raw CSVs are never mapped directly to TTL, ensuring all entities undergo validation, gazetteer alignment, and resolution.
2. **YARRRML as a First-Class Exportable Mapping Standard**:
   - Stage 3's mapping generator (`generate_mapping.py`) will support an export target generating standards-compliant YARRRML (`heritagegraph.yarrrml.yaml`) directly from `schemas/HeritageGraph.yaml`.
   - This provides full interoperability with the wider W3C/RML tooling ecosystem without tying pipeline execution to external runtimes.
3. **Pure-Python Native Execution Engine by Default**:
   - The primary pipeline runner (`map_to_rdf.py`) remains pure Python with RDFLib, executing in milliseconds with zero non-Python dependencies.
   - For environments standardizing strictly on RML engines, the exported YARRRML can be compiled to RML and executed via `morph-kgc` or `rmlmapper` against `02_resolved.json`.

## Consequences
- **High Data Quality**: Living heritage records preserve rich entity resolution, provenance assertions, and SHACL compliance.
- **Standards Interoperability**: Researchers and external organizations can leverage standard YARRRML/RML mappings across external triple stores.
- **Zero-Friction Local Execution**: Developers and automated CI runners retain fast, dependency-free execution in pure Python.

