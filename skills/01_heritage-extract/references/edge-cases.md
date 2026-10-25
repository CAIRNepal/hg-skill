# Extraction edge cases

## Lots and sets
A line like "pair of brass lamps, 18th c." is one record with `object_type` "pair of brass lamps". Do not split it unless the source lists the parts separately with their own identifiers.

## Attribution language
Map the source's wording into `creators[].role` verbatim: "attributed to", "workshop of", "after", "circle of". Do not collapse them to "creator"; the distinction decides how the mapper types the relationship.

## Uncertain readings
If OCR or a transcription marks a word uncertain (`[?]`, `...`), keep the marker in the label and mention the record in your report. Do not resolve the doubt yourself.

## Conflicting data in one source
When two fields disagree (a catalogue date and a note date), keep the primary field in the record and put the other in `description`. Mention the conflict in the report.

## CSV and JSON exports
Respect column meaning from headers, but check a few rows. Columns named "creator" sometimes hold donors, and "date" is often an acquisition date, not a production date. Put acquisition and donor information under `provenance`.

## Person versus group
"Newar craftsmen of Patan" is `kind: group`, not `person`. Kind matters for stage 2 because it picks which vocabulary or gazetteer to query.
