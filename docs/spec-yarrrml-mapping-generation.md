## Problem Statement

Users and external researchers working with Knowledge Graphs and Linked Data often standardize on W3C RML (RDF Mapping Language) and its YAML syntax, YARRRML, for triplification. Currently, the repository's Stage 3 mapping relies exclusively on an internal custom YAML format executed by an internal mapper. External data pipelines and researchers cannot easily reuse the LinkML-defined mappings within standard RML toolchains (such as `rmlmapper`, `morph-kgc`, or Web-based YARRRML parsers) without manually translating the schema into YARRRML. Furthermore, attempting to bypass Stages 1 and 2 by running raw CSVs directly through RML loses domain-specific entity extraction and reconciliation.

## Solution

1. **YARRRML Generator**: Extend the schema mapping generator with a `--format yarrrml` option to export valid, standards-compliant YARRRML rules (`heritagegraph.yarrrml.yaml`) derived deterministically from the LinkML schema and overrides.
2. **Standardized Target Mapping**: Configure generated YARRRML rules to target the structured Container schema (`02_resolved.json`), mapping collection records, literal values, enumerated IRIs, and resolved entity links (e.g. `skos:exactMatch`, `skos:broadMatch`, etc.) to standard Subject-Predicate-Object maps.
3. **Documented Pipeline Boundary (ADR-0005)**: Formalize the decision that tabular inputs (CSV/XLSX) must pass through extraction (Stage 1) and resolution (Stage 2) before triplification, ensuring data quality, living heritage scanning, and multi-authority LOD grounding.

## User Stories

1. As a Knowledge Graph engineer, I want to export a YARRRML mapping file from our LinkML schema, so that I can use standard RML engines (such as Morph-KGC or RMLMapper) in external data workflows.
2. As a Linked Data researcher, I want the generated YARRRML to map JSON paths in `02_resolved.json` to canonical HeritageGraph classes and predicates, so that the triplified output adheres strictly to the ontology.
3. As a pipeline developer, I want `generate_mapping.py --format yarrrml` to respect the overrides file, so that custom slot rules and class substitutions apply consistently to both native and YARRRML outputs.
4. As a pipeline operator, I want YARRRML generation to be deterministic, so that identical schema versions produce identical YARRRML output files across different environments.
5. As a curator, I want entity resolutions (`uri` and `match_type`) from Stage 2 to be correctly represented in the YARRRML mapping rules, so that external RML runs preserve graded SKOS and OWL alignments.
6. As a CI engineer, I want a validation check (`--check`) that ensures committed YARRRML mapping assets do not drift from the authoritative LinkML schema.
7. As a new contributor, I want clear architectural documentation explaining why tabular datasets are not triplified directly from raw CSV with RML, so that I understand the importance of extraction and entity resolution stages.

## Implementation Decisions

- **Mapping Generator Flag**: The schema mapping generation utility is augmented with a `--format` argument accepting `native` (default) and `yarrrml`.
- **YARRRML Schema Structure**: The exported YARRRML follows standard YARRRML specification:
  - `prefixes`: Bound namespaces extracted from the LinkML schema and built-in prefixes.
  - `mappings`: One mapping definition per collection in the Container schema.
  - `sources`: Targets `02_resolved.json` using JSONPath expressions (`$.collection[*]`).
  - `s`: Subject reference template using the entity ID or minted URI pattern.
  - `po`: Predicate-object pairs mapping plain literals, datatype-tagged literals, referenced entity IRIs, and resolved external matches.
- **Pure-Python Generation**: The YARRRML file is generated using PyYAML directly in Python with no requirement for Node.js or Java tools during generation.
- **Architectural Preservation**: Native Python execution via RDFLib remains the default pipeline runtime; YARRRML serves as an interoperable export and alternative execution specification.

## Testing Decisions

- **Good Test Description**: Tests must verify that generated YARRRML parses as valid YAML conforming to the YARRRML specification structure, that all collections from the schema are represented with correct subject and predicate-object maps, and that running the generator with `--check` flags detecting drift.
- **Modules Tested**:
  - Mapping Generator: Verifies output structure, prefix binding, and slot translation for `--format yarrrml`.
  - Freshness Checker: Verifies that committed YARRRML assets match the schema.
- **Prior Art**: Existing mapping generation tests in the test suite verifying fresh mapping generation against schema files.

## Out of Scope

- Bundling Node.js `@rmlio/yarrrml-parser` or Java `rmlmapper` binaries in the repository dependencies.
- Writing a standalone RML interpreter from scratch (external RML runners handle execution).
- Mapping raw un-extracted CSV directly to RDF via RML.

## Further Notes

- YARRRML documentation and specification: https://rml.io/yarrrml/
- Morph-KGC (Python-based RML/YARRRML engine): https://github.com/morph-kgc/morph-kgc

