# Data model and storage interface

This document describes the **shared logical data model and persistence contract** used across the repository.

It is intentionally separate from the MongoDB schema. MongoDB is one implementation of the storage interface; the logical model and application behavior must not depend on MongoDB-specific code.

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
- risk-analysis code does not need to know how MongoDB collections are implemented;
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
- whether a previous evidence claim should remain historical or be superseded;
- which validation/provenance rules apply.

The backend should not invent preservation semantics.

### `query`

Returns documents from a logical collection matching a simple equality filter.

The risk manager deliberately consumes this minimal operation through a Protocol instead of importing MongoDB directly.

## Built-in storage adapters

The registry builder currently registers these backend names:

| `type` | Class / behavior | Intended use |
| --- | --- | --- |
| `memory` | in-memory document collections | unit tests, transient runs |
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

A typical local configuration is:

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

For MongoDB-specific collection indexes, field examples, and verification queries, see [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md).

## Logical collections

The base storage interface exposes named convenience methods that write the following logical collections.

| Logical collection | Purpose / ownership |
| --- | --- |
| `runs` | Pipeline/run identity, timestamps, status, and provenance. |
| `source_snapshots` | Acquired artifacts, source URI, hashes, cache/acquisition metadata. |
| `source_records` | Adapter-extracted source records before canonical reconciliation. |
| `canonical_formats` | Current reconciled file-format identities and aggregated evidence references. |
| `format_identifiers` | Identifier claims linking canonical formats to authority/source identifiers. |
| `institution_policy_overlays` | Institution-specific decisions/policy; not universal format facts. |
| `format_evidence_claims` | Legacy/general format evidence claims retained for compatibility/use. |
| `criterion_claims` | Normalized, provenance-bearing claims against neutral preservation criteria. |
| `hazard_assessments` | Stored hazard assessment outputs produced by builder workflows. |
| `readiness_assessments` | Local/readiness observations. |
| `trend_observations` | Time-based observations. |
| `assessment_changes` | Change events between current/previous registry state. |

Not every backend must represent these as physical database collections/tables with identical names. They are the **logical collection names used by the application contract**.

## Core entities

### Source snapshot

A `SourceSnapshot` records acquisition of a source artifact:

- `source_id`
- `source_type`
- `uri`
- `acquired_at`
- `sha256`
- local cached path
- content type/note
- changed/from-cache state
- adapter/source metadata

Snapshots make acquisition auditable and allow offline replay.

### Raw source record

`RawFormatRecord` is the adapter boundary. It can contain:

- source name/category/description;
- extensions/MIME types;
- source-specific identifier fields;
- generic identifier claims;
- URLs;
- institutional policy/context;
- institutional criterion evidence;
- hazard/readiness/trend observations;
- generic evidence;
- `native_fields` for source-native vocabulary used by declarative mappings;
- `raw` source payload.

Adapters should preserve upstream meaning here instead of prematurely translating every source into QNL policy or a risk score.

### Identifier claim

An identifier contains:

```text
kind
value
source
verified
source_record_id
```

`verified=true` means the claim came from the authority that owns the identifier namespace, e.g. a PUID from PRONOM. This distinction is important for conservative reconciliation.

### Canonical format

`CanonicalFormat` is the reconciled registry identity. It includes:

- `canonical_id`
- preferred name/category/description
- identifiers grouped by namespace
- identifier-claim provenance
- contributing source records
- institution policy overlays
- institution evidence claims
- external hazard evidence/assessment
- readiness/trend observations
- preservation method profile
- provenance

The canonical record is a **current view over retained evidence**, not a replacement for source records.

### Criterion claim

A criterion claim is the primary normalized evidence object consumed by the risk manager. Typical fields include:

```text
canonical_id
criterion_id
value
source_id / source_type
source_record_id
source_field
mapping_rule_id / mapping_version
institution_id (optional)
source_independence / review metadata
raw/source value where retained
current/review status
```

The exact populated fields depend on the mapping/source. The key principle is that a criterion claim should preserve enough provenance to trace a normalized value back to an upstream record and mapping rule.

## Native evidence vs normalized claim vs framework answer

These are separate layers:

```text
upstream source field/value
       |
       v
declarative criterion mapping
       |
       v
criterion_claim
  criterion_id + normalized value + provenance
       |
       v
RiskFramework question
  declares evidence_fields + allowed answers
       |
       v
deterministic answer derivation
       |
       v
score / risk band (when calibrated and sufficiently complete)
```

