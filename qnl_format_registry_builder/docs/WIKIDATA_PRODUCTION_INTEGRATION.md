# Wikidata production integration

Status: production evidence/relationship model approved and first backfill verified on 2026-08-21.

## Frozen production contract

Wikidata is a source-native evidence and cross-registry context source. It is **not** a canonical identity authority and is **not** a risk authority.

The production model is:

```text
Wikidata QID
    -> evidence-only source record
    -> semantic classification/context/technical evidence
    -> copied PRONOM / LOC / NARA identifiers (unverified)
    -> governed source_relationship_claim(s) to existing canonicals
```

Wikidata must never, by itself:

- create a canonical format;
- merge canonical formats;
- promote a copied PRONOM/LOC/NARA identifier to verified identity;
- generate risk assessments;
- generate criterion claims;
- use labels as canonical identity;
- assume one QID equals one external authority identity.

A single QID may legitimately relate to several current canonicals. Multi-target relationships are preserved as context rather than collapsed into identity equivalence.

## Production population and relationship baseline

Frozen population policy: `2026-08-20-v3`.

Verified first production backfill:

- current canonical formats: **3,372**;
- Wikidata source records: **15,479**;
- evidence-only Wikidata source records: **15,479**;
- QIDs with governed canonical relationships: **2,519**;
- canonical formats with Wikidata relationships: **2,793**;
- relationship edges: **2,856**;
- copied authority claims resolved: **3,266**;
  - PRONOM/PUID: 2,337;
  - LOC FDD: 295;
  - NARA: 634;
- unmatched copied authority claims: **0**;
- promoted Wikidata strong identifier claims: **0**;
- Wikidata source records with risk assessments: **0**.

Relationship outcomes at the approved baseline:

- single-target cross-reference: 2,240 QIDs;
- multi-target context: 279 QIDs;
- no authority cross-reference: 12,960 QIDs.

## Projection versions

Evidence-only projection:

```text
2026-08-21-v2-evidence-only
```

Governed authority cross-reference projection:

```text
2026-08-21-v1-authority-cross-reference
```

## Adapters

`wikidata_sparql` remains the low-level acquisition/review adapter. It implements the frozen policy-v3 population, resumable staged acquisition, VALUES batching and offline replay.

`wikidata_sparql_evidence` is the production extraction adapter. It inherits the acquisition behavior unchanged, then projects every acquired QID into a `RawFormatRecord` with:

```text
record_role = evidence_only
identity_projection = false
identifier_promotion = false
```

The semantic `wikidata_role` is retained independently, for example `format`, `format_family`, `format_subclass`, `container`, `codec_or_encoding` or `authority_linked_unclassified`.

The QID remains a verified Wikidata source identity. Copied PUID/LOC/NARA values remain unverified assertions.

## Governed relationship persistence

Canonical attachments are stored separately in:

```text
source_relationship_claims
```

Claims are versioned by their semantic payload. On a reviewed Wikidata relationship refresh, relationships absent from the new projection are superseded rather than silently retained as current.

Current relationship claims are replayed after normal reconciliation so unrelated source refreshes cannot strip the governed Wikidata links from rebuilt canonical documents.

Relationship replay never creates missing canonicals. Orphan relationship claims are reported instead.

## First production write

The first production backfill completed under run:

```text
relationship-backfill-20260821T190919Z
```

Input SHA-256:

```text
a6c1e598b567dd89557a67f186e99bf8486cddf40615384bbe998e450a1810df
```

The independent verifier returned `status: ok` with no errors and confirmed:

- 3,372 current canonicals;
- 15,479 latest Wikidata evidence-only source records;
- 2,856 current Wikidata relationship claims;
- 2,856 materialized relationship edges;
- 2,793 materialized canonical formats;
- zero promoted Wikidata strong identifiers;
- zero Wikidata risk assessments.

## Current operational boundary

Do not enable `wikidata_sparql_evidence` in the general production source configuration until the refresh workflow is finalized.

A fresh Wikidata acquisition can change copied authority identifiers. The governed relationship layer must therefore be recomputed and replace the previous current Wikidata relationship claims as part of the same operational refresh procedure. Until that workflow is wired as one controlled operation, use the reviewed backfill/verification path.

Production backfill:

```powershell
python -m registry_builder.wikidata_relationship_backfill `
  --config config/wikidata_relationship_backfill.production.json `
  --out out/wikidata-relationship-backfill-production.json
```

Independent verification:

```powershell
python -m registry_builder.wikidata_relationship_verify `
  --config config/wikidata_relationship_backfill.production.json `
  --out out/wikidata-relationship-verify.json
```

The production verifier must return `status: ok` before the refreshed Wikidata relationship layer is accepted.
