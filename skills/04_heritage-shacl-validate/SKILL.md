---
name: heritage-shacl-validate
description: >-
  Validate generated RDF graphs against CIDOC-CRM SHACL shapes using pySHACL.
  Final quality gate (stage 4) ensuring semantic and structural integrity before delivery.
disable-model-invocation: true
---

# Heritage SHACL Validation (Stage 4)

Input: `graph.ttl` from stage 3.  
Output: `validation-report.json` and conformance sign-off.

**Core Principle**: Shapes represent the authoritative semantic contract of the knowledge graph. Always remediate violations upstream at the source stage; never weaken or edit shapes to force an invalid graph to pass.

## Workflow

1. **Execute Validation**:
   Run the SHACL validator against HeritageGraph shapes:
   ```bash
   python scripts/validate.py graph.ttl \
     --shapes assets/shapes/HeritageGraph.shacl.ttl \
     --report validation-report.json
   ```
   *(For shape authoring guidelines and constraint components, consult [references/shacl-notes.md](references/shacl-notes.md))*.
   The report (`validation-report.json`) includes `shape_coverage` (shapes matched and nodes matched per shape). A graph with **no `heritageGraph:` instances**, or one that matches **no shape**, **fails as vacuous** (`"vacuous": true`): nothing was validated. For the CIDOC-CRM alternate mapping pass `--allow-crm-only`.

2. **Evaluate Conformance**:
   - **Exit code `0` (`CONFORMS`)**: The graph satisfies all semantic constraints. Proceed to **Step 4 (Final Delivery)**.
   - **Exit code `1` (`FAILS`)**: Violations detected. Proceed to **Step 3 (Upstream Remediation Loop)**.

3. **Upstream Remediation Loop**:
   - Inspect `validation-report.json` and group violations by pattern.
   - Trace the root cause upstream following the **Diagnostic Mapping**:
     - *Missing required attributes* (e.g., missing titles, dates): Remediate in [01_heritage-extract](../01_heritage-extract/SKILL.md).
     - *Malformed or unlinked URIs*: Remediate in [02_heritage-entity-resolution](../02_heritage-entity-resolution/SKILL.md).
     - *Misplaced properties or illegal domain/range*: Remediate in the Stage 3 mapping source: fix the schema or add an exception in [03_heritage-rdf-mapper/assets/mappings/heritagegraph.overrides.yaml](../03_heritage-rdf-mapper/assets/mappings/heritagegraph.overrides.yaml), then regenerate with `scripts/generate_mapping.py` (never hand-edit the generated `heritagegraph.yaml`; for the alternate CRM path edit [cidoc-crm.yaml](../03_heritage-rdf-mapper/assets/mappings/cidoc-crm.yaml)).
     - *Vacuous failure* (zero `heritageGraph:` instances / no shape matched): the mapper emitted wrong or no types. Check the Stage 3 `unmapped_fields` report and that the heritagegraph mapping is in use.
   - Re-execute the pipeline from the modified stage forward, then re-run validation.

4. **Final Delivery & Quality Sign-Off**:
   **Completion Gate**: Script exits with code `0` (`CONFORMS`). Deliver `graph.ttl` accompanied by the **Reporting Format**.

## Reference: Diagnostic Mapping

| Violation Pattern | Likely Root Cause | Upstream Remediation Stage |
|---|---|---|
| Missing identifier or title (`MinCountConstraintComponent`) | Extraction omitted key fields from raw data | [01_heritage-extract](../01_heritage-extract/SKILL.md) |
| Invalid class on actor or place (`ClassConstraintComponent`) | Resolution mapped to wrong entity kind or vocabulary | [02_heritage-entity-resolution](../02_heritage-entity-resolution/SKILL.md) |
| Predicate directly on object instead of event (`MaxCountConstraintComponent`) | Mapping YAML attached activity predicate directly to `E22_Object` | [03_heritage-rdf-mapper](../03_heritage-rdf-mapper/SKILL.md) |
| Malformed begin/end date format (`DatatypeConstraintComponent`) | Date parsing failed to output valid ISO 8601 bounds | [01_heritage-extract](../01_heritage-extract/SKILL.md) |

## Reporting Format

Conclude the quality audit with:
1. Conformance verdict: `CONFORMS` (Pass) or `FAILS`.
2. Total triples validated and shapes matched (`shape_coverage`).
3. Summary of any upstream fixes applied during remediation.
4. Final graph deliverable path (`graph.ttl`) and validation report path (`validation-report.json`).