This separation avoids hard-coding one assessment framework into source adapters.

## Read/write ownership

### Registry builder: write/update owner

Normal creation and update operations are performed by `qnl_format_registry_builder`:

- acquire/replay sources;
- persist snapshots;
- replace/upsert current source contributions;
- reconcile canonical formats;
- generate criterion claims from approved mappings;
- supersede old claims where configured;
- save assessments/change events.

The builder calls the storage abstraction rather than issuing direct MongoDB commands from preservation logic.

### Risk manager: read/query owner

`preservation_risk_manager.RegistryReader` requires only:

```python
query(collection, filt)
```

It provides higher-level read methods such as:

- list current canonical formats;
- get a canonical format;
- resolve which canonical/source-derived IDs can contribute criterion claims;
- retrieve criterion claims for global or institutional scope;
- retrieve legacy format evidence claims.

When given a storage configuration, it lazily uses `registry_builder.storage.create_store(...)`, so MongoDB/file/plugin implementation remains centralized in the registry builder.

## JSON export fallback

The risk manager can also use `JsonRegistryStore` to read exported JSON without a live backend.

This is useful for:

- tests;
- portable/review snapshots;
- offline analysis;
- environments where the builder package/database is not available.

A JSON export used for risk analysis must include the relevant evidence collections if question derivation depends on criterion claims. A canonical-format-only export can resolve formats but may not provide enough evidence for meaningful assessment.

## Global vs institution-scoped claims

Scope is enforced at read time.

### Global request

A global risk assessment excludes institution-scoped claims.

### Institution request

An institution request, e.g. `institution_id=qnl`, includes:

- global/external claims; and
- claims explicitly scoped to the requested institution.

This supports a global statement such as “format specification is public” alongside a local statement such as “QNL currently lacks a required specialist tool” without merging the two into one universal fact.

## Access/query through adapters

A service or module should use the common interface rather than directly calling MongoDB.

Correct pattern:

```text
business logic
 -> RegistryReader / RegistryStore
 -> configured backend adapter
 -> MongoDB/file/etc.
```

Avoid:

```text
risk/scoring/business logic
 -> pymongo collection calls
```

Direct database access is acceptable for administration/debugging, but it should not become the application API.

## Updates through adapters

The current risk manager does not expose arbitrary registry writes. Updates should flow through builder-supported ingestion or storage workflows so provenance and replacement rules are applied.

For example, to add new QNL evidence:

```text
QNL evidence JSON/source
 -> qnl_institution_format_evidence adapter
 -> RawFormatRecord/native evidence
 -> criterion mapping
 -> criterion_claims with institution_id=qnl
 -> RegistryStore.upsert
```

A future web/API service that supports updates should invoke an application-level update service or source adapter and then `RegistryStore`; it should **not** let clients issue arbitrary database mutations.

## Canonical request interface above the data layer

For consumers, the risk manager's controlled request layer sits above `RegistryReader`.

Example machine request:

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

The request executor resolves PDF, queries the configured registry store, selects claims, applies the active framework, and returns canonical JSON. A future HTTP API can wrap this request/response contract without changing the backend interface.

## Backend implementation guidance

A new storage backend should:

1. subclass `RegistryStore`;
2. implement deterministic `upsert` behavior;
3. implement equality-filter `query` behavior used by current callers;
4. preserve documents without silently dropping provenance fields;
5. provide stable keys/replace semantics consistent with the base helper methods;
6. implement connection/transaction lifecycle hooks if needed;
7. add backend-specific indexes for common query fields without changing logical semantics;
8. add tests using the same storage contract.

See [`../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md).

## Related documentation

- Repository architecture: [`REPOSITORY_ARCHITECTURE.md`](REPOSITORY_ARCHITECTURE.md)
- Builder storage/export configuration: [`../qnl_format_registry_builder/docs/STORAGE_AND_EXPORT_CONFIG.md`](../qnl_format_registry_builder/docs/STORAGE_AND_EXPORT_CONFIG.md)
- MongoDB physical schema: [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md)
- Builder adapter implementation: [`../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md)
- Risk-manager architecture: [`../preservation_risk_manager/docs/ARCHITECTURE.md`](../preservation_risk_manager/docs/ARCHITECTURE.md)
- Human/system query API: [`../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md`](../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md)
