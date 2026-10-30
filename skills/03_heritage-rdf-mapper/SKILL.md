---
name: heritage-rdf-mapper
description: >-
  Deterministically map the extracted/resolved Container into HeritageGraph-native Turtle (.ttl)
  using a declarative YAML mapping generated from the LinkML schema. Stage 3 of the
  heritage-to-rdf pipeline. A CIDOC-CRM mapping remains available as an alternate.
disable-model-invocation: true
---

# Heritage RDF Mapper (Stage 3)

Input: `resolved.json` (or `extracted.json`) Container from stage 1/2.  
Output: `graph.ttl`, typed with `heritageGraph:` classes and properties.

**Core Principle**: Triplification is strictly deterministic. The same input and mapping configuration produce the exact same triples across runs. Correct model or schema discrepancies in the schema, the overrides file or the generator and re-execute; never patch generated `graph.ttl` or the generated mapping by hand.

## Workflow

1. **Ontology Mapping**:
   Default: `assets/mappings/heritagegraph.yaml`, **generated** from `schemas/HeritageGraph.yaml` (each Container collection maps to its class, each slot to its `slot_uri`). After an ontology update (`python scripts/update_ontology.py --ref <ref>`), regenerate:
   ```bash
   python scripts/generate_mapping.py          # add --check to detect a stale mapping
   python scripts/generate_mapping.py --format yarrrml # export W3C YARRRML mapping
   ```
   Exceptions live in `assets/mappings/heritagegraph.overrides.yaml` (replace or suppress a slot rule, or change a class). Alternate: `assets/mappings/cidoc-crm.yaml` (record-based, CRM-typed output; validate with `--allow-crm-only`).
   *(Mapping syntax: [references/mapping-format.md](references/mapping-format.md))*.

2. **Execute Mapping**:
   Run the mapping script:
   ```bash
   python scripts/map_to_rdf.py resolved.json \
     --base https://cair-nepal.org/heritagegraph/ \
     --out graph.ttl
   ```
   (`--mapping` defaults to `heritagegraph.yaml`.)

3. **Audit Transformation Report**:
   The script outputs a JSON execution summary:
   - Verify `triples` count is non-zero.
   - Inspect `unmapped`: ensure no critical heritage attributes (dates, creators, locations) were dropped.

4. **Verify Quality Gate**:
   **Completion Gate**: `graph.ttl` exists, contains valid RDF triples, and script exits with code `0`. Once confirmed, proceed to [04_heritage-shacl-validate](../04_heritage-shacl-validate/SKILL.md).

5. **Report**: Present the transformation summary using the **Reporting Format**.

## Reference: URI & Node Handling

- **Entity URIs**: In the native mapping every entity keeps its Container `heritageGraph:` id as its URI, so cross-references (`managed_by_guthi`, `has_current_location`, ...) always resolve.
- **Linked Entities**: Entities with `resolution.status: "linked"` gain a `skos:exactMatch` to the authoritative URI (`http://vocab.getty.edu/...`, `http://www.wikidata.org/...`); the id is never replaced.
- **Ambiguous Entities**: Receive an `rdfs:comment` flag indicating unresolved status for human review. Local entities need no extra triple.
- **Literals**: Plain `xsd:string` (no language tags), because HeritageGraph shapes require `xsd:string`. Enums become `heritageGraph:<Enum>#<Value>` IRIs.
- **Alternate CRM mapping** (record-based): linked entities use their authoritative URI directly; physical objects are minted as `<base>object/<record_id>`; rules sharing the same initial `node` key (e.g., `production`) reuse one node across attributes.

## Reporting Format

Conclude the run with:
1. Target ontology, mapping and schema version used.
2. Total records processed and triples generated.
3. List of any unmapped fields detected during triplication.
4. Next step: handoff to [04_heritage-shacl-validate](../04_heritage-shacl-validate/SKILL.md).
