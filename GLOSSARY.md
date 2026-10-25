# HeritageGraph Domain Glossary

Ubiquitous language for the **HeritageGraph** platform and the cultural heritage transformation pipeline.

## Platform & Project Concepts

### HeritageGraph
The CAIR-Nepal open knowledge platform for digitizing, modeling, and preserving cultural heritage data across Nepal and the Himalayan region. Data contributed to HeritageGraph is serialized as validated RDF Turtle (`.ttl`).
- **Namespace**: `heritageGraph:` `<https://cair-nepal.org/heritagegraph/>`
- **Documentation**: [heritagegraphontology](https://cairnepal.github.io/heritagegraphontology/)
- **LinkML Source Schema**: [schemas/HeritageGraph.yaml](schemas/HeritageGraph.yaml)
- **Core Ontology TTL**: [schemas/HeritageGraph.ttl](schemas/HeritageGraph.ttl)
- **Quality Shapes**: [schemas/HeritageGraph.shacl.ttl](schemas/HeritageGraph.shacl.ttl)
- **Upstream Sources**: [schemas/SOURCES.md](schemas/SOURCES.md)

### CulturalHeritageObject
A physical monument, temple, chaitya, sculpture, manuscript, artifact, or historic structure.
- **CIDOC-CRM Mapping**: `crm:E22_Human_Made_Object`
- **HeritageGraph Class**: `heritageGraph:CulturalHeritageObject`

### ProductionEvent
An event representing the creation, carving, casting, founding, or construction of a cultural heritage object or monument.
- **CIDOC-CRM Mapping**: `crm:E12_Production`
- **HeritageGraph Class**: `heritageGraph:ProductionEvent`
- **Standard Predicates**:
  - `crm:P108i_was_produced_by`: links object to production event.
  - `crm:P14_carried_out_by`: links production event to creator actor.
  - `crm:P4_has_time-span`: links event to dating interval.
  - `crm:P7_took_place_at`: links event to location/place.

### Actor
An artisan, sculptor, guild, royal patron, donor, or historical entity responsible for commissioning, creating, or transferring a heritage asset.
- **CIDOC-CRM Mapping**: `crm:E39_Actor`
- **HeritageGraph Classes**: `heritageGraph:Actor`, `heritageGraph:Person`, `heritageGraph:Group`

### Place
A geographical or administrative location (e.g., Patan, Bhaktapur, Kathmandu, specific tole, ward, or complex).
- **CIDOC-CRM Mapping**: `crm:E53_Place`
- **HeritageGraph Class**: `heritageGraph:Place` / `geo:SpatialObject`

### Assertion & Provenance
A structured proposition capturing historical, archaeological, or scholarly consensus alongside its verbatim documentary evidence.
- **Ontology Predicates**: `crminf:J4_that`, `prov:wasDerivedFrom`, `prov:wasAttributedTo`

### Local Minting
Constructing a deterministic fallback URI under the project base (`https://cair-nepal.org/heritagegraph/<kind>/<slug>`) when an entity cannot be confidently matched to an external vocabulary (Getty ULAN, Getty AAT, Wikidata).

### Container
The top-level LinkML `tree_root` class in [schemas/HeritageGraph.yaml](schemas/HeritageGraph.yaml) that anchors intermediate JSON extraction datasets into organized collections (`structures`, `iconographic_objects`, `persons`, `guthis`, `festivals`, `production_events`, `places`).

### Guthi
A traditional Newar socio-religious institution responsible for the governance, ritual maintenance, worship, and physical preservation of monuments and temples in the Kathmandu Valley.
- **HeritageGraph Class**: `heritageGraph:Guthi` (subclass of `heritageGraph:Group` / `crm:E74_Group`)

### Living Heritage
Intangible and active ritual expressions tied to physical structures, including periodic worship (`heritageGraph:RitualEvent`), chariot processions and festivals (`heritageGraph:Festival`), and caste-specific custodial duties.

### Quality Gate (SHACL)
The final validation phase ensuring that generated Turtle files (`graph.ttl`) strictly conform to [HeritageGraph.shacl.ttl](schemas/HeritageGraph.shacl.ttl).
