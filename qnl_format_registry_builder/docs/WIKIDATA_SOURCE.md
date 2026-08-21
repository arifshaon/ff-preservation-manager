# Wikidata file-format source

Status: **production-ready through the controlled Wikidata evidence/relationship refresh workflow** as of 2026-08-21.

Wikidata is used by the QNL registry as a source-native technical/context source and as a cross-registry linking source. It is **not** a canonical identity authority and is **not** a preservation-risk authority.

The supported production model is:

```text
Wikidata QID
    -> evidence-only source record
    -> semantic classification/context/technical evidence
    -> copied PRONOM / LOC / NARA identifiers (unverified)
    -> governed source_relationship_claim(s) to existing canonicals
```

For the complete production decision record, baseline counts and operational workflow, see [`WIKIDATA_PRODUCTION_INTEGRATION.md`](WIKIDATA_PRODUCTION_INTEGRATION.md).

## Adapters and responsibility boundary

Two adapter types deliberately have different responsibilities.

### `wikidata_sparql`

This is the low-level acquisition/review adapter. It downloads file-format metadata from the Wikidata Query Service, stores immutable content-addressed snapshots and produces the merged review CSV. Its `extract()` method intentionally returns no `RawFormatRecord` objects.

Use it for acquisition diagnostics, population-policy comparison and source review.

### `wikidata_sparql_evidence`

This is the production extraction adapter. It inherits the same frozen acquisition behavior, then projects the acquired CSV into source-native `RawFormatRecord` objects with a hard identity boundary:

```text
record_role = evidence_only
identity_projection = false
identifier_promotion = false
```

The semantic Wikidata role is retained independently, for example `format`, `format_family`, `format_subclass`, `container`, `codec_or_encoding`, `authority_linked_unclassified` or `other_format_concept`.

A QID is a verified **Wikidata source identity**. PRONOM, LOC and NARA identifiers copied from Wikidata remain unverified assertions and are never promoted to authority-owned canonical identifiers.

## Frozen production safety contract

Wikidata must never, by itself:

- create a canonical format;
- merge canonical formats;
- promote a copied PRONOM/LOC/NARA identifier to verified identity;
- use a label as canonical identity;
- generate preservation-risk assessments;
- generate criterion claims;
- assume one QID corresponds to one external authority identity.

A broad Wikidata concept may legitimately carry several external authority identifiers. Such a QID can therefore relate to several existing canonicals. Those links are preserved as source context, not collapsed into identity equivalence.

## Why population policy is explicit

The original unrestricted transitive discovery route:

```text
P31/P279* -> Q235557
```

produced 85,269 QIDs and pulled in large unrelated ontology branches such as Wikimedia modules, templates and map-data modules.

The production acquisition policy is explicit, versioned and evidence-gated. `P279` is still harvested as source context but never determines population membership transitively.

Current population policy:

```text
2026-08-20-v3
```

## Policy v3 population union

The current population is the union of:

1. direct instances of **file format** (`P31 = Q235557`);
2. direct instances of **file format family** (`P31 = Q26085352`);
3. direct instances of reviewed specialist file-format classes;
4. evidence-bearing instances of **XML-based format**;
5. evidence-bearing instances of a reviewed set of specific format-parent concepts;
6. evidence-bearing instances of reviewed contextual format classes such as video compression format;
7. evidence-bearing instances of **open file format**, excluding known protocol/standard co-classifications;
8. any item carrying a PRONOM file-format ID (`P2748`);
9. any item carrying a Library of Congress FDD ID (`P3266`);
10. any item carrying a NARA File Format Preservation Plan ID (`P11167`).

The authority-linked routes remain independent of Wikidata classification.

## Reviewed specialist file-format classes

The direct `P31` specialist classes approved for population discovery are:

- image file format (`Q1572121`);
- archive file format (`Q1351368`);
- document file format (`Q336705`);
- disk image format (`Q138827382`);
- raw image format (`Q654383`);
- raster-graphics file format (`Q105599390`);
- font file format (`Q55281818`);
- music file format (`Q1955133`);
- digital container format (`Q167772`);
- patch format (`Q115729440`);
- audio file format (`Q682626`);
- video file format (`Q18359031`);
- vector graphics file format (`Q105599400`);
- package format (`Q2026749`);
- executable file format (`Q17560478`);
- chemical file format (`Q5090461`);
- GIS project file (`Q133897645`);
- e-book file format (`Q81986407`);
- exe-extension-associated executable file format (`Q17560541`).

