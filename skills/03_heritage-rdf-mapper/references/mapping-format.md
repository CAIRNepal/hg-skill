# Mapping YAML format

```yaml
name: cidoc-crm
prefixes:            # prefix -> namespace URI, bound in the output
  crm: http://www.cidoc-crm.org/cidoc-crm/
object:
  class: crm:E22_Human_Made_Object
  uri: "object/{id}"             # appended to --base
rules:
  - field: title                 # path in the record (dots for nesting)
    steps:                       # a chain of triples from the subject
      - {p: crm:P1_is_identified_by, node: appellation, class: crm:E41_Appellation}
      - {p: crm:P190_has_symbolic_content, literal: true}
```

## Keys

- `field`: record path. For lists the rule runs once per item. Missing or null fields are skipped.
- `steps`: ordered chain. Each step creates (or reuses) a node and links it from the previous one.
  - `p`: predicate (prefixed).
  - `class`: type of the node created.
  - `literal: true`: the last step's object is the field's value as a literal.
  - `entity: true`: the last step's object is the entity's URI from its `resolution` (or a minted local one).
  - `node`: a name used for the minted blank/local node, so repeated steps share it (for example one `E12_Production` shared by creator, date and place).
- `datatype`: optional XSD datatype for literals (`xsd:date`, `xsd:gYear`).

## Sharing nodes

Rules that start with the same first-step `node` name within one record reuse that node. This is how creator, date and place all attach to a single production event.

## Safe changes

Adding rules is safe. Changing a `class` or `p` affects the shapes in `../../04_heritage-shacl-validate/assets/shapes/`, so update both and rerun the validation step on your generated `graph.ttl`.

## Container mappings (HeritageGraph-native)

`heritagegraph.yaml` is **generated** by `scripts/generate_mapping.py` from `schemas/HeritageGraph.yaml`; do not edit it. It walks the LinkML Container instead of flat records:

```yaml
name: heritagegraph
generated_from: {schema_version: 1.0.1, sha256: <schema checksum>}
prefixes: {heritageGraph: https://cair-nepal.org/heritagegraph/, crm: ..., ...}
container:
  collections:
    structures:                              # Container slot name
      class: heritageGraph:ArchitecturalStructure   # the schema's class_uri
      slots:
        name: {p: rdfs:label}                       # plain xsd:string literal
        generated_at_time: {p: prov:generatedAtTime, datatype: xsd:dateTime}
        managed_by_guthi: {p: heritageGraph:managedByGuthi, ref: true}   # IRI of another entity id
        existence_status: {p: heritageGraph:existenceStatus, enum: heritageGraph:ExistenceStatus}
```

- Every item's `id` (CURIE or IRI) is its subject URI. `id` itself maps to `dcterms:identifier` (`xsd:anyURI`).
- `ref: true` links to the referenced id (a string or an inlined object's `id`).
- `enum: X` emits the IRI `X#<value>`.
- Items with a Stage 2 `resolution` also get `skos:exactMatch` (linked) or an `rdfs:comment` review flag (ambiguous).
- Fields with no slot rule are reported in `unmapped_fields` as `collection.field`.

### Overrides

`assets/mappings/heritagegraph.overrides.yaml` layers hand-written exceptions on the generated output:

```yaml
collections:
  structures:
    class: heritageGraph:ArchitecturalStructure   # optional class replacement
    slots:
      note: {p: rdfs:comment}                     # replace a rule
      was_influenced_by: null                     # suppress a rule
```

Re-run `generate_mapping.py` after editing. `generate_mapping.py --check` exits 1 when the committed mapping no longer matches the schema and overrides.
