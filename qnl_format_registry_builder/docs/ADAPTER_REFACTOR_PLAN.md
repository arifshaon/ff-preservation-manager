# Adapter-Based Storage and Export Refactor Plan

This note tracks the storage/export refactor status.

## Goal

Use one active storage backend per run and keep file outputs as optional exports:

```text
Pipeline services → RegistryStore → queryable local registry
Pipeline services → RegistryExporter adapters → optional outputs
```

## Completed

### Phase 1: Interfaces and documentation

- Added `storage/base.py` with `RegistryStore`.
- Added `storage/memory.py` for tests and clean sample runs.
- Added exporter interface/placeholder modules.
- Added architecture documentation.

### Phase 2: Source-to-storage pipeline wiring

The pipeline now:

1. creates a store using config;
2. creates a run record;
3. acquires source snapshots;
4. extracts and normalizes source records;
5. reconciles into canonical format records;
6. assigns method profiles;
7. validates the registry;
8. persists snapshots, source records, canonical records, identifiers, institutional overlays, hazard assessments, readiness assessments and trend observations through `RegistryStore`;
9. updates the run record with summary counts;
10. writes file exports only when `exports.enabled` is true.

### Phase 3: MongoDB backend

Implemented `MongoRegistryStore` with PyMongo.

MongoDB collections:

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

MongoDB is installed with:

```bash
python -m pip install -e ".[mongo]"
```

## Remaining work

### 1. Move remaining file-export implementation into exporter adapters

The pipeline now treats exports as optional and can run database-only. The implementation of file exports still lives in `pipeline.py`. Move it into:

- `exporters/json_exporter.py`
- `exporters/jsonl_exporter.py`
- `exporters/csv_exporter.py`
- `exporters/sqlite_exporter.py`
- `exporters/markdown_reporter.py`

Rename or retire `registry_builder/db.py` once SQLite export has moved.

### 2. Add MongoDB integration tests

Add integration tests that run only when a MongoDB URI is supplied, for example through:

```text
MONGODB_URI=mongodb://localhost:27017
```

Unit tests should continue to use `MemoryRegistryStore`.

### 3. Add baseline/change reporting

MongoDB now stores run history. The next major feature is comparing two stored runs and generating assessment changes.
