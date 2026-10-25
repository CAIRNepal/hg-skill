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
