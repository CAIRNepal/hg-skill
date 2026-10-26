# ADR-0004: Native HeritageGraph Output via a Generated Stage 3 Mapping

## Status
Accepted

## Context
Stage 3 originally emitted plain CIDOC-CRM from a hand-written record-based mapping (`cidoc-crm.yaml`). Three problems followed:

1. **Wrong deliverable**: the platform contribution is HeritageGraph RDF, but `graph.ttl` contained only `crm:` classes. No `heritageGraph:` class appeared in any output.
2. **Vacuous validation**: Stage 4 reported `CONFORMS` although the generated `heritageGraph:` shapes matched no node, so nothing about the HeritageGraph model was checked.
3. **Dropped living heritage**: Stage 1 emits a typed LinkML Container (Guthis, Festivals, ritual events, ...), but the record-based rules covered only a flat object model, and Stage 2 replaced local ids with Getty/Wikidata URIs, which broke the `heritageGraph:` id cross-references that Stage 1 depends on (ADR-0002).

## Decision
1. **Native output**: `graph.ttl` is typed with the classes and properties the HeritageGraph ontology declares (`class_uri` / `slot_uri`). CRM alignment is the ontology's own business; where it declares a CRM `class_uri` (for example `crm:E53_Place` for Place) the output follows it.
2. **Generated mapping**: `skills/03_heritage-rdf-mapper/scripts/generate_mapping.py` derives `heritagegraph.yaml` from `schemas/HeritageGraph.yaml`, mirroring ADR-0002's zero-drift approach. The mapping records the schema version and SHA-256, and `--check` detects a stale mapping. Hand-written exceptions live in `heritagegraph.overrides.yaml`.
3. **Container-walking mapper**: each Container collection maps to its class and each slot to its `slot_uri` (literal, `ref`, or `enum`). The record-based path remains for `cidoc-crm.yaml`.
4. **Ids stay URIs**: Container `heritageGraph:` ids are the entity URIs. Stage 2 results add `skos:exactMatch` to the external URI (linked) or an `rdfs:comment` review flag (ambiguous); they never replace the id.
5. **No language tags in native output**: HeritageGraph shapes require `xsd:string` for text slots and a language-tagged literal (`rdf:langString`) fails that constraint. Text is preserved verbatim, including non-Latin scripts.
6. **No vacuous passes**: Stage 4 fails a graph with zero `heritageGraph:` instances or no matched shape, and reports per-shape coverage. The CRM alternate opts out with `--allow-crm-only`.
7. **Default and alternate**: `heritagegraph` is the pipeline default (`run_pipeline.py --ontology heritagegraph`); `cidoc-crm` remains as `--ontology cidoc-crm`.

## Consequences
- Ontology updates need `update_ontology.py` then `generate_mapping.py`; no manual mapping edits.
- Golden-file tests (`tests/golden/`) pin the Stage 3 output byte-for-byte; `.gitattributes` marks them `-text` so line endings are not rewritten.
- Source-language tags are not carried into native output. If the ontology later allows `rdf:langString`, the mapper can add them without changing the mapping format.
- Slots whose range is an inlined object (rather than an id reference) are linked by the inlined object's `id` and its nested fields are reported as unmapped, never silently dropped.
