# Vocabulary notes

## Getty AAT (Art & Architecture Thesaurus)
- Covers materials, techniques, object types, styles and periods.
- URI pattern: `http://vocab.getty.edu/aat/<id>`.
- SPARQL endpoint: `https://vocab.getty.edu/sparql`. Labels are in `skos:prefLabel` / `gvp:prefLabelGVP`.
- Prefer the most specific concept that the source supports ("gilt bronze" over "bronze" only if the source says gilt).

## Getty ULAN (Union List of Artist Names)
- People and corporate bodies who made or commissioned art.
- URI pattern: `http://vocab.getty.edu/ulan/<id>`.
- Entries carry birth/death dates and nationality. Always check them against the object's date before linking.

## Getty TGN (Thesaurus of Geographic Names)
- URI pattern: `http://vocab.getty.edu/tgn/<id>`. Useful for historical place names.

## Wikidata
- URI pattern: `http://www.wikidata.org/entity/Q<id>`.
- Search API: `https://www.wikidata.org/w/api.php?action=wbsearchentities`.
- Broad coverage including South Asian places and people, but quality varies. Check `instance of` against the mention's kind (a "Patan" that is a film is not the city).

## Internal gazetteers
- CSV with columns `uri,label,alt_labels,kind,context`. `alt_labels` is pipe-separated.
- These win over public vocabularies because they encode the institution's own decisions.

## Matching hygiene
- Compare case-insensitively with diacritics folded, but keep the original label in the output.
- For transliterated names (Devanagari to Latin), expect multiple spellings. Match on `alt_labels` before giving up.
- A name match alone is never enough for a person; require a second agreeing signal (dates, place, role).
