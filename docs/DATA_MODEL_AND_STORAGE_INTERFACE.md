# Data storage, query, and adapter interface

This document describes the **persistence/access contract** used across the repository.

For the canonical backend-neutral data model—entities, in-flight types, logical collections including `criterion_claims`, and the evidence-to-risk transformation chain—read first:

**[`DATA_MODEL.md`](DATA_MODEL.md)**

This document answers a different question: **how do modules read, write, query, and swap storage backends without coupling preservation logic to MongoDB?**

MongoDB is one implementation of the storage interface; file and memory stores use the same logical contract, and future backends can implement it as plugins.

## Why this interface exists

The two active modules have different responsibilities but need the same evidence:

```text
qnl_format_registry_builder
  creates / updates registry documents
        |
        v
RegistryStore
        |
        +--> memory
        +--> file / JSON document store
        +--> MongoDB
        +--> future plugin backend
        |
        v
preservation_risk_manager.RegistryReader
  queries canonical formats and evidence
```

This means:

- ingestion code does not need to know which database is used;
- risk-analysis code does not need MongoDB-specific access logic;
- tests can use an in-memory or JSON-backed store;
- a future SQL/search/API-backed implementation can be introduced behind the same application boundary.

## Core storage contract

`registry_builder.storage.base.RegistryStore` defines the common backend interface.

Every full storage backend implements:

```python
def upsert(collection: str, key: str | None, doc: dict) -> str:
    ...

def query(collection: str, filt: dict | None = None) -> list[dict]:
    ...
```

### `upsert`

Creates or replaces one logical document and returns the key used by the backend.

Application code decides:

- which logical collection the document belongs to;
- which fields form a stable key;
- whether previous evidence remains historical or is superseded;
- which validation/provenance rules apply.

The backend must not invent preservation semantics.

### `query`

Returns documents from a logical collection matching the supported filter contract.

The risk manager deliberately consumes a minimal query Protocol instead of importing MongoDB directly.

## Built-in storage adapters

| `type` | Behavior | Intended use |
| --- | --- | --- |
| `memory` | in-memory document collections | unit tests, transient runs, quickstarts |
| `file` | file-backed document store | lightweight persistent/local use |
| `json_file` | alias of file backend | compatibility/config convenience |
| `mongodb` | MongoDB-backed document store | persistent operational registry |

A trusted external backend can be loaded with a plugin path such as:

```json
{
  "storage": {
    "type": "mypkg.storage.sql:SqlRegistryStore"
  }
}
```

The plugin must subclass `RegistryStore`. Importing a plugin executes trusted Python code, so plugin paths must come from reviewed packages/configuration.

## MongoDB example

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry",
    "collection_prefix": "",
    "server_selection_timeout_ms": 5000,
    "ping": true
  },
  "exports": {
    "enabled": false
  }
}
```

The same storage block can be used by the registry builder to write and by the risk manager to create a `RegistryReader`.

For MongoDB-specific collection fields, indexes, key escaping, and verification queries, see:

[`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md)

## Logical collections

The canonical list and semantics live in [`DATA_MODEL.md`](DATA_MODEL.md). Current logical collection names include:

```text
runs
source_snapshots
source_records
canonical_formats
format_identifiers
institution_policy_overlays
format_evidence_claims
criterion_claims
hazard_assessments
readiness_assessments
trend_observations
assessment_changes
```

Not every backend must represent these as physical database collections/tables with identical names. They are the logical names used by the application contract.

## Criterion claims through the common interface

`criterion_claims` are ordinary logical collection documents from the storage layer's perspective, but they have preservation semantics defined by the data model and mapping workflow.

The builder writes reviewed normalized claims through `RegistryStore` helpers/upserts. The risk manager queries them through `RegistryReader`.

```text
source record
 -> mapping rule
 -> criterion_claim
 -> RegistryStore
 -> RegistryReader
 -> RiskFramework
```

Storage code should preserve the document/provenance; it should not reinterpret the criterion value or calculate a risk band.

## Read/write ownership

### Registry builder: write/update owner

Normal creation and update operations are performed by `qnl_format_registry_builder`:

- acquire/replay source artifacts;
- persist snapshots;
- replace/upsert current source contributions;
- reconcile canonical formats;
- generate criterion claims from reviewed mappings;
- supersede old claims where configured;
- save hazard/readiness/trend/change outputs.

For narrative sources, the reviewed transcription artifact enters the builder as source evidence; the storage layer does not perform LLM transcription.

### Risk manager: read/query owner

