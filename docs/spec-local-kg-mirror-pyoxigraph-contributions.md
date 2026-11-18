## Problem Statement

The primary contributor failure mode in HeritageGraph is unintentional duplicate minting. When domain experts or automated agents extract cultural heritage entities from archival records (such as temples, chaityas, guthi organizations, or artisan groups), Stage 2 currently reconciles entities only against external Linked Open Data authorities (Getty AAT/ULAN, Wikidata, Yale LUX) and local static CSV gazetteers. If an entity—such as `heritageGraph:struct-nyatapola`—already exists in the published knowledge graph, the pipeline has no knowledge of it. Consequently, it mints a fresh duplicate URI (e.g. `heritageGraph:struct-nyatapola-bkt`), producing silent graph duplication and co-reference fragmentation that SHACL shape validation cannot detect.

Additionally, contributors and automated agents lack:
1. Fast, offline-first access to authoritative ontology assets and knowledge graph snapshots without requiring AWS credentials or local triplestore server infrastructure (e.g., GraphDB or Jena).
2. Ground-truth pre-flight verification: the ability to diff newly minted triples against the existing published graph before claiming assertions ("42 new entities, 17 references to existing, 3 suspected duplicates requiring review").
3. Standardized contribution packaging with provenance (PROV-O activity traces), per-fact evidence spans (page, line, cell coordinates), and cultural rights/sensitivity guards (for sacred or esoteric Guthi rituals).
4. An intent-routing entry skill and automated diagnostic checks (`hg doctor`) to ensure non-blocking, reliable pipeline execution.

## Solution

1. **Embedded Local KG Mirror (`pyoxigraph`)**: Embed Oxigraph via Python bindings (`pyoxigraph`) as a zero-server, high-performance in-memory/on-disk local mirror of the published HeritageGraph snapshot. Oxigraph parses millions of N-Triples or Turtle statements in seconds with sub-millisecond SPARQL query times and zero daemon management.
2. **Internal-KG-First Resolution Strategy**: Update Stage 2 entity resolution to query the local Oxigraph mirror *first* before consulting external LOD authorities:
   - Fast exact-URI check to immediately reuse known URIs and avoid re-minting.
   - SPARQL-based label, type, and geospatial-proximity matching to discover existing entities.
   - Surface candidate matches and near-duplicates to the human-in-the-loop (HITL) review queue.
3. **Anonymous S3 Asset Synchronization (`hg sync`)**: Implement anonymous S3 fetch (using unsigned requests equivalent to `--no-sign-request` via HTTP/boto3) to retrieve pinned LinkML schemas, ontology TTLs, SHACL shapes, and published knowledge graph snapshots from the CAIR-Nepal AWS Open Data bucket, with local content-hash and ETag caching.
4. **Stage 05 (Diff & Deduplication Gate)**: Introduce a dedicated pipeline stage comparing the triplified graph against the local Oxigraph mirror, calculating graph diffs (new entities, reused URIs, property additions) and halting on uncurated high-probability duplicates.
5. **Stage 06 (Contribution Bundle Packaging)**: Introduce an automated packaging stage producing signed contribution bundles containing contribution-specific named graphs, PROV-O run activities, per-fact evidence source spans, and cultural sensitivity/rights metadata ready for pull-request submission.
6. **Unified CLI Facade (`hg`) & Diagnostics (`hg doctor`)**: Provide a single CLI entry point (`hg sync`, `hg doctor`, `hg run`, `hg diff`, `hg bundle`) with lightweight diagnostic checks that run on demand when failures occur.
7. **Intent-Level Entry Router**: Add a conversational entry skill (`skills/heritagegraph-contribute/`) that inspects contributor intent, checks environment readiness, and routes execution cleanly.

## User Stories

