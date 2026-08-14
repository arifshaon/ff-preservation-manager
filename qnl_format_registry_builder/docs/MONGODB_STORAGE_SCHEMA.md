# MongoDB storage schema

This document describes the MongoDB implementation of the `RegistryStore` backend.

MongoDB is the first production storage backend for the registry. The pipeline writes directly to MongoDB through `MongoRegistryStore`; JSON, CSV, SQLite and Markdown files are optional exports and are not staging files for database population.

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

```bash
python -m pip install -e ".[mongo]"
```

## Storage model

The registry is stored as logical MongoDB collections. A pipeline run persists:

1. run metadata and report;
2. source snapshots acquired in the current run;
3. source records extracted in the current run;
4. the current canonical registry view recomputed from active evidence contributions;
5. per-format identifier, overlay, hazard, readiness, trend, and change records.

When `incremental_source_updates` is enabled, running one source at a time is supported. The current run contributes new evidence, while latest successful evidence contributions from other sources are reused for reconciliation. Earlier source records remain in MongoDB as provenance/history.

## Mongo-safe key handling

Source material can contain upstream keys that MongoDB may treat specially, for example field names containing `.` or starting with `$`.

`MongoRegistryStore` normalizes dictionary keys before persistence:

| Original key pattern | Stored form |
| --- | --- |
| `.` in a key | Replaced with fullwidth dot `\uff0e` |
| Leading `$` | Replaced with fullwidth dollar `\uff04` |

This happens recursively for nested dictionaries and lists. It is a storage-layer concern only; source adapters and reconciliation code should not perform MongoDB-specific key rewriting.

## Collection overview

| Collection | Purpose | Main lookup keys |
| --- | --- | --- |
| `runs` | One document per pipeline run, including run report and source status. | `run_id` |
| `source_snapshots` | Immutable source material snapshots acquired in a run. | `run_id`, `source_id`, `sha256` |
| `source_records` | Normalized raw evidence records extracted from source snapshots. | `run_id`, `source_id`, `source_record_id` |
| `canonical_formats` | Current queryable canonical registry records, plus retained non-current records. | `canonical_id`, `current` |
| `format_identifiers` | Flattened identifier claims for lookup and matching. | `type`, `value`, `format_id` |
| `institution_policy_overlays` | Institutional policy/action overlays attached to canonical formats. | `run_id`, `format_id`, `institution_id`, `institution_format_id` |
| `hazard_assessments` | Current-run hazard assessment snapshot per canonical format. | `run_id`, `format_id`, `basis`, `band` |
| `readiness_assessments` | Readiness evidence/actions per canonical format. | `run_id`, `format_id`, `sequence` |
| `trend_observations` | Trend/exposure evidence per canonical format. | `run_id`, `format_id`, `sequence` |
| `assessment_changes` | Typed change events between the previous current registry view and the new view. | `change_id`, `created_at`, `format_id`, `change_type` |

If `collection_prefix` is set, the physical collection name is prefixed, for example `dev_canonical_formats`.

## Common fields

Most persisted documents contain some combination of the following fields:

| Field | Purpose |
| --- | --- |
| `run_id` | Pipeline run that produced or stored the document. |
| `source_id` | Configured source instance ID, for example `nara_digital_preservation_framework`. |
| `source_type` | Adapter type, for example `nara_digital_preservation_framework` or `pronom_registry`. |
| `canonical_id` | Stable canonical format ID created during reconciliation. |
| `format_id` | Alias of `canonical_id` used by storage helper collections. |
| `current` | Boolean flag on `canonical_formats`; `false` means retained history, not current registry view. |
| `last_seen_run_id` | Last run where a canonical format appeared in the current registry view. |
| `last_removed_run_id` | Run that first marked a canonical format as no longer current. |
| `removed_at` | Timestamp when a canonical format was marked non-current. |
| `_storage_key` | Generic key used by the fallback `upsert()` method. |

## `runs`

One document is written at the start of a run with `status: running`, then replaced with the final run report after the run completes.

Important fields:

| Field | Purpose |
| --- | --- |
| `run_id` | Unique run identifier. |
| `started_at` | UTC timestamp when the run started. |
| `finished_at` | UTC timestamp when the run finished. |
| `status` | `running` at start, usually `completed` at end. |
| `config_path` | Config file used for the run. |
| `storage` | Storage summary: type, database, path, collection prefix. |
| `offline` | Whether offline replay was used. |
| `incremental_source_updates` | Whether source-by-source augmentation was enabled. |
| `previous_canonical_formats` | Count of current canonical records before the run. |
| `sources` | Per-source status summary. |
| `identifier_kinds` | Identifier strength/verification rules used for the run. |
| `source_status_counts` | Count of completed, failed, disabled sources. |
| `source_change_counts` | Count of changed/unchanged completed source snapshots. |
| `raw_records_extracted` | Number of source records extracted in this run only. |
| `stored_source_records_used_for_augmentation` | Number of stored source records reused from other sources for source-by-source augmentation. |
| `active_source_records` / `raw_records` | Total evidence records used for reconciliation in this run. |
| `contributing_source_ids` | Source IDs that contributed new evidence in this run. |
| `canonical_formats` | Number of canonical formats generated in the current view. |
| `institution_policy_formats` | Count of canonical formats with institutional overlays. |
| `validation_errors` | Validation errors from the run. |
| `validation_warnings` | Validation warnings from the run. |
| `change_detection` | Compact change summary. |
| `change_counts` | Change counts by type. |
| `changes` | Sample change events included in the run report. |
| `exports_enabled` | Whether optional file exports were written. |
| `outputs` | Export filenames when exports are enabled. |

Typical query:

```javascript
db.runs.find().sort({finished_at: -1}).limit(1).pretty()
```

## `source_snapshots`

Stores the source material snapshots acquired during a run.

Important fields:

| Field | Purpose |
| --- | --- |
| `run_id` | Run that acquired the snapshot. |
| `source_id` | Configured source instance. |
| `source_type` | Adapter type. |
| `uri` | Original URI or file path used by the adapter. |
| `acquired_at` | UTC acquisition timestamp. |
| `sha256` | Content hash of the acquired source material. |
| `local_path` | Cached local snapshot path under the work directory. |
| `content_type` | Optional content type. |
| `note` | Optional adapter/acquisition note. |
| `changed` | Whether the source content changed compared with the local snapshot index. |
| `from_cache` | Whether the snapshot came from cache/offline replay. |
| `metadata` | Adapter-specific metadata such as release mode, release date, Git ref, or fallback details. |

Upsert identity:

```text
run_id + source_id + sha256
```

Typical query:

```javascript
db.source_snapshots.find(
  {source_id: "nara_digital_preservation_framework"},
  {run_id: 1, uri: 1, sha256: 1, metadata: 1}
).pretty()
```

## `source_records`

Stores normalized raw evidence records extracted from source snapshots. These records are the source-level evidence contributions that feed reconciliation.

Important fields mirror `RawFormatRecord`:

| Field | Purpose |
| --- | --- |
| `run_id` | Run that extracted the record. |
| `source_id` | Configured source instance. |
| `source_type` | Adapter type. |
| `source_record_id` | Stable source-local record ID; generated if missing. |
| `name` | Source-provided format name. |
| `category` | Source-provided category/family. |
| `description` | Source description or note. |
| `extensions` | Compatibility list of extensions. |
| `mime_types` | Compatibility list of MIME types. |
| `puids`, `loc_ids`, `nara_ids`, `wikidata_ids` | Compatibility identifier lists for existing adapters. |
| `identifiers` | Generic identifier claims, each with `kind`, `value`, `source`, `verified`, `source_record_id`. |
| `urls` | Source URLs or authority links. |
| `institution_policy` | Institutional policy/action overlay data when the source is an institutional workbook. |
| `hazard` | Source hazard estimate and native rating payload. |
| `readiness` | Source readiness evidence. |
| `trend` | Source trend/exposure evidence. |
| `evidence` | Snapshot/source-row evidence pointers. |
| `raw` | Original source row or useful source subset for audit/debugging. |

Upsert identity:

```text
run_id + source_id + source_record_id
```

Typical query:

```javascript
db.source_records.find(
  {source_id: "nara_digital_preservation_framework"},
  {source_record_id: 1, name: 1, identifiers: 1, hazard: 1}
).limit(5).pretty()
```

## `canonical_formats`

Stores the recomputed canonical registry view. This is the main collection for querying the current registry.

Important fields mirror `CanonicalFormat` plus storage fields:

| Field | Purpose |
| --- | --- |
| `canonical_id` | Stable canonical ID, usually based on the strongest verified identifier or a name-derived fallback. |
| `format_id` | Alias of `canonical_id`. |
| `preferred_name` | Reconciled preferred display name. |
| `category` | Reconciled format category/family. |
| `description` | Reconciled description where available. |
| `identifiers` | Identifier values grouped by kind, for example `{puid: [...], nara: [...], extension: [...]}`. |
| `identifier_claims` | Flattened source-specific identifier evidence with provenance. |
| `source_records` | Source evidence summaries contributing to this canonical format. |
| `institution_policy_overlays` | Institutional policy/action overlays. |
| `external_hazard` | External hazard evidence before final reconciliation. |
| `hazard_assessment` | Final hazard band/basis/review state and native rating metadata. |
| `readiness` | Readiness evidence/actions. |
| `trend` | Trend/exposure observations. |
| `preservation_method` | Assigned preservation method profiles. |
| `provenance` | Reconciliation and source provenance metadata. |
| `run_id` | Run that produced the current stored version. |
| `current` | `true` or absent means current; `false` means retained historical record. |
| `last_seen_run_id` | Latest run where this record was current. |
| `last_removed_run_id` | Run that marked the record non-current. |
| `removed_at` | Timestamp when marked non-current. |

Upsert identity:

```text
canonical_id
```

Current registry query:

```javascript
db.canonical_formats.find({current: {$ne: false}})
```

Sample query:

```javascript
db.canonical_formats.findOne(
  {"identifiers.extension": "pdf", current: {$ne: false}},
  {canonical_id: 1, preferred_name: 1, identifiers: 1, hazard_assessment: 1, source_records: 1}
)
```

## `format_identifiers`

Stores one flattened row per identifier claim attached to a canonical format. This supports fast lookup by identifier type and value.

Important fields:

| Field | Purpose |
| --- | --- |
| `run_id` | Run that generated the identifier claim. |
| `format_id` | Canonical format ID. |
| `canonical_id` | Canonical format ID alias. |
| `type` | Identifier namespace, for example `puid`, `loc`, `nara`, `wikidata`, `extension`, `mime`, or future namespaces such as `dpc`. |
| `value` | Identifier value. |
| `source` | Source that made or verified the claim. |
| `verified` | Whether this source verifies the namespace according to `identifier_kinds`. |
| `source_record_id` | Source record that produced the claim. |

Upsert identity:

```text
format_id + type + value + source
```

Typical query:

```javascript
db.format_identifiers.findOne({type: "puid", value: "fmt/18"})
```

## `institution_policy_overlays`

Stores institutional policy/action overlays separated from external authority evidence.

Important fields depend on the institutional adapter but commonly include:

| Field | Purpose |
| --- | --- |
| `run_id` | Run that generated the overlay. |
| `format_id` / `canonical_id` | Canonical format ID. |
| `institution_id` | Institution profile, for example `qnl`. |
| `institution_name` | Institution display name. |
| `institution_format_id` | Local/institutional format ID. |
| `source_row` | Workbook/source row if available. |
| `local_risk_level` / `risk_level` | Institutional risk label. |
| `preservation_action` | Institution-defined action. |
| `proposed_preservation_plan` | Proposed local preservation plan. |
| `preferred_tools` | Preferred processing/conversion tools. |
| `conversion_process` | Local conversion or handling process. |
| `raw` | Original source row or subset. |

Upsert identity:

```text
run_id + format_id + institution_id + institution_format_id + source_row
```

Typical query:

```javascript
db.institution_policy_overlays.find({institution_id: "qnl"}).limit(10).pretty()
```

## `hazard_assessments`

Stores the final hazard assessment for each canonical format generated by a run.

Important fields:

| Field | Purpose |
| --- | --- |
| `run_id` | Run that produced the assessment. |
| `format_id` / `canonical_id` | Canonical format ID. |
| `band` | Final hazard band, for example `Low`, `Moderate`, `High`, or operational states such as `no_estimator_available`. |
| `basis` | Basis for the final assessment, for example external-only, corroborated, institutional override, or no estimator. |
| `rating` | Normalized rating where available. |
| `external_band` | External source band where available. |
| `institution_band` | Institutional band where available. |
| `review_required` | Whether a human review is required. This is not the same as divergence. |
| `external_rating_native` | Source-native rating value. |
| `external_rating_native_scale` | Name of source-native scale. |
| `external_rating_native_direction` | Direction such as `higher_is_safer` or `lower_is_safer`. |
| `external_native_gap_to_institution_band` | Source-specific native gap when the core understands the source scale. |
| `confidence` | Assessment confidence where supplied. |
| `reasons` / `evidence` | Explanation and supporting evidence where supplied. |

Upsert identity:

```text
run_id + format_id
```

Typical query:

```javascript
db.hazard_assessments.find({band: "High"}).limit(20).pretty()
```

## `readiness_assessments`

Stores readiness evidence and actions by format.

Important fields:

| Field | Purpose |
| --- | --- |
| `run_id` | Run that produced the record. |
| `format_id` / `canonical_id` | Canonical format ID. |
| `sequence` | Sequence number for multiple readiness entries per format. |
| `status` | Readiness status where supplied. |
| `action` / `recommended_action` | Readiness action where supplied. |
| `basis` | Why the readiness state/action was assigned. |
| `evidence` | Supporting evidence. |

Upsert identity:

```text
run_id + format_id + sequence
```

## `trend_observations`

Stores trend/exposure evidence separately from base hazard.

Important fields:

| Field | Purpose |
| --- | --- |
| `run_id` | Run that produced the record. |
| `format_id` / `canonical_id` | Canonical format ID. |
| `sequence` | Sequence number for multiple trend entries per format. |
| `trend` / `direction` | Trend direction where supplied. |
| `exposure` | Exposure/holdings/use context where supplied. |
| `basis` | Why the trend observation was assigned. |
| `evidence` | Supporting evidence. |

Upsert identity:

```text
run_id + format_id + sequence
```

## `assessment_changes`

Stores actionable change events generated by comparing the previous current registry view with the newly computed view.

Important fields:

| Field | Purpose |
| --- | --- |
| `change_id` | Stable change ID for the run/change/canonical field. |
| `run_id` | Run that detected the change. |
| `created_at` | Timestamp when detected. |
| `change_type` | Event type. |
| `canonical_id` / `format_id` | Affected canonical format. |
| `field` | Field that changed, where applicable. |
| `previous` | Summary of previous state. |
| `current` | Summary of current state. |
| `severity` | Review severity, for example `info` or `review`. |
| `recommended_actions` | Suggested follow-up actions. |
| `collapsed_change_type` | For bulk source-level collapse events. |
| `affected_count` | Number of per-format changes collapsed into a bulk event. |
| `dominant_source_ids` | Sources involved in a bulk event. |

Common `change_type` values:

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

Upsert identity:

```text
change_id
```

Typical query:

```javascript
db.assessment_changes.find({change_type: "hazard_band_changed"}).sort({created_at: -1}).limit(20).pretty()
```

## Indexes created by `MongoRegistryStore`

The MongoDB adapter creates these indexes at startup:

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

These are not unique indexes. Upsert behavior is controlled in the store methods by the filter used in `replace_one(..., upsert=True)`.

## Useful local verification queries

```javascript
use format_registry

db.runs.countDocuments()
db.canonical_formats.countDocuments({current: {$ne: false}})
db.source_records.countDocuments()
db.source_snapshots.countDocuments()
db.format_identifiers.countDocuments()
db.hazard_assessments.countDocuments()
db.assessment_changes.countDocuments()
```

Latest run:

```javascript
db.runs.find().sort({finished_at: -1}).limit(1).pretty()
```

Formats with no estimator:

```javascript
db.canonical_formats.find(
  {"hazard_assessment.basis": "no_estimator_available", current: {$ne: false}},
  {canonical_id: 1, preferred_name: 1, hazard_assessment: 1, source_records: 1}
).pretty()
```

Formats requiring review:

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

Show source evidence for a format:

```javascript
db.canonical_formats.findOne(
  {preferred_name: /Portable Document Format/i, current: {$ne: false}},
  {canonical_id: 1, preferred_name: 1, identifiers: 1, source_records: 1, hazard_assessment: 1}
)
```

Recent review actions:

```javascript
db.assessment_changes.find(
  {severity: "review"},
  {created_at: 1, change_type: 1, canonical_id: 1, recommended_actions: 1}
).sort({created_at: -1}).limit(20).pretty()
```

## Operational notes

- `canonical_formats` is the best collection for ordinary current registry queries.
- `source_records` and `source_snapshots` are evidence/provenance collections. Do not manually edit them to change the canonical view; rerun the relevant source adapter instead.
- `hazard_assessments` is useful for per-run reporting, while the latest assessment is also embedded in `canonical_formats.hazard_assessment`.
- `assessment_changes` is the operational review queue produced by change detection.
- Optional exports can be disabled for database-only runs with `"exports": {"enabled": false}`.
- If you need to reset a local test database, use `db.dropDatabase()` from the selected database after confirming you are not connected to a production database.
