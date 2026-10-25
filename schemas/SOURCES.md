# HeritageGraph Authoritative Ontology Sources

This document records the official upstream repository and raw artifact URLs for the CAIR-Nepal **HeritageGraph** ontology. When the user requests a different version, release tag, or branch, use these URL patterns to fetch and update local schemas.

## Upstream Repository
- **Repository**: [CAIRNepal/heritagegraphontology](https://github.com/CAIRNepal/heritagegraphontology)
- **Documentation**: [https://cairnepal.github.io/heritagegraphontology/](https://cairnepal.github.io/heritagegraphontology/)
- **Default Branch**: `main`
- **Current Version in Repository**: `1.0.1`

---

## Authoritative Raw Artifact URLs (Default: `main`)

| Artifact | Upstream Raw URL | Local Destination |
|---|---|---|
| **LinkML Schema YAML** | `https://raw.githubusercontent.com/CAIRNepal/heritagegraphontology/refs/heads/main/ontology/HeritageGraph.yaml` | `schemas/HeritageGraph.yaml` |
| **Ontology TTL** | `https://raw.githubusercontent.com/CAIRNepal/heritagegraphontology/refs/heads/main/ontology/HeritageGraph.ttl` | `schemas/HeritageGraph.ttl` |
| **SHACL Shapes TTL** | `https://raw.githubusercontent.com/CAIRNepal/heritagegraphontology/refs/heads/main/ontology/HeritageGraph.shacl.ttl` | `schemas/HeritageGraph.shacl.ttl` & `skills/04_heritage-shacl-validate/assets/shapes/HeritageGraph.shacl.ttl` |

---

## Versioning & URL Templates

To download a specific version, release tag (e.g., `v1.0.0`, `v1.0.1`, `alpha.5`), or branch:

### URL Template Pattern
```text
https://raw.githubusercontent.com/CAIRNepal/heritagegraphontology/<REF>/ontology/HeritageGraph.<EXT>
```
Where:
- `<REF>`: Branch name (e.g. `refs/heads/main`), release tag (e.g. `v1.0.1`), or commit SHA.
- `<EXT>`: `yaml`, `ttl`, or `shacl.ttl`.

### Fetch Command Pattern

**PowerShell**:
```powershell
$ref = "main" # or "v1.0.1", "alpha.5", etc.
$baseUrl = "https://raw.githubusercontent.com/CAIRNepal/heritagegraphontology/$ref/ontology"

Invoke-WebRequest -Uri "$baseUrl/HeritageGraph.yaml" -OutFile "schemas/HeritageGraph.yaml"
Invoke-WebRequest -Uri "$baseUrl/HeritageGraph.ttl" -OutFile "schemas/HeritageGraph.ttl"
Invoke-WebRequest -Uri "$baseUrl/HeritageGraph.shacl.ttl" -OutFile "schemas/HeritageGraph.shacl.ttl"
Copy-Item "schemas/HeritageGraph.shacl.ttl" -Destination "skills/04_heritage-shacl-validate/assets/shapes/HeritageGraph.shacl.ttl" -Force
```

**Python (Cross-platform)**:
```python
import urllib.request
import shutil

ref = "main"
base_url = f"https://raw.githubusercontent.com/CAIRNepal/heritagegraphontology/{ref}/ontology"

for filename in ["HeritageGraph.yaml", "HeritageGraph.ttl", "HeritageGraph.shacl.ttl"]:
    urllib.request.urlretrieve(f"{base_url}/{filename}", f"schemas/{filename}")

shutil.copy("schemas/HeritageGraph.shacl.ttl", "skills/04_heritage-shacl-validate/assets/shapes/HeritageGraph.shacl.ttl")
```

---

## Local Usage in Pipeline
- **Validation Stage ([skills/04_heritage-shacl-validate](file:///c:/Users/nabin/Desktop/myall/hg-skill/skills/04_heritage-shacl-validate))**: Uses `schemas/HeritageGraph.shacl.ttl`.
- **Mapping Stage ([skills/03_heritage-rdf-mapper](file:///c:/Users/nabin/Desktop/myall/hg-skill/skills/03_heritage-rdf-mapper))**: Uses predicates and classes derived from `schemas/HeritageGraph.yaml` and `schemas/HeritageGraph.ttl`.