1. As a cultural heritage contributor, I want the entity resolution stage to query the local knowledge graph mirror before generating new identifiers, so that I reuse existing canonical URIs instead of creating duplicate entities.
2. As a data curator, I want the pipeline to download the latest published knowledge graph snapshot and ontology artifacts anonymously from AWS Open Data, so that I do not need AWS credentials or complicated IAM setup to run transformations.
3. As an autonomous agent, I want local graph queries to run via embedded Oxigraph without running background database server processes, so that execution is lightweight, isolated, and fast.
4. As a pipeline operator, I want Stage 2 to perform SPARQL label and type lookups against the local mirror, so that existing monuments and actors are discovered even if exact URIs were not specified in the raw source.
5. As a domain expert, I want suspected entity duplicates to be routed to the interactive HITL review queue, so that human judgment can confirm whether a record represents an existing monument or an uncataloged structure.
6. As a knowledge graph engineer, I want Stage 5 to produce a structured diff report against the mirror, so that maintainers can inspect exactly how many new entities are minted and how many existing entities are referenced.
7. As a data maintainer, I want duplicate entity candidates to block pull-request merging, so that unvetted entity fragmentation is caught before ingestion into production GraphDB.
8. As an archivist, I want extraction outputs to include per-fact evidence spans (page numbers, line numbers, or table cells), so that every asserted RDF triple can be traced directly back to its source document location.
9. As a Guthi custodian, I want contribution records to specify rights and cultural sensitivity flags, so that esoteric ritual knowledge or sacred restricted records are marked with appropriate access tiers and prevented from unrestricted public publishing.
10. As a knowledge graph contributor, I want each pipeline run to generate a distinct named graph with PROV-O attribution metadata, so that merged contributions can be independently audited, attributed, or rolled back if errors occur.
11. As a developer, I want an `hg doctor` diagnostic command that verifies dependencies, network access to S3/Wikidata/Getty, and cache freshness, so that environment issues can be diagnosed immediately when something fails.
12. As a developer, I want `hg sync` to cache snapshots with ETag and version pinning, so that repeated offline pipeline runs do not needlessly re-download multi-gigabyte graph snapshots.
13. As a CI maintainer, I want automated GitHub Actions workflows that re-validate submitted contribution bundles using SHACL and diff gates, so that pull requests are verified without manual maintainer intervention.
14. As a contributor, I want a single command `hg bundle` that packages graph triples, provenance manifests, evidence spans, and metadata into a valid pull-request contribution bundle, so that submission is frictionless.
15. As a new contributor, I want an intent-driven conversational skill that automatically routes my raw files into the appropriate workflow, so that I do not need to memorize low-level stage scripts.
16. As a researcher, I want golden-fixture tests ensuring graph determinism and isomorphism, so that identical source inputs always produce structurally identical RDF output.
17. As an ontology engineer, I want URI minting to adhere strictly to documented transliteration and slug rules, so that newly minted entity URIs remain stable, predictable, and collision-resistant across releases.

## Implementation Decisions

- **Embedded Oxigraph (`pyoxigraph`) Integration**:
  - The local mirror uses `pyoxigraph.Store` configured for fast read-only queries against local snapshot files (`.nt` / `.ttl`).
  - No background HTTP triplestore daemon is required; Oxigraph runs embedded within the Python runtime.
  - Queries are expressed as standard SPARQL 1.1 SELECT queries matching labels (`skos:prefLabel`, `rdfs:label`, `schema:name`), `rdf:type`, and coordinate boundaries.
- **Hierarchical Entity Resolution Order**:
  - Resolution order in Stage 2 is strictly prioritized:
    1. Local Oxigraph Mirror: Exact URI match, then SPARQL label + type match.
    2. Curated Gazetteer: Approved institutional linkages from `curated-links.csv`.
    3. External LOD Providers: Yale LUX, Getty AAT/ULAN, Wikidata.
    4. HITL Review Queue: Unresolved, ambiguous, or near-match candidates staged in `02_review_queue.json`.
    5. Fallback Minting: Mint canonical `heritageGraph:<type>/<slug>` only when all resolution avenues confirm the entity is novel.
- **Anonymous S3 Client & Cache Management**:
  - S3 synchronization uses unsigned HTTP requests (`boto3` with `botocore.UNSIGNED` configuration, or direct HTTPS streaming requests against AWS Open Data URLs).
  - Artifacts are stored in a designated local cache directory (`~/.cache/heritagegraph/` or `.cache/heritagegraph/`), verified against SHA-256 manifests and HTTP ETag headers.
  - Offline mode flag `--offline` allows running against existing cached snapshots without network checks.
