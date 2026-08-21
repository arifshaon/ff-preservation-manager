# Wikidata production integration

Status: **production-ready under the controlled evidence/relationship refresh workflow** as of 2026-08-21.

The production evidence model, governed relationship persistence, rebuild survival, independent verifier, drift-gated refresh path and deterministic changed-source simulation have all been validated against the current production registry.

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

`wikidata_sparql` remains the low-level acquisition/review adapter. It implements the frozen policy-v3 population, resumable staged acquisition, VALUES batching and offline replay. Its extraction boundary remains disabled so it cannot accidentally participate in normal reconciliation.

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

Wikidata refresh is an explicit governed operation, not part of every normal registry build.

### 1. Preflight

Run without `--apply`:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --out out/wikidata-refresh-preflight.json
```

Or replay the cached acquisition without contacting Wikidata:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --offline `
  --out out/wikidata-refresh-preflight-offline.json
```

The preflight:

1. requires the current persisted Wikidata layer to pass the independent verifier;
2. extracts every acquired QID through `wikidata_sparql_evidence`;
3. confirms every record remains `evidence_only` and carries no risk assessment;
4. recomputes copied PRONOM/LOC/NARA relationships against the current canonical registry;
5. calculates relationship additions, removals and unchanged claims by semantic claim ID;
6. blocks unresolved copied authority identifiers;
7. blocks any identity creation, identity merge or identifier-promotion signal;
8. applies configured population, relationship-edge and claim-turnover drift gates.

Proceed only when:

```text
status = ready
gate_passed = true
```

### 2. Apply

After review of a ready preflight:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --apply `
  --out out/wikidata-refresh-production.json
```

The apply phase:

1. persists the new evidence-only source records;
2. supersedes relationship claims no longer present;
3. persists the new current relationship claim set;
4. rematerializes current relationships onto existing canonicals;
5. preserves the acquired source snapshot provenance;
6. independently verifies the resulting persistent registry state.

Success requires:

```text
status = completed
verification.status = ok
```

If the command returns `blocked`, `write_failed` or `verification_failed`, do not rerun it blindly. Inspect the reported gate or verification errors first.

## Production drift gates

The approved 2026-08-21 counts are a verified baseline, not permanent expected counts. Future legitimate Wikidata changes are allowed within controlled thresholds.

Current review gates are:

- population change: maximum 2,000 records and 10%;
- relationship-edge change: maximum 1,000 edges and 20%;
- relationship claim turnover: maximum 750 additions/removals and 25%;
- unresolved copied authority identifiers: maximum 0.

The refresh is also blocked if the persisted baseline is not independently verifiable or if any canonical creation, merge, copied-identifier promotion, risk-generation or criterion-generation signal is observed.

## Verified no-change preflight

The production offline preflight was run against the same cached source snapshot used for the first production backfill.

Observed:

```text
status: ready
gate_passed: true
population drift: 0
relationship-edge drift: 0
claim turnover: 0
unmatched authority claims: 0
```

The source SHA-256 remained:

```text
a6c1e598b567dd89557a67f186e99bf8486cddf40615384bbe998e450a1810df
```

This proved the refresh workflow recognizes a no-change acquisition without performing a production write.

## Verified changed-source simulation

A deterministic read-only simulation was then run against the **real current production registry**.

The simulation command has no apply mode. It fingerprints the relevant registry collections before and after the exercise, clones the cached acquisition to a temporary CSV, mutates exactly one current single-edge QID, and runs the normal refresh preflight against that temporary snapshot.

Simulation mutation:

```text
QID: Q2078
removed field: locFdd
removed identifier: fdd000020
```

The mutation was selected from the 2,240 QIDs with exactly one governed relationship so the expected relationship delta was deterministic.

Expected and observed result:

```text
Wikidata records                 15479 -> 15479
relationship edges               2856 -> 2855
QIDs with relationships           2519 -> 2518
canonicals with relationships     2793 -> 2792
matched authority claims          3266 -> 3265
LOC matched claims                 295 -> 294
single-target QIDs                2240 -> 2239
no-authority QIDs                12960 -> 12961
canonical formats                 3372 -> 3372
```

Safety results:

```text
status: ok
errors: []
gate_passed: true
relationship additions: 0
relationship removals: 1
claim turnover: 1
unmatched authority claims: 0
identity_merges_performed: 0
canonical_formats_created: 0
canonical_identifiers_promoted: 0
registry_writes_performed: 0
registry_fingerprint_unchanged: true
```

This demonstrates that an upstream Wikidata authority-reference removal is detected as a governed evidence/relationship change while canonical identity remains untouched.

The reproducible simulation command is:

```powershell
python -m registry_builder.wikidata_refresh_simulation `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --out-csv out/wikidata-refresh-simulated-change.csv `
  --out out/wikidata-refresh-simulation.json
```

## Test gates completed

The implemented production path has passed focused suites covering:

- acquisition population policy and resumable VALUES batching;
- production evidence-only extraction;
- inability of Wikidata evidence rows to create/merge canonical identity;
- relationship preview semantics and multi-target context;
- governed relationship persistence;
- supersession of obsolete claims;
- materialization idempotence and orphan handling;
- rebuild survival through unrelated source refreshes;
- independent production verification;
- no-change refresh preflight;
- changed relationship refresh/apply behavior;
- excessive-drift blocking before writes;
- deterministic changed-source simulation with registry fingerprint protection.

The final focused refresh/simulation suite passed 5/5 tests, after the broader integration suites passed 11/11, 28/28 and 20/20 at their respective gates.

## General pipeline boundary

Do not add `wikidata_sparql_evidence` to the ordinary `sources.qnl.json` source loop.

Wikidata acquisition and governed relationship replacement must remain one coordinated refresh transaction boundary. The evidence-only Wikidata source records already persisted by the verified backfill remain available to incremental registry rebuilding, and current `source_relationship_claims` are replayed after normal reconciliation.

Therefore ordinary source refreshes preserve the current Wikidata evidence layer without triggering a new WDQS acquisition. Use `wikidata_refresh` only when the Wikidata source itself is intentionally refreshed.

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

## Production decision

The Wikidata implementation is now considered complete for the current registry architecture:

```text
acquisition            production-ready
source projection      production-ready (evidence-only)
relationship mapping   production-ready
claim persistence      production-ready
claim supersession     production-ready
rebuild survival       production-ready
refresh drift gates    production-ready
independent verifier   production-ready
changed-source test    production-ready
canonical identity     deliberately NOT owned by Wikidata
risk assessment        deliberately NOT supplied by Wikidata
```

Future work should be driven by an actual source-policy change, new authority namespace, observed drift, or a concrete operational requirement rather than by further expansion of the Wikidata identity model.
