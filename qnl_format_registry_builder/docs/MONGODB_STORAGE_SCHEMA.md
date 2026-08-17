# MongoDB storage schema

This document describes the **MongoDB physical implementation** of the repository's backend-neutral registry data model.

For the canonical entity/collection/transformation model—including `SourceSnapshot`, `Identifier`, `RawFormatRecord`, `CanonicalFormat`, `criterion_claims`, and risk-framework outputs—start with:

[`../../docs/DATA_MODEL.md`](../../docs/DATA_MODEL.md)

MongoDB is one `RegistryStore` implementation. The pipeline writes directly to MongoDB through `MongoRegistryStore`; JSON, CSV, SQLite and Markdown files are optional exports and are not staging files for database population.

## Implementation location

```text
registry_builder/storage/mongo.py
```

The backend implements the narrowed `RegistryStore` contract:

```python
upsert(collection: str, key: str | None, doc: dict) -> str
query(collection: str, filt: dict | None = None) -> list[dict]
```

It also overrides common helper methods such as `create_run`, `save_snapshot`, `save_source_record`, `upsert_canonical_format`, `upsert_identifier`, and `save_hazard_assessment` so records are stored with stable MongoDB upsert keys and useful indexes.

`criterion_claims` use the generic/storage helper path and have dedicated MongoDB indexes for format/criterion, source/mapping, criteria/mapping version, and institution scope.

## Configuration

Minimal local configuration:

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry"
  }
}
```

Full supported storage block:

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry",
    "collection_prefix": "",
    "server_selection_timeout_ms": 5000,
    "ping": true
  }
}
```

| Field | Purpose |
| --- | --- |
| `type` | Must be `mongodb` for the built-in MongoDB backend. |
| `uri` | MongoDB connection URI. Defaults to `mongodb://localhost:27017`. |
| `database` / `db` | Database name. Defaults to `format_registry`. |
| `collection_prefix` | Optional prefix added to every collection name, useful for side-by-side test stores. |
| `server_selection_timeout_ms` | Connection timeout before MongoDB is treated as unavailable. Defaults to `5000`. |
| `ping` | Whether to run an initial MongoDB `ping`. Defaults to `true`. |

Install dependency:

```powershell
python -m pip install -e ".[mongo]"
```

## Storage model

A pipeline run may persist:

1. run metadata and report;
2. source snapshots acquired in the current run;
3. source records extracted in the current run;
4. the current canonical registry view recomputed from active evidence contributions;
5. identifier claims and institution overlays;
6. normalized `criterion_claims` when criterion mapping is enabled;
7. hazard/readiness/trend/change records.

When `incremental_source_updates` is enabled, running one source at a time is supported. The current run contributes new evidence, while latest successful evidence contributions from other sources are reused for reconciliation. Earlier source records remain in MongoDB as provenance/history.

## Mongo-safe key handling

Source material can contain upstream keys that MongoDB may treat specially, for example field names containing `.` or starting with `$`.

`MongoRegistryStore` normalizes dictionary keys before persistence:

| Original key pattern | Stored form |
| --- | --- |
| `.` in a key | Replaced with fullwidth dot `\uff0e` |
| Leading `$` | Replaced with fullwidth dollar `\uff04` |

This happens recursively for nested dictionaries and lists. It is a storage-layer concern only; source adapters and reconciliation code should not perform MongoDB-specific key rewriting.

Criterion mapping's dotted-path resolver understands exact, Mongo-safe, and case-insensitive dictionary-key variants, so source-native keys that contain literal dots can still be addressed through mapping rules.

## Collection overview

| Collection | Purpose | Main lookup keys |
| --- | --- | --- |
| `runs` | One document per pipeline run, including run report and source status. | `run_id` |
| `source_snapshots` | Source material snapshots acquired in a run. | `run_id`, `source_id`, `sha256` |
| `source_records` | Normalized raw/source-native evidence records emitted by adapters. | `run_id`, `source_id`, `source_record_id` |
| `canonical_formats` | Current reconciled registry records, plus retained non-current records. | `canonical_id`, `current` |
| `format_identifiers` | Flattened identifier claims for lookup/matching. | `type`, `value`, `format_id` |
| `institution_policy_overlays` | Institutional policy/action overlays attached to canonical formats. | `run_id`, `format_id`, `institution_id`, `institution_format_id` |
| `criterion_claims` | Neutral normalized evidence used by framework-driven risk analysis. | `canonical_id`, `criterion_id`, `source_id`, `mapping_rule_id`, `institution_id` |
| `hazard_assessments` | Current-run hazard assessment snapshot per canonical format. | `run_id`, `format_id`, `basis`, `band` |
| `readiness_assessments` | Readiness evidence/actions per canonical format. | `run_id`, `format_id`, `sequence` |
| `trend_observations` | Trend/exposure evidence per canonical format. | `run_id`, `format_id`, `sequence` |
| `assessment_changes` | Typed change events between previous and current registry state. | `change_id`, `created_at`, `format_id`, `change_type` |