- **Stage 05 Diff & Deduplication Engine**:
  - Compares the triplified graph (`03_graph.ttl`) with the local Oxigraph snapshot.
  - Generates `05_diff_report.json` categorizing:
    - `new_entities`: Novel subjects minted in this run.
    - `existing_references`: Statements linking to or enriching existing URIs in the mirror.
    - `suspected_duplicates`: High-scoring fuzzy matches against existing mirror entities that were minted as new URIs without curator confirmation.
  - Returns a non-zero exit code if unresolved duplicate candidates exist.
- **Stage 06 Contribution Bundling & Provenance Model**:
  - Each contribution run generates a dedicated named graph IRI (`heritageGraph:graph/contribution-<run_id>`).
  - Outputs are bundled into a standardized archive or directory containing:
    - Triples serialized as N-Quads / Turtle.
    - `manifest.json` including PROV-O execution activity, input checksums, schema versions, and curation logs.
    - `evidence.json` mapping RDF subject-predicate-object triples to source document spans (page, paragraph, line, table cell).
    - `rights.json` declaring licensing (e.g. CC-BY, CC0) and cultural sensitivity tiers (e.g., Public, Restricted-Sacred, Guthi-Internal).
- **CLI Facade (`src/hg`)**:
  - Package `src/hg/cli.py` provides commands:
    - `hg sync`: Pulls schemas, shapes, and latest KG snapshot.
    - `hg doctor`: Non-blocking environmental diagnosis (Python version, dependencies, cache status, external network reachability).
    - `hg run`: Orchestrates end-to-end transformation (Stages 01–06).
    - `hg diff`: Runs Stage 05 against a completed run.
    - `hg bundle`: Generates Stage 06 contribution package for submission.
- **Intent Router Skill (`heritagegraph-contribute`)**:
  - High-level skill registered under `skills/heritagegraph-contribute/SKILL.md` (under 150 lines) with sub-references in `references/` for URI policy, setup, contribution formatting, and troubleshooting.

## Testing Decisions

- **Good Test Description**:
  - Tests must verify observable system behavior at the highest operational interface (the `hg` CLI and the orchestration engine `run_pipeline`), validating that given raw input fixtures and a mock or local Oxigraph graph snapshot:
    1. Known entities in the snapshot are reused without minting new URIs.
    2. Suspected duplicates are flagged in the diff report.
    3. Contribution bundles contain valid named graphs, PROV-O metadata, and evidence spans.
    4. SHACL validation strictly passes with non-vacuous shape coverage.
  - Tests must NOT assert internal SQL/SPARQL string building details or private Oxigraph pointer manipulation.
- **Modules Tested**:
  - Pipeline Orchestrator & CLI Facade (`src/hg/cli.py` & `run_pipeline`): End-to-end execution across Stages 01–06.
  - S3 Sync & Cache Manager: Validates anonymous fetch, ETag verification, and offline fallback.
  - Oxigraph Resolution Provider (Stage 02): Validates exact URI reuse and SPARQL candidate matching.
  - Diff & Dedupe Engine (Stage 05): Validates graph delta computation, new entity counts, and duplicate detection.
  - Contribution Bundler (Stage 06): Validates named graph serialization, PROV-O statements, and rights metadata packaging.
  - Golden Fixture Suite: Determinism tests (identical inputs yield identical graph checksums) and graph isomorphism checks.
- **Prior Art**:
  - `tests/test_pipeline_run_e2e.py` (Run workspace orchestration and lifecycle gates).
  - `tests/test_stage3_entity_links.py` (LOD predicate mapping and resolution output).
  - `tests/test_interactive_resolution.py` (Review queue and HITL gazetteer integration).
  - `tests/test_stage4_coverage.py` (SHACL quality gates and non-vacuous validation).

## Out of Scope

- Hosting a public multi-tenant SPARQL endpoint server or deploying GraphDB/Fuseki server clusters.
- Automatically approving fuzzy duplicate matches without human curation.
- Direct automated push/commit to production `main` branch without pull request review.
- Complex digital asset management or binary media (high-resolution image/3D scan) hosting.

## Further Notes

- PyOxigraph documentation: https://pyoxigraph.readthedocs.io/
- AWS Open Data Sponsorship Program guidelines for anonymous public bucket hosting.
- W3C PROV-O specification: https://www.w3.org/TR/prov-o/
- LinkML container schema specification: `schemas/HeritageGraph.yaml`.

