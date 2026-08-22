# Wikidata

## What it is

Wikidata is a collaborative structured knowledge base. This project uses Wikidata only for controlled contextual/cross-registry evidence around file formats.

Official query service:

```text
Human query interface:
https://query.wikidata.org

SPARQL endpoint:
https://query.wikidata.org/sparql

Wikidata query-service documentation:
https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service
```

Wikidata itself warns that WDQS is not suitable for very large uncontrolled extractions; use query design/population controls rather than a broad unbounded crawl.

## Why this source is special

An earlier broad transitive taxonomy query reached many classes that were technically connected through Wikidata's ontology but were not meaningful preservation file formats. The production integration therefore uses a frozen/reviewed population policy and drift-gated refresh.

Wikidata is **not** part of the ordinary `sources.qnl.json` selected-source refresh loop.

## Production role

Wikidata is:

```text
source-native context
+ verified QID source identity
+ semantic classification
+ copied authority cross-references
+ governed relationships to existing canonicals
```

Wikidata must not, by itself:

- create a canonical format;
- merge canonical formats;
- promote copied PRONOM/LOC/NARA identifiers to verified authority identifiers;
- generate preservation-risk assessments;
- generate criterion claims;
- use labels as canonical identity.

Copied PUID/LOC/NARA identifiers are cross-reference assertions and are resolved only against existing authority-backed canonicals.

## Current controlled source configuration

```text
qnl_format_registry_builder/config/wikidata_refresh.production.json
```

Core source settings:

```json
{
  "id": "wikidata_file_formats",
  "type": "wikidata_sparql_evidence",
  "batch_size": 200,
  "population_page_size": 500,
  "retries": 5,
  "timeout_seconds": 90
}
```

The current frozen population policy is documented in the production integration reference.

## Current data model

Acquired records are projected as:

```text
record_role = evidence_only
identity_projection = false
identifier_promotion = false
```

Governed links to current canonicals are stored separately in:

```text
source_relationship_claims
```

This lets contextual relationships survive registry rebuilds without turning Wikidata into an identity authority.

## Refresh: preflight first

From `qnl_format_registry_builder`:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config\wikidata_refresh.production.json `
  --workdir work `
  --out out\wikidata-refresh-preflight.json
```

Offline replay:

```powershell
python -m registry_builder.wikidata_refresh `
  --config config\wikidata_refresh.production.json `
  --workdir work `
  --offline `
  --out out\wikidata-refresh-preflight-offline.json
```

Proceed only when the preflight reports the configured gates are satisfied, including:

```text
status = ready
gate_passed = true
```

## Apply only after review

```powershell
python -m registry_builder.wikidata_refresh `
  --config config\wikidata_refresh.production.json `
  --workdir work `
  --apply `
  --out out\wikidata-refresh-production.json
```

Successful apply requires post-write verification.

Do not rerun a blocked or verification-failed refresh blindly; inspect drift/unmatched-identifier/invariant errors.

## Drift gates

The production config limits large unexplained changes in:

- population size;
- relationship-edge count;
- relationship-claim turnover;
- unresolved copied authority identifiers.

It also rejects identity creation/merge/promotion and risk/criterion generation signals from Wikidata.

## What to review after refresh

Check:

- population delta;
- QID additions/removals;
- copied authority claim resolution;
- relationship additions/removals;
- multi-target contextual relationships;
- zero promoted strong identifiers;
- zero Wikidata risk assessments;
- independent verifier status.

## Risk Manager behavior

Wikidata relationships/context may be shown to a human/AI as supporting context where appropriate. They do not create a preservation-risk level.

## Deep reference

The full production contract, baseline, projection versions, drift gates and verification process are maintained in:

[`../../qnl_format_registry_builder/docs/WIKIDATA_PRODUCTION_INTEGRATION.md`](../../qnl_format_registry_builder/docs/WIKIDATA_PRODUCTION_INTEGRATION.md)

Also see:

[`../../qnl_format_registry_builder/docs/WIKIDATA_SOURCE.md`](../../qnl_format_registry_builder/docs/WIKIDATA_SOURCE.md)
