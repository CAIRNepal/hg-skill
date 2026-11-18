# HeritageGraph URI Policy & Minting Rules

This document records the official URI minting, transliteration, and deduplication policy for the HeritageGraph knowledge platform.

## Core Mandate: Reuse Before Mint

The #1 contributor failure mode is minting a duplicate URI (such as `heritageGraph:struct-nyatapola-bkt`) when the entity is already cataloged in the knowledge graph.

Before creating any new URI, the pipeline and contributors MUST:
1. Check the local `pyoxigraph` mirror snapshot for an existing URI.
2. If the entity is cataloged under a canonical URI, **reuse that URI directly** as the RDF subject.
3. If near-matches or ambiguous candidates exist, route them to the human-in-the-loop (HITL) review queue.
4. Mint a new URI **only** after confirming that the entity represents an uncataloged individual.

## Namespace Architecture

- Canonical Base URI: `https://cair-nepal.org/heritagegraph/`
- Prefix: `heritageGraph:` or `hg:`

### URI Schema

When an entity is novel and must be locally minted:

```
https://cair-nepal.org/heritagegraph/<kind>/<slug>
```

Where `<kind>` is one of:
- `structure`: Monuments, temples, stupas, chaityas, resthouses, dhungedharas.
- `object`: Sculptures, paubhas, manuscripts, ritual objects.
- `place`: Settlements, cities, toles, administrative wards.
- `person`: Historical artisans, sculptors, patrons, donors.
- `group`: Guthis, lineages, caste organizations.
- `event`: Historical, ritual, or festival occurrences.
- `concept`: Iconographic types, theological concepts.

## Transliteration & Slug Rules

1. **Normalization**: Slugs are normalized using Unicode NFC decomposition.
2. **Diacritics**: Diacritical marks (macrons, dots) are folded into ASCII equivalents (e.g., *Nyātāpola* → `nyatapola`).
3. **Word Separators**: Spaces and underscores are replaced with hyphens (`-`). Consecutive hyphens are collapsed.
4. **Devanagari Transliteration**: When names are in Devanagari script, standard IAST Romanization or official English municipal spelling is used for the slug, while original Devanagari is preserved in `rdfs:label` or `heritageGraph:name`.
5. **Stability**: Slugs must be immutable once published. Never alter a slug across releases even if additional details are discovered; use `skos:altLabel` or redirect aliases instead.
