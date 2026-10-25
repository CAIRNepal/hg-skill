---
name: heritage-rdf-mapper
description: >-
  Deterministically map resolved heritage records into Turtle (.ttl) using declarative YAML mappings.
  Stage 3 of the heritage-to-rdf pipeline, targeting CIDOC-CRM (ISO 21127).
disable-model-invocation: true
---

# Heritage RDF Mapper (Stage 3)

Input: `resolved.json` from stage 2.  
Output: `graph.ttl`.

**Core Principle**: Triplication is strictly deterministic. The same input and mapping configuration produce the exact same triples across runs. Correct model or schema discrepancies directly in the mapping YAML (`assets/mappings/`) and re-execute; never patch generated `graph.ttl` by hand.

## Workflow

1. **Ontology Mapping**:
   Uses the declarative CIDOC-CRM (ISO 21127) mapping: `assets/mappings/cidoc-crm.yaml`.
   *(To customize rules or add new ontologies, consult [references/mapping-format.md](references/mapping-format.md))*.

2. **Execute Mapping**:
   Run the mapping script:
   ```bash
   python scripts/map_to_rdf.py resolved.json \
     --mapping assets/mappings/cidoc-crm.yaml \
     --base https://cair-nepal.org/heritagegraph/ \
     --out graph.ttl
   ```

3. **Audit Transformation Report**:
   The script outputs a JSON execution summary:
   - Verify `triples` count is non-zero.
   - Inspect `unmapped`: ensure no critical heritage attributes (dates, creators, locations) were dropped.

4. **Verify Quality Gate**:
   **Completion Gate**: `graph.ttl` exists, contains valid RDF triples, and script exits with code `0`. Once confirmed, proceed to [04_heritage-shacl-validate](../04_heritage-shacl-validate/SKILL.md).

5. **Report**: Present the transformation summary using the **Reporting Format**.

## Reference: URI & Node Handling

- **Linked Entities**: Entities with `status: "linked"` use their authoritative URI (`http://vocab.getty.edu/...`, `http://www.wikidata.org/...`).
- **Local & Ambiguous Entities**: Assigned deterministic URIs prefixed by `--base`. Ambiguous entities receive an `rdfs:comment` flag indicating unresolved status for human review.
- **Physical Object URIs**: Minted as `<base>object/<record_id>`, ensuring cross-run stability.
- **Node Sharing**: Rules sharing the same initial `node` key in mapping YAML (e.g., `production`) reuse the same blank or local node across multiple attributes (dating, creator, place).

## Reporting Format

Conclude the run with:
1. Target ontology and mapping specification used.
2. Total records processed and triples generated.
3. List of any unmapped fields detected during triplication.
4. Next step: handoff to [04_heritage-shacl-validate](../04_heritage-shacl-validate/SKILL.md).