A record may carry additional `P31` values. They remain source-native context and do not erase approved population evidence.

## Evidence-gated routes

Conditional routes require at least one of:

- PRONOM ID (`P2748`);
- LOC FDD ID (`P3266`);
- NARA format-plan ID (`P11167`);
- file extension (`P1195`);
- MIME type (`P1163`);
- file-format identification pattern (`P4152`).

### XML-based format

`XML-based format` (`Q20155966`) remains conditional rather than an unconditional allowlist class.

### Reviewed format parents

Some preservation-relevant versions/variants are modeled as direct instances of a particular parent rather than a reusable format class. The following parents are acquisition selectors only; they are not promoted to general canonical format classes:

- Renoise Song (`Q2597575`);
- Parchive (`Q497118`);
- Microsoft Word Binary File Format (`Q28858032`);
- Excel Binary File Format (`Q3502441`);
- Small Web Format family (`Q594447`);
- PDF/VT (`Q125650`);
- Softdisk Family Tree (`Q34739013`);
- STATISTICA (`Q34746188`);
- git packfile index (`Q53756508`);
- Python bytecode (`Q28009469`);
- WebP Extended (`Q45989477`).

### Context classes

`video compression format` (`Q7927899`) is acquired conditionally as preservation context. Its records can be classified semantically as `codec_or_encoding` but remain evidence-only for canonical identity purposes.

### Open file format

`open file format` (`Q1056408`) is evidence-gated and excludes records also classified as:

- domain application protocol (`Q16937237`);
- de facto standard (`Q385853`).

## Deliberate exclusions

Policy v3 does not try mechanically to recover every record reached by the former transitive crawl. Concepts deliberately left outside the acquisition boundary include protocol/language/pathological-file cases such as oEmbed in protocol classifications, Biological Expression Language, 42.zip, HTTP Cache, and broad programming-language/protocol/standard classes.

The goal is a defensible and reproducible preservation-format population, not reproduction of accidental ontology reachability.

## Policy validation history

The broad acquisition contained **85,269** QIDs.

Policy v1 reduced that population to **15,233** and retained 391 of a reviewed 595-record useful non-direct diagnostic set.

Policy v2 increased the population to **15,421** and retained 539 / 595 useful non-direct records.

Policy v3 added the reviewed parent/context routes and produced the approved production population of **15,479** QIDs. It retained 590 / 595 useful non-direct records while reducing the broad population by about 81.9%. The remaining five reviewed cases were intentionally excluded rather than forced into scope.

## Acquisition reproducibility

The query-set hash includes:

- every population-query template;
- population-policy version;
- reviewed specialist-class QIDs;
- conditional XML class;
- reviewed format-parent QIDs;
- contextual class QIDs;
- open-format class and exclusions;
- property-batch query templates;
- output columns.

Population discovery and property harvesting are separate. QIDs are deduplicated and frozen for one acquisition session. Population queries use keyset pagination by entity URI; property queries use bounded `VALUES ?format { ... }` batches over the frozen population.

An interrupted acquisition records its session under:

```text
work/snapshots/wikidata_file_formats/.wikidata_acquisition_session.json
```

Completed batches are cached individually so rerunning can resume without repeating population discovery or completed property requests. Use `--restart` only when a deliberately fresh population discovery is required.

## Acquired fields

The merged CSV contains one row per QID and can include:

- English label, description and aliases;
- direct instance-of and subclass-of context;
- PRONOM file format ID (`P2748`);
- LOC FDD ID (`P3266`);
- NARA format-plan ID (`P11167`);
- extension (`P1195`);
- MIME type (`P1163`);
- version (`P348`);
- identification pattern (`P4152`);
- developer (`P178`);
- publication and inception dates (`P577`, `P571`);
- part-of, based-on, replaces/replaced-by and described-by relationships;
- official website (`P856`).

Multi-valued properties are pipe-delimited. Paired relationship QIDs and labels remain aligned.

## Standalone acquisition/review command

From `qnl_format_registry_builder`:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --workdir work
```

Useful controls include:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --workdir work `
  --batch-size 200 `
  --population-page-size 500 `
  --transport-retries 5
