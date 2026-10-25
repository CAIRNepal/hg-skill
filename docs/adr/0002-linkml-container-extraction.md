# ADR-0002: LinkML Container Schema for Stage-1 Extraction and In-IDE Agent Workflow

## Status
Accepted

## Context
In Stage 1 (Extract & Structure) of the HeritageGraph pipeline, raw cultural heritage records (unstructured field notes, inscriptions, gazetteer texts, archival registers) are parsed into an intermediate, strongly-typed JSON structure before entity resolution and triplication.

Previous prototypes used a bespoke, flat `records: [...]` JSON schema that covered only generic museum objects, failing to represent Nepal's rich living heritage (such as Guthis, Jatras/festivals, ritual events, Kumari tenures, and syncretic caste/deity traditions) and introducing schema drift from the authoritative ontology.

Furthermore, introducing external LLM API keys (e.g., dedicated third-party API configurations) creates friction, credential leakage risks, and vendor lock-in.

## Decision
1. **Canonical Schema from LinkML**:
   - The authoritative schema for Stage 1 extraction is compiled directly from `schemas/HeritageGraph.yaml` (v1.0.1) using LinkML's native schema compiler:
     ```bash
     gen-json-schema schemas/HeritageGraph.yaml -t Container > skills/01_heritage-extract/assets/extraction.schema.json
     ```
   - The root object is the LinkML `Container` (`tree_root: true`), providing typed collections for:
     - Tangible heritage: `structures`, `architectural_elements`, `human_made_objects`, `iconographic_objects`
     - Intangible & living heritage: `festivals`, `ritual_events`, `guthis`, `consecration_events`, `enshrinement_events`, `kumari_tenures`, `caste_groups`, `deities`
     - Agents & Context: `persons`, `actors`, `places`, `materials`, `techniques`, `assertions`, `metadata`

2. **In-IDE Agent Extraction (Zero External API Dependencies)**:
   - The extraction task is executed directly by the in-IDE coding agent (Antigravity) using the system instructions and extraction rules defined in `skills/01_heritage-extract/SKILL.md`.
   - No secondary LLM API keys, client libraries, or external endpoint subscriptions are required.
   - Deterministic validation is performed locally using `validate_extraction.py` backed by `Draft202012Validator`.

3. **Identifier & Reference Conventions**:
   - All extracted entities must have unique CURIE IDs prefixed with `heritageGraph:` (or `hg:`).
   - Cross-references (e.g., `managed_by_guthi`, `has_current_location`, `participates_in_ritual`) must resolve to declared entity IDs within the container or recognized canonical URIs.

## Consequences
- **Zero Schema Drift**: Any update to `schemas/HeritageGraph.yaml` propagates directly to the extraction schema via a single CLI generator command.
- **Full Living Heritage Coverage**: Guthis, rituals, and festivals are first-class entities from the very first extraction stage.
- **Self-Contained Local Tooling**: The entire pipeline operates with local Python tools and the existing IDE agent.
