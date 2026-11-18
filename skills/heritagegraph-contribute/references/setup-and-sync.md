# Setup and S3 Synchronization (`hg sync` & `hg doctor`)

This guide explains how to set up the HeritageGraph contributor environment and synchronize authoritative assets from the AWS Open Data bucket.

## Environment Diagnostics: `hg doctor`

Run the diagnostic tool to verify that your environment has all required dependencies and network access:

```bash
python -m hg.cli doctor
```

Checks performed:
- Python runtime version (>= 3.10 required).
- Core packages: `pyoxigraph`, `rdflib`, `pyshacl`, `requests`, `linkml`.
- Optional packages: `boto3`, `luxy`, `pypdf`, `openpyxl`.
- Local cache presence in `~/.cache/heritagegraph/`.
- Reachability of external Linked Open Data endpoints (Wikidata, Getty, Yale LUX, S3).

## Anonymous S3 Synchronization: `hg sync`

The HeritageGraph knowledge graph and LinkML ontology assets are hosted on AWS Open Data with public, anonymous read access (no AWS credentials or IAM keys needed).

To download or refresh the local cache:

```bash
python -m hg.cli sync
```

### S3 Layout

```
s3://cair-nepal-heritagegraph/
├── ontology/
│   ├── HeritageGraph.yaml       # Authoritative LinkML schema
│   ├── HeritageGraph.ttl        # Core OWL/RDFS ontology
│   └── HeritageGraph.shacl.ttl  # SHACL shape definitions
└── snapshots/
    ├── manifest.json            # Snapshot metadata & checksums
    └── kg-YYYY-MM-DD.nt         # Compressed N-Triples graph snapshot
```

### Offline Mode

If working without an internet connection or in air-gapped environments:

```bash
python -m hg.cli sync --offline
```

As long as a snapshot was previously downloaded into `~/.cache/heritagegraph/snapshots/`, the pipeline will use the cached snapshot without issuing network requests.