`preservation_risk_manager.RegistryReader` requires the read side of the contract:

```python
query(collection, filt)
```

It provides higher-level operations such as:

- list current canonical formats;
- get a canonical format;
- resolve strong identity aliases that can contribute criterion claims;
- retrieve global/institution-scoped criterion claims;
- retrieve legacy evidence where needed.

When given a storage configuration, it lazily uses `registry_builder.storage.create_store(...)`, keeping backend implementation centralized in the builder.

## File-export access

The risk manager can also use `JsonRegistryStore` without a live persistent backend.

The supported builder export handoff is:

```text
output/
  registry.json
  criterion_claims.jsonl   (or criterion_claims.json)
        |
        v
JsonRegistryStore
        |
        v
RegistryReader / risk manager
```

When `--registry-json` points to `registry.json`, the risk manager automatically looks for sibling criterion-claim exports. This keeps the portable export path functionally equivalent to the logical collections needed for assessment.

A canonical-format-only file can resolve formats, but without relevant criterion claims it may produce missing/unknown framework answers.

## Global vs institution-scoped queries

Scope is enforced above the generic storage query layer by `RegistryReader`/evidence assembly.

### Global assessment

Excludes institution-scoped claims.

### Institution assessment

For example `institution_id=qnl` includes:

```text
global/external evidence
+ claims explicitly scoped to qnl
```

This permits both:

```text
"the specification is publicly documented"      (global)
"QNL currently lacks a required specialist tool" (institution-scoped)
```

without turning the local observation into a universal property of the format.

## Access/query through adapters

Application/service code should use the common layers:

```text
business logic
 -> RegistryReader / RegistryStore
 -> configured backend adapter
 -> MongoDB / file / memory / future backend
```

Avoid:

```text
risk/scoring/business logic
 -> direct pymongo collection calls
```

Direct database queries are acceptable for administration/debugging, but they are not the application API.

## Updates through adapters

The risk manager does not expose arbitrary registry writes. Updates should flow through builder-supported source/update workflows so provenance and replacement rules are applied.

Examples:

```text
QNL evidence file
 -> institutional source adapter
 -> RawFormatRecord
 -> criterion mapping
 -> institution-scoped criterion_claims
 -> RegistryStore
```

```text
DPC PDF/HTML
 -> reviewed transcription JSON
 -> standard_json / DPC adapter
 -> RawFormatRecord
 -> criterion mapping
 -> criterion_claims
 -> RegistryStore
```

A future HTTP/web service that supports updates should call an application-level source/update service above `RegistryStore`; it should not expose arbitrary database mutation to clients or AI models.

## Canonical request interface above the data layer

Consumers use the risk manager's controlled request layer rather than constructing database queries.

Example:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["software_dependencies_environment"]
  },
  "scope": "global"
}
```

The request executor resolves PDF, queries the configured store, selects evidence by scope, applies the framework, and returns canonical JSON.

A future HTTP API or external reporting service can wrap this request/response contract without changing the backend interface.

## Backend implementation guidance

A new storage backend should:

1. subclass `RegistryStore`;
2. implement deterministic `upsert` behavior;
3. implement query behavior required by current callers;
4. preserve documents without silently dropping provenance fields;
5. provide stable keys/replacement semantics consistent with base helpers;
6. implement connection/transaction lifecycle hooks if needed;
7. add backend-specific indexes for common query fields without changing logical semantics;
8. add storage-contract tests;
9. prove the risk manager can query canonical formats and `criterion_claims` through it.

See:

[`../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md)

## Related documentation

- Canonical backend-neutral data model: [`DATA_MODEL.md`](DATA_MODEL.md)
- Repository architecture: [`REPOSITORY_ARCHITECTURE.md`](REPOSITORY_ARCHITECTURE.md)
- Source onboarding: [`HOW_TO_ADD_A_SOURCE.md`](HOW_TO_ADD_A_SOURCE.md)
- Unstructured-source transcription: [`TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](TRANSCRIBING_UNSTRUCTURED_SOURCES.md)
- Builder storage/export configuration: [`../qnl_format_registry_builder/docs/STORAGE_AND_EXPORT_CONFIG.md`](../qnl_format_registry_builder/docs/STORAGE_AND_EXPORT_CONFIG.md)
- MongoDB physical schema: [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md)
- Risk-manager architecture: [`../preservation_risk_manager/docs/ARCHITECTURE.md`](../preservation_risk_manager/docs/ARCHITECTURE.md)
- Human/system query API: [`../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md`](../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md)
