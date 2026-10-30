## Problem Statement

When extracting cultural heritage records (monuments, artifacts, concepts, guthis, materials), entities currently face two major limitations in external linked open data (LOD) connectivity:
1. **Lack of integration with Yale LUX**: While Wikidata and Getty AAT/ULAN/TGN have basic lookup scripts, Yale LUX (the Linked Art platform indexing museum and library cultural collections, concepts, and places across Yale and partner institutions) is not integrated. Extracted entities cannot discover or link to candidate LUX records.
2. **Flattened mapping semantics**: The entity resolution and RDF mapping stages currently treat all resolved external links as flat `skos:exactMatch` assertions. In cultural heritage, concepts and entities often have broader, narrower, or close relationships (e.g., a specific Nepalese architectural style to a broader Getty AAT classification, or a regional deity manifestation to a close Wikidata concept). Lumping all alignments into `skos:exactMatch` distorts semantic fidelity.
3. **Dual-level alignment ambiguity**: Users need clarity and synchronization between class-level alignments in the core ontology (`schemas/HeritageGraph.yaml`) and instance-level / vocabulary alignments produced during dataset ingestion, ensuring local URI sovereignty is preserved while establishing rich outbound links.

## Solution

1. **Yale LUX Lookup Provider**: Integrate LUX lookup capability (using the Yale LUX Search API / `luxy` wrapper) across Concepts, Places, Works, and Objects, normalizing candidates into the standard candidate resolution pool alongside Wikidata and Getty.
2. **Graded SKOS & Identity Predicates**: Upgrade the entity resolution data model to capture exact relationship semantics: `skos:exactMatch`, `skos:closeMatch`, `skos:broadMatch`, `skos:narrowMatch`, and `owl:sameAs`. Allow both automated resolvers and human curators in the interactive review queue to assign match types.
3. **Stage 3 Triplification Alignment**: Update the RDF mapper to emit the specific SKOS or OWL predicate corresponding to the resolution record while keeping the minted HeritageGraph URI as the canonical subject.
4. **LinkML Schema Expansion**: Align class-level mappings in `schemas/HeritageGraph.yaml` to include corresponding LUX and Wikidata concepts using LinkML's `exact_mappings`, `close_mappings`, `broad_mappings`, and `narrow_mappings`.

## User Stories

1. As a heritage data curator, I want to query Yale LUX for cultural objects and conceptual terms during Stage 2 entity resolution, so that Nepalese heritage items held in or cataloged by Linked Art repositories can be discovered and linked.
2. As a knowledge graph engineer, I want entity resolutions to support `skos:broadMatch` and `skos:narrowMatch`, so that a specialized Nepalese monument type (e.g., a Shikhar-style temple) can be linked to a broader classification in Getty AAT or LUX without claiming equivalence.
3. As a knowledge graph engineer, I want entity resolutions to support `skos:closeMatch`, so that syncretic or near-equivalent deities and architectural terms can be linked without breaking logical consistency.
4. As a knowledge graph engineer, I want entity resolutions to support `owl:sameAs`, so that definitive co-referent individuals (such as identical physical monuments cataloged in Wikidata) can be formally asserted as identical.
5. As a pipeline operator, I want every entity to retain its canonical, minted HeritageGraph URI as the subject of all RDF statements, so that HeritageGraph maintains an autonomous, sovereign URI space.
6. As a human curator using the interactive review CLI (`--interactive`), I want to select the match degree (exact, close, broad, narrow, same-as) when linking an entity to a candidate URI, so that human judgment determines the semantic relationship.
7. As an automated pipeline, I want unlinked or ambiguous entities to be staged in the review queue with candidate suggestions from LUX alongside Wikidata and Getty, so that non-interactive CI jobs run without interruption.
8. As a downstream SPARQL researcher, I want to traverse from HeritageGraph nodes outward to LUX, Wikidata, and Getty via standard SKOS mapping properties, so that federated queries across global heritage platforms succeed.
9. As an ontology engineer, I want the LinkML schema (`schemas/HeritageGraph.yaml`) to document verified class-level alignments to LUX and Wikidata concepts, so that ontology validation and SHACL shapes reflect international Linked Art and LOD standards.

## Implementation Decisions

- **Candidate Resolution Model**: The resolution schema for entities in Stage 2 is extended with an explicit `match_type` field with allowed values: `exact`, `close`, `broad`, `narrow`, `sameAs`. When omitted, `exact` is preserved for backward compatibility.
- **LUX Provider Integration**: A dedicated lookup client is introduced using Yale LUX REST search endpoints (with `luxy` integration or direct HTTP fallback) across Concepts, Places, Objects, and Works. Candidates are normalized to `{uri, label, source, description, type, match_type}`.
- **Predicates in RDF Mapping**: The RDF triplifier maps `match_type` to its corresponding RDF predicate:
  - `exact` -> `skos:exactMatch`
  - `close` -> `skos:closeMatch`
  - `broad` -> `skos:broadMatch`
  - `narrow` -> `skos:narrowMatch`
  - `sameAs` -> `owl:sameAs`
- **Sovereign Subject URIs**: External URIs never replace the entity's minted subject URI in the output knowledge graph; all alignments are emitted as outbound predicates with the external URI as the object.
- **Interactive Review CLI**: The interactive prompt in Stage 2 is expanded to allow curators to select candidate match types when confirming an alignment.

## Testing Decisions

- **Good Test Description**: Tests must verify external behavior through pipeline artifact boundaries (input JSON -> output resolved JSON and RDF graph) rather than asserting internal API mock details. Tests should confirm that appropriate SKOS and OWL predicates appear in the parsed RDF graph based on the resolution configuration.
- **Modules Tested**:
  - Entity Resolution Runner (Stage 2): Verifies candidate generation and structured resolution output including `match_type`.
  - LUX Lookup Client: Verifies response parsing and normalization from LUX search responses into candidate schemas.
  - RDF Mapper (Stage 3): Verifies that resolved entities with different `match_type` values produce the exact expected RDF triples (`skos:broadMatch`, `skos:narrowMatch`, `skos:closeMatch`, `skos:exactMatch`, `owl:sameAs`).
- **Prior Art**: Existing tests in `tests/test_stage3_entity_links.py`, `tests/test_interactive_resolution.py`, and `tests/test_review_queue.py`.

## Out of Scope

- Bi-directional sync or harvesting of full LUX collection graphs into HeritageGraph.
- Real-time SPARQL endpoint federation during pipeline runtime (all external alignments are resolved at Stage 2).
- Automatic reconciliation of ungrounded entities without human review when confidence is below defined thresholds.

## Further Notes

- Yale LUX uses Linked Art (JSON-LD) models. LUX URIs conform to patterns like `https://lux.collections.yale.edu/data/concept/<uuid>` and `https://lux.collections.yale.edu/data/place/<uuid>`.
- The `luxy` Python library wraps these endpoints cleanly and can be included in `requirements.txt` or integrated with resilient HTTP fallback.

