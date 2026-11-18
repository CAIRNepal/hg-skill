# Contribution Bundle Specification & Rights Metadata

This document defines the contribution bundle format produced by Stage 06 (`hg bundle`).

## Bundle Directory Layout

```
06_contribution_bundle/
├── bundle.json               # Bundle manifest, UUID, timestamps, and file checksums
├── contribution-graph.nq     # Triples serialized in a dedicated named graph (N-Quads)
├── provenance.ttl            # PROV-O execution activity and lineage
├── manifest.json             # Copy of the transformation run manifest
├── evidence.json             # Per-fact source document spans (page/line/cell coordinates)
├── rights.json               # Cultural sensitivity tiers and licensing declarations
├── diff_report.json          # Stage 05 diff vs. local KG mirror
└── shacl_report.json         # Stage 04 SHACL validation results
```

## Named Graph Typing

To enable clean merge, audit, attribution, and rollback semantics, all asserted triples in a contribution are scoped to a unique named graph:

```
https://cair-nepal.org/heritagegraph/graph/contribution-<run_id>
```

In N-Quads format, every asserted fact includes this graph context as its fourth element.

## PROV-O Activity Envelope

Each contribution records a W3C PROV-O activity in `provenance.ttl`:
- `prov:Activity`: The pipeline run execution, tracking timestamps and tools used.
- `prov:wasAssociatedWith`: The contributor agent or curator.
- `prov:wasGeneratedBy`: Links the named graph entity to the activity.
- `prov:wasDerivedFrom`: Links the graph entity to the original source document checksum.

## Cultural Rights & Sensitivity Metadata

Cultural heritage records from Nepal often include sacred, secret, or esoteric knowledge (e.g., internal Guthi ritual records, tantric iconography, initiation texts).

HeritageGraph recognizes three sensitivity tiers in `rights.json`:
1. `public`: Unrestricted open access (published under CC-BY-4.0 or CC0).
2. `restricted-sacred`: Sacred knowledge with community restrictions; excluded from open downloads.
3. `guthi-internal`: Esoteric custodial records accessible only to verified guthi members.

Contributions containing `restricted-sacred` or `guthi-internal` records are automatically flagged with `"restricted_distribution": true` in `manifest.json` and prevented from public export.
