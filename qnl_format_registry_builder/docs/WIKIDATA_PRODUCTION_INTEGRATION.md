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

## Controlled refresh workflow

Wikidata refresh is an explicit governed operation, not part of every normal registry build. The production command is:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --out out/wikidata-refresh-preflight.json
```

Without `--apply`, the command acquires (or with `--offline`, replays) the policy-v3 snapshot and performs a **no-write preflight**. It:

1. requires the current persisted Wikidata layer to pass the independent verifier;
2. extracts every acquired QID through `wikidata_sparql_evidence`;
3. confirms every record remains `evidence_only` and carries no risk assessment;
4. recomputes all copied PRONOM/LOC/NARA authority relationships against the current canonical registry;
5. calculates relationship additions, removals and unchanged claims by semantic claim ID;
6. blocks unresolved copied authority identifiers;
7. blocks any identity creation, identity merge or identifier-promotion signal;
8. applies configured population, relationship-edge and claim-turnover drift gates.

The production drift thresholds are intentionally review gates rather than permanent expected counts. A future valid Wikidata update may change the 15,479-record or 2,856-edge baseline, but a large change must be reviewed rather than silently accepted.

When the preflight returns:

```text
status = ready
gate_passed = true
```

apply the same controlled workflow with:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --apply `
  --out out/wikidata-refresh-production.json
```

The apply phase uses the reviewed preflight invariants to:

1. persist the new evidence-only source records;
2. supersede relationship claims no longer present;
3. persist the new current relationship claim set;
4. rematerialize current relationships onto existing canonicals;
5. preserve the acquired source snapshot provenance;
6. independently verify the resulting persistent registry state.

A successful applied refresh must finish with:

```text
status = completed
verification.status = ok
```

If the command returns `blocked`, `write_failed` or `verification_failed`, do not rerun it blindly. Inspect the reported gate or verification errors first.

### Offline preflight

To test the currently cached acquisition without contacting Wikidata or writing the registry:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --offline `
  --out out/wikidata-refresh-preflight-offline.json
```

### Deliberately restarting acquisition

An interrupted staged acquisition resumes its frozen population and cached batches. Use `--restart` only when a deliberately fresh population discovery is required:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --restart `
  --out out/wikidata-refresh-preflight.json
```

A restarted acquisition is still preflight-only unless `--apply` is also supplied.

## General pipeline boundary

Do not add `wikidata_sparql_evidence` to the ordinary `sources.qnl.json` source loop. Wikidata acquisition and governed relationship replacement must remain one coordinated refresh transaction boundary.

The evidence-only Wikidata source records already persisted by the verified backfill remain available to incremental registry rebuilding, and current `source_relationship_claims` are replayed after normal reconciliation. Therefore ordinary source refreshes can preserve the current Wikidata evidence layer without triggering a new WDQS acquisition.

Use `wikidata_refresh` when the Wikidata source itself is intentionally refreshed.

## Legacy backfill and independent verification

The one-time/recovery backfill remains available:

```powershell
python -m registry_builder.wikidata_relationship_backfill `
  --config config/wikidata_relationship_backfill.production.json `
  --out out/wikidata-relationship-backfill-production.json
```

Independent verification remains available separately:

```powershell
python -m registry_builder.wikidata_relationship_verify `
  --config config/wikidata_relationship_backfill.production.json `
  --out out/wikidata-relationship-verify.json
```

The standalone verifier must return `status: ok` before a refreshed Wikidata relationship layer is accepted.