```

Offline replay after a completed acquisition:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --workdir work `
  --offline
```

## Controlled production refresh

Do **not** add `wikidata_sparql_evidence` to the ordinary `sources.qnl.json` source loop. Wikidata source refresh and governed relationship replacement are one coordinated transaction boundary.

Run a no-write preflight first:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --out out/wikidata-refresh-preflight.json
```

For the cached current snapshot:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --offline `
  --out out/wikidata-refresh-preflight-offline.json
```

Only when the preflight returns:

```text
status = ready
gate_passed = true
```

may the reviewed refresh be applied:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --apply `
  --out out/wikidata-refresh-production.json
```

The apply phase persists the new evidence-only source records, supersedes obsolete Wikidata relationship claims, materializes the current relationship set onto existing canonicals, preserves snapshot provenance and independently verifies the resulting persistent state.

A successful refresh must finish with:

```text
status = completed
verification.status = ok
```

## Production drift gates

The refresh does not freeze the 2026-08-21 counts forever. Future Wikidata changes are permitted within controlled review thresholds.

Current production review gates block a refresh when:

- population change exceeds 2,000 records or 10%;
- relationship-edge change exceeds 1,000 edges or 20%;
- claim turnover exceeds 750 additions/removals or 25%;
- any copied PRONOM/LOC/NARA identifier becomes unresolved;
- any canonical creation/merge or copied-identifier promotion signal appears;
- the current persisted Wikidata baseline fails independent verification.

A blocked refresh requires review; it must not be blindly rerun with relaxed thresholds.

## Verified production baseline

First production backfill run:

```text
relationship-backfill-20260821T190919Z
```

Input SHA-256:

```text
a6c1e598b567dd89557a67f186e99bf8486cddf40615384bbe998e450a1810df
```

Verified baseline:

- 3,372 current canonical formats;
- 15,479 Wikidata evidence-only source records;
- 2,519 QIDs with governed canonical relationships;
- 2,793 canonicals with Wikidata relationships;
- 2,856 governed relationship edges;
- 3,266 matched copied authority claims: 2,337 PUID, 295 LOC, 634 NARA;
- zero unmatched authority claims;
- zero promoted Wikidata strong identifiers;
- zero Wikidata risk assessments.

Relationship outcomes:

- single-target cross-reference: 2,240 QIDs;
- multi-target context: 279 QIDs;
- no authority cross-reference: 12,960 QIDs.

## Verified changed-source simulation

Production refresh behavior was also validated against the real persisted registry with a deterministic read-only changed-source simulation.

The simulation cloned the cached 15,479-row snapshot, selected `Q2078` (one current governed edge and one copied authority identifier), and removed LOC `fdd000020` from the temporary CSV only.

Expected and observed changes were exact:

- population: 15,479 -> 15,479;
- relationship edges: 2,856 -> 2,855;
- linked QIDs: 2,519 -> 2,518;
- matched authority claims: 3,266 -> 3,265;
- LOC matches: 295 -> 294;
- single-target relationships: 2,240 -> 2,239;
- no-authority QIDs: 12,960 -> 12,961;
- canonical formats: 3,372 -> 3,372;
- canonical creation/merges/promotions: 0;
- registry writes: 0;
- persistent registry fingerprint unchanged: true.

The simulation command is intentionally preflight-only and exposes no apply mode:

```powershell
python -m registry_builder.wikidata_refresh_simulation `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --out-csv out/wikidata-refresh-simulated-change.csv `
  --out out/wikidata-refresh-simulation.json
```

## Relationship persistence and rebuild survival

Canonical attachments are stored in the governed `source_relationship_claims` collection. Claim identity includes the semantic relationship payload, so changed source assertions create a new claim while obsolete claims are explicitly superseded.

Current relationship claims are replayed after normal reconciliation. Therefore an unrelated source rebuild cannot strip Wikidata links from canonical documents. Relationship replay never creates a missing canonical; orphan claims are reported instead.

## Recovery and independent verification

The one-time/recovery relationship backfill remains available:

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

The verifier checks current source-record roles, projection versions, relationship counts/materialization, canonical count, copied-identifier promotion and Wikidata risk contribution. A production Wikidata layer is accepted only when the verifier returns `status: ok`.
