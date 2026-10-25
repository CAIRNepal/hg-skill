# SHACL notes

## Reading a violation
- `focusNode`: the resource that broke the rule.
- `resultPath`: the property involved.
- `sourceConstraintComponent`: which kind of rule (`MinCountConstraintComponent` means a required property is missing, `ClassConstraintComponent` means the value has the wrong type, `PatternConstraintComponent` means a string/date format problem).
- `resultMessage`: the author's message from the shape. Write shape messages for humans.

## Writing a new shape
1. Target a class: `sh:targetClass crm:E22_Human_Made_Object`.
2. Add one `sh:property` per requirement with a `sh:message`.
3. Test it against both a compliant sample graph (must pass) and a deliberately invalid graph (must fail with expected violation message).

## Common patterns
- Required: `sh:minCount 1`.
- Value is a particular class: `sh:class crm:E39_Actor`.
- Forbidden property on a class: `sh:path crm:P14_carried_out_by ; sh:maxCount 0`.
- Date format: `sh:datatype xsd:date` or `sh:pattern`.

## Inference
The script validates with `inference=none`. Shapes therefore assert explicit types. If a mapping relies on subclass reasoning, state the subclass types explicitly in the mapping.