If `collection_prefix` is set, the physical collection name is prefixed, for example `dev_canonical_formats`.

## Common fields

Most persisted documents contain some combination of:

| Field | Purpose |
| --- | --- |
| `run_id` | Pipeline run that produced/stored the document where applicable. |
| `source_id` | Configured source instance ID. |
| `source_type` | Adapter/source type. |
| `canonical_id` | Stable canonical format ID. |
| `format_id` | Alias of `canonical_id` used by helper collections. |
| `institution_id` | Optional institution scope, e.g. `qnl`. |
| `current` | Current/non-current flag where the collection uses retained history. |
| `_storage_key` | Generic stable key used by fallback `upsert()`. |

## `runs`

One document is written at the start of a run with `status: running`, then replaced with the final run report after the run completes.

Important fields:

| Field | Purpose |
| --- | --- |
| `run_id` | Unique run identifier. |
| `started_at` / `finished_at` | Run timestamps. |
| `status` | Run status. |
| `config_path` | Config file used. |
| `storage` | Storage summary. |
| `offline` | Whether cached/offline replay was used. |
| `incremental_source_updates` | Whether source-by-source augmentation was enabled. |
| `sources` | Per-source status summary. |
| `identifier_kinds` | Identifier strength/authority rules. |
| `raw_records_extracted` | Source records extracted in this run. |
| `stored_source_records_used_for_augmentation` | Stored records reused from other source contributions. |
| `canonical_formats` | Current canonical format count. |
| `validation_errors` / `validation_warnings` | Validation outcome. |
| `change_detection` / `change_counts` | Change summary. |
| `exports_enabled` / `outputs` | Export state and filenames. |

Typical query:

```javascript
db.runs.find().sort({finished_at: -1}).limit(1).pretty()
```

## `source_snapshots`

Stores source material snapshots acquired during a run.

Important fields:

| Field | Purpose |
| --- | --- |
| `run_id` | Run that acquired the snapshot. |
| `source_id` / `source_type` | Source identity/type. |
| `uri` | Original URI/file path. |
| `acquired_at` | Acquisition timestamp. |
| `sha256` | Content hash. |
| `local_path` | Cached/temporary local path. |
| `content_type` | Optional content type. |
| `note` | Adapter/acquisition note. |
| `changed` | Source-change indicator where available. |
| `from_cache` | Cached/offline replay indicator. |
| `metadata` | Adapter-specific release/acquisition metadata. |

Upsert identity:

```text
run_id + source_id + sha256
```

## `source_records`

Stores source-level evidence records emitted by adapters. These records feed reconciliation and criterion mapping.

Important fields mirror `RawFormatRecord`:

| Field | Purpose |
| --- | --- |
| `run_id` | Run that extracted/stored the record. |
| `source_id` / `source_type` | Source identity/type. |
| `source_record_id` | Stable source-local record ID. |
| `name` / `category` / `description` | Source-provided identity/description. |
| `extensions` / `mime_types` | Source-provided compatibility fields. |
| `puids`, `loc_ids`, `nara_ids`, `wikidata_ids` | Compatibility identifier lists. |
| `identifiers` | Generic identifier claims with provenance/verification. |
| `urls` | Source/authority links. |
| `institution_policy` | Institution-specific policy/action overlay. |
| `institution_evidence` | Institution-scoped evidence observations. |
| `hazard` | Source-native/composite hazard evidence. |
| `readiness` | Readiness/capability evidence. |
| `trend` | Trend/exposure evidence. |
| `evidence` | Snapshot/source-row/source-locator evidence pointers. |
| `native_fields` | Source-native values intended for declarative criterion mappings. |
| `raw` | Original source row/record/useful raw subset for audit/debugging. |

For transcribed narrative sources ingested through `standard_json`, transcription-specific values may remain under `raw.native_fields.*`. A thin source-specific adapter may instead promote them into top-level `native_fields`.

Upsert identity:

```text
run_id + source_id + source_record_id
```

Typical query:

```javascript
db.source_records.find(
  {source_id: "loc_fdd_xml"},
  {source_record_id: 1, name: 1, native_fields: 1, identifiers: 1}
).limit(5).pretty()
```

## `canonical_formats`

Stores the recomputed canonical registry view. This is the main collection for ordinary current-format lookup.

Important fields mirror `CanonicalFormat` plus storage fields:

| Field | Purpose |
| --- | --- |
| `canonical_id` / `format_id` | Stable canonical identity. |
| `preferred_name` | Reconciled display name. |
| `category` / `description` | Reconciled descriptive fields. |
| `identifiers` | Identifier values grouped by kind. |
| `identifier_claims` | Source-specific identifier evidence with provenance. |
| `source_records` | Source contributions to this canonical format. |
| `institution_policy_overlays` | Institutional policy/action overlays. |
| `institution_evidence_claims` | Local institutional evidence. |
| `external_hazard` | External hazard evidence. |
| `hazard_assessment` | Final builder hazard state. |
| `readiness` / `trend` | Capability/trend observations. |
| `preservation_method` | Assigned method profiles. |
| `provenance` | Reconciliation/source provenance. |
| `run_id` | Run producing stored current version. |
| `current` | Current/non-current state. |
| `last_seen_run_id` / `last_removed_run_id` / `removed_at` | History markers. |

Upsert identity:

```text
canonical_id
```

Current registry query:

```javascript
db.canonical_formats.find({current: {$ne: false}})
```

## `format_identifiers`

Stores one flattened document per identifier claim attached to a canonical format.

Important fields:

```text
run_id
format_id / canonical_id
type
value
source
verified
source_record_id
```

Upsert identity:

```text
format_id + type + value + source
```

Typical query:

```javascript
db.format_identifiers.findOne({type: "puid", value: "fmt/18"})
```

## `institution_policy_overlays`

Stores institution-specific policy/action decisions separately from external authority evidence and neutral criterion claims.

Common fields include:

```text
run_id
format_id / canonical_id
institution_id
institution_name
institution_format_id
source_row
local_risk_level
preservation_action
proposed_preservation_plan
preferred_tools
conversion_process
raw
```

Institution policy decisions should not be treated as universal format facts.

## `criterion_claims`

This collection is the normalized evidence bridge between registry-builder sources and `preservation_risk_manager` frameworks.

A typical claim looks like:

```json
{
  "canonical_id": "puid-fmt-18",
  "criterion_id": "sustainability.disclosure",
  "value": "openly_documented",
  "source_id": "pronom_registry",
  "source_type": "pronom_registry",
  "source_record_id": "fmt/18",
  "source_field": "native_fields.specification_status",
  "source_value": "Full",
  "native_vocabulary": "pronom",
  "directness": "explicit",
  "covers": "full",
  "source_independence": "independent",
  "criteria_version": "v1",
  "mapping_version": "2026-08-17",
  "mapping_rule_id": "pronom.disclosure.specification_status.v1",
  "review_status": "approved",
  "observed_at": "2026-08-17T00:00:00+00:00"
}
```

Fields:

| Field | Purpose |
| --- | --- |
| `canonical_id` | Format the claim describes. |
| `criterion_id` | Neutral criteria-vocabulary field. |
| `value` | Normalized allowed criterion value. |
| `source_id` / `source_type` | Source contribution provenance. |
| `source_record_id` | Source-local record that produced the observation. |
| `source_field` | Actual mapped field path. |
| `source_value` | Source/native value used by the mapping where retained. |
| `native_vocabulary` | Name/version of source vocabulary where supplied. |
| `directness` | `explicit`, `derived`, or `inferred`. |
| `covers` / `covers_note` | Full/partial semantic coverage. |
| `source_independence` | `independent`, `source_derived`, or `institution_scoped`. |
| `criteria_version` | Criteria vocabulary version. |
| `mapping_version` | Mapping configuration version. |
| `mapping_rule_id` | Rule producing the claim. |
| `review_status` | Claim review state. |
| `observed_at` | Observation/mapping execution timestamp. |
| `institution_id` | Optional institution scope. |

Institution-scoped claims must include/retain institution scope and are excluded from global-only analysis by the risk manager.

Do not directly edit this collection to “fix” a risk result. Correct the source/transcription/mapping and regenerate claims so provenance remains valid.

Typical queries:

```javascript
db.criterion_claims.find({canonical_id: "fmt-pdf"}).pretty()
```

```javascript
db.criterion_claims.find({criterion_id: "sustainability.adoption"}).limit(20).pretty()
```

```javascript
db.criterion_claims.find({institution_id: "qnl"}).limit(20).pretty()
```

```javascript
db.criterion_claims.aggregate([
  {$group: {_id: "$criterion_id", count: {$sum: 1}}},
  {$sort: {count: -1}}
])
```

## `hazard_assessments`

Stores builder hazard conclusions separately from primitive criterion claims.

Important fields commonly include:

```text
run_id
format_id / canonical_id
band
basis
rating
external_band
institution_band
review_required
external_rating_native
external_rating_native_scale
external_rating_native_direction
confidence
reasons / evidence
```

A source/composite hazard band is a conclusion and should not automatically be remapped into a primitive criterion claim.

## `readiness_assessments`

Stores readiness/capability evidence/actions by format.

Common fields:

```text
run_id
format_id / canonical_id
sequence
status
action / recommended_action
basis
evidence
```

## `trend_observations`

Stores trend/exposure evidence separately from base hazard.

Common fields:

```text
run_id
format_id / canonical_id
sequence
trend / direction
exposure
basis
evidence
```

## `assessment_changes`

Stores actionable change events generated by comparing the previous current registry view with the newly computed view.

Common fields:

```text
change_id
run_id
created_at
change_type
canonical_id / format_id
field
previous
current
severity
recommended_actions
collapsed_change_type
affected_count
dominant_source_ids
```

Common change types include:

```text
record_added
record_removed
preferred_name_changed
category_changed
identifiers_changed
hazard_band_changed
hazard_basis_changed
external_rating_native_changed
divergence_opened
divergence_resolved
source_coverage_changed
```

## Indexes created by `MongoRegistryStore`

The MongoDB adapter currently creates these indexes at startup:

| Collection | Indexes |
| --- | --- |
| `runs` | `run_id` |
| `source_snapshots` | `run_id + source_id + sha256` |
| `source_records` | `run_id + source_id + source_record_id` |
| `canonical_formats` | `canonical_id`, `preferred_name`, `current` |
| `format_identifiers` | `type + value`, `format_id + type + value` |
| `institution_policy_overlays` | `run_id + format_id`, `institution_id + institution_format_id` |
| `hazard_assessments` | `run_id + format_id`, `basis + band` |
| `readiness_assessments` | `run_id + format_id` |
| `trend_observations` | `run_id + format_id` |
| `assessment_changes` | `created_at`, `format_id`, `change_type` |
| `criterion_claims` | `canonical_id + criterion_id`, `source_id + mapping_rule_id`, `criteria_version + mapping_version`, `institution_id` |

These are not unique indexes. Upsert behavior is controlled by store/helper key semantics.

## Useful local verification queries

```javascript
use format_registry

db.runs.countDocuments()
db.canonical_formats.countDocuments({current: {$ne: false}})
db.source_records.countDocuments()
db.source_snapshots.countDocuments()
db.format_identifiers.countDocuments()
db.criterion_claims.countDocuments()
db.hazard_assessments.countDocuments()
db.assessment_changes.countDocuments()
```

Latest run:

```javascript
db.runs.find().sort({finished_at: -1}).limit(1).pretty()
```

Criterion-claim coverage by source:

```javascript
db.criterion_claims.aggregate([
  {$group: {_id: "$source_id", claims: {$sum: 1}}},
  {$sort: {claims: -1}}
])
```

Criterion-claim coverage by criterion:

```javascript
db.criterion_claims.aggregate([
  {$group: {_id: "$criterion_id", claims: {$sum: 1}}},
  {$sort: {claims: -1}}
])
```

Formats requiring builder hazard review:

```javascript
db.canonical_formats.find(
  {"hazard_assessment.review_required": true, current: {$ne: false}},
  {canonical_id: 1, preferred_name: 1, hazard_assessment: 1}
).pretty()
```

Lookup by identifier:

```javascript
const id = db.format_identifiers.findOne({type: "puid", value: "fmt/18"})
db.canonical_formats.findOne({canonical_id: id.format_id, current: {$ne: false}})
```

Show source evidence and mapped claims for a format:

```javascript
const f = db.canonical_formats.findOne(
  {preferred_name: /Portable Document Format/i, current: {$ne: false}},
  {canonical_id: 1, preferred_name: 1, identifiers: 1, source_records: 1}
)

db.criterion_claims.find({canonical_id: f.canonical_id}).pretty()
```

Note that risk-manager identity expansion may also consume claims attached to strong source-derived aliases such as PUID/LOC canonical IDs, not only the aggregate display record.

## Operational notes

- `canonical_formats` is the best collection for ordinary current registry identity queries.
- `source_records` and `source_snapshots` are evidence/provenance collections. Rerun the source adapter/transcription workflow rather than manually editing them.
- `criterion_claims` is the normalized evidence layer for framework-driven risk analysis. Correct source mappings and regenerate claims rather than manually changing claim values.
- `hazard_assessments` stores builder hazard conclusions and is conceptually separate from neutral criterion claims.
- `assessment_changes` is an operational review/change queue.
- Optional exports can be disabled for database-only runs with `"exports": {"enabled": false}`.
- If you reset a local test database, confirm first that you are not connected to production.

## Related documentation

- Canonical backend-neutral data model: [`../../docs/DATA_MODEL.md`](../../docs/DATA_MODEL.md)
- Storage interface/adapter contract: [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
- Criterion mapping workflow: [`criterion_mapping_workflow.md`](criterion_mapping_workflow.md)
- Reading the registry: [`READING_THE_REGISTRY.md`](READING_THE_REGISTRY.md)
