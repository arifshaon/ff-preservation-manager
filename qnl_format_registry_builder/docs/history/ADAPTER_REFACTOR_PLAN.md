# Adapter-Based Storage and Export Refactor Plan

Historical note: this document records a completed storage/export refactor. It is kept for context and should not be treated as current implementation guidance. For current storage behavior, read `../STORAGE_AND_EXPORT_CONFIG.md` and `../MONGODB_STORAGE_SCHEMA.md`.

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

## Notes that were still open at the time

These items may now be complete or superseded. Check current documentation before using them as work items.

### Move remaining file-export implementation into exporter adapters

The pipeline treats exports as optional and can run database-only. The implementation of file exports still lives in `pipeline.py`. A future cleanup may move it into exporter modules.

### Add MongoDB integration tests

Unit tests currently cover Mongo-safe serialization and storage behavior. Full integration tests can be added when a stable test MongoDB service is available in CI.

### Add baseline/change reporting

Baseline/change reporting has since been implemented. Current behavior is documented in `../READING_THE_REGISTRY.md`, `../INCREMENTAL_SOURCE_UPDATES.md`, and `../STORAGE_AND_EXPORT_CONFIG.md`.
