# Storage and export configuration

The pipeline now uses one active storage backend per run through the `RegistryStore` interface.

```text
pipeline objects -> selected RegistryStore
```

File exports are optional review/interchange products. They are not staging files for MongoDB.

## MongoDB storage

MongoDB is the first real production storage backend.

Install the MongoDB dependency:

```bash
python -m pip install -e ".[mongo]"
```

Use this storage block in the pipeline config:

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

The MongoDB backend writes to these collections:

```text
runs
source_snapshots
source_records
canonical_formats
format_identifiers
institution_policy_overlays
hazard_assessments
readiness_assessments
trend_observations
assessment_changes
```

The pipeline persists directly to those collections from in-memory objects already produced during the run:

```text
SourceSnapshot        -> source_snapshots
RawFormatRecord       -> source_records
CanonicalFormat       -> canonical_formats
Identifier claims     -> format_identifiers
Institution overlays  -> institution_policy_overlays
Hazard assessments    -> hazard_assessments
Readiness assessments -> readiness_assessments
Trend observations    -> trend_observations
Run report            -> runs
```

## Database-only run

Set exports off when MongoDB should be the only persistent output:

```json
{
  "exports": {
    "enabled": false
  }
}
```

With exports disabled, the pipeline still creates/acquires source snapshots in the work directory because current source adapters snapshot acquired upstream material before parsing. It does not write registry JSON/CSV/SQLite/Markdown outputs.

## Review/export run

Set exports on when review files are useful:

```json
{
  "exports": {
    "enabled": true
  }
}
```

Current file exports are:

```text
registry.json
registry.jsonl
registry.csv
registry.sqlite
raw_records.jsonl
source_snapshots.json
run_report.json
coverage_report.md
```

These are generated from the current run. They are not the source of truth and are not used to populate MongoDB.

## Default sample behaviour

`config/sources.example.json` keeps `storage.type` as `memory` so a clean clone remains runnable without local infrastructure.

For the first real deployment, switch to:

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry"
  },
  "exports": {
    "enabled": false
  }
}
```

or copy values from:

```text
config/storage.mongodb.example.json
```
