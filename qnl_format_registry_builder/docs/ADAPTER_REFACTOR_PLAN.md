# Adapter-Based Storage and Export Refactor Plan

This note translates the architecture into implementation tasks.

## Goal

Move from direct file writing inside `pipeline.py` to a design where:

```text
Pipeline services → RegistryStore → queryable local registry
Pipeline services → RegistryExporter adapters → optional outputs
```

## Phase 1: Interfaces and documentation

- Add `storage/base.py` with `RegistryStore`.
- Add `storage/memory.py` for tests.
- Add `storage/mongo.py` stub documenting the MongoDB collection plan.
- Add `exporters/base.py` with `RegistryExporter`.
- Add placeholder exporter adapters.
- Add `docs/ARCHITECTURE.md`.

## Phase 2: Move existing exports into adapters

Move current direct writes from `pipeline.py` into:

- `exporters/json_exporter.py`
- `exporters/jsonl_exporter.py`
- `exporters/csv_exporter.py`
- `exporters/sqlite_exporter.py`
- `exporters/markdown_reporter.py`

Rename or retire `registry_builder/db.py` once SQLite export has moved.

## Phase 3: Refactor pipeline to use storage

The pipeline should:

1. create a store using config;
2. create a run record;
3. save snapshots and source records through the store;
4. reconcile into canonical format records;
5. save canonical records and identifiers through the store;
6. calculate assessments and change events;
7. fetch `store.get_current_registry_view()`;
8. run enabled exporters.

## Phase 4: MongoDB backend

Implement `MongoRegistryStore` with PyMongo.

Initial collections:

```text
runs
source_snapshots
source_records
canonical_formats
format_identifiers
qnl_policy_overlays
hazard_assessments
readiness_assessments
trend_observations
assessment_changes
```

## Phase 5: Tests

- Unit-test the storage contract against `MemoryRegistryStore`.
- Add exporter adapter tests.
- Add skipped MongoDB integration tests that run only when MongoDB is available.
- Add pipeline test using memory storage and file export adapters.
