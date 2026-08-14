# Storage and export configuration

The pipeline uses **one active storage backend per run** through the `RegistryStore` interface.

```text
pipeline objects -> selected RegistryStore
```

File exports are optional review/interchange products. They are not staging files for MongoDB or any other storage backend.

## Storage backends

Currently supported storage types:

```text
memory     # in-process dry run / tests
file       # JSON document storage on disk
json_file  # alias for file
mongodb    # MongoDB production backend
```

All storage backends receive the same logical records from the pipeline:

```text
SourceSnapshot        -> source_snapshots
RawFormatRecord       -> source_records
CanonicalFormat       -> canonical_formats
Identifier claims     -> format_identifiers
Institution overlays  -> institution_policy_overlays
Hazard assessments    -> hazard_assessments
Readiness assessments -> readiness_assessments
Trend observations    -> trend_observations
Change events         -> assessment_changes
Run report            -> runs
```

## File JSON storage

The file backend is a real `RegistryStore`, not an export. It stores one JSON document per record under collection directories.

Use this storage block:

```json
{
  "storage": {
    "type": "file",
    "path": "output/file_registry_store"
  },
  "exports": {
    "enabled": false
  }
}
```

Expected directory structure:

```text
output/file_registry_store/
  runs/
  source_snapshots/
  source_records/
  canonical_formats/
  format_identifiers/
  institution_policy_overlays/
  hazard_assessments/
  readiness_assessments/
  trend_observations/
  assessment_changes/
```

This gives a simple way to test persistence, inspect stored documents, and verify change detection before switching the same run to MongoDB.

## MongoDB storage

MongoDB is the first production database backend.

Detailed implementation notes, collection purposes, field names, indexes, and verification queries are documented in [`MONGODB_STORAGE_SCHEMA.md`](MONGODB_STORAGE_SCHEMA.md).

Install the MongoDB dependency:

```bash
python -m pip install -e ".[mongo]"
```

Use this storage block:

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

MongoDB writes to the same logical collections as the file backend:

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

## Change detection

Change detection uses the selected storage backend. Before building the new run, the pipeline reads:

```text
store.get_current_registry_view()
```

The first run against an empty store is a `baseline` run. It establishes the first current registry view and does not emit one `record_added` event for every format.

Later runs compare the previous current view with the newly built registry and persist typed change events to `assessment_changes`, including:

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
```

When a previously current canonical format disappears from a later run, the record is retained for history but marked:

```json
{
  "current": false,
  "last_removed_run_id": "...",
  "removed_at": "..."
}
```

Current registry queries return only records where `current` is not false, so removed formats do not keep generating repeated removal events on every later run.

## Toggle test

To test the storage abstraction, keep the sources unchanged and toggle only the `storage` block.

File-backed run:

```json
{
  "storage": {
    "type": "file",
    "path": "output/file_registry_store"
  },
  "exports": {
    "enabled": false
  }
}
```

MongoDB-backed run:

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

The canonical record counts and change counts should match across storage backends for the same enabled sources and method-profile config.

## Review/export run

Set exports on only when review files are useful:

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

These are generated from the current run. They are not the source of truth and are not used to populate storage.

## Default sample behaviour

`config/sources.example.json` keeps `storage.type` as `memory` so a clean clone remains runnable without local infrastructure.

For file storage, copy values from:

```text
config/storage.file.example.json
```

For MongoDB storage, copy values from:

```text
config/storage.mongodb.example.json
```
