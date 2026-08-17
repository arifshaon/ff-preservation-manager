# Registry Builder: installation, setup, and run guide

This is the primary operator runbook for `qnl_format_registry_builder`.

For architecture, adapter internals, MongoDB field details, or source-specific edge cases, follow the links at the end rather than putting backend-specific logic into this runbook.

## 1. What this module does

The registry builder constructs and updates the preservation evidence registry:

```text
source acquisition
 -> snapshots
 -> source records
 -> normalization
 -> identifier reconciliation
 -> canonical formats
 -> criterion mapping
 -> criterion claims
 -> RegistryStore
 -> change detection / reports / exports
```

It is the normal **write/update owner** for the registry. The sibling `preservation_risk_manager` reads the resulting data through the same storage abstraction.

Shared architecture/data model:

- [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)

## 2. Requirements

- Python 3.10 or later.
- Network access for online source acquisition unless using cached/offline/local-file modes.
- MongoDB only if the selected storage backend is `mongodb`.
- Sufficient local space for source snapshots under `work/` and optional exports under `output/` or `out/`.

## 3. Install

From the repository root in PowerShell:

```powershell
cd qnl_format_registry_builder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mongo]"
pytest -q
```

If MongoDB support is not needed:

```powershell
python -m pip install -e ".[dev]"
```

If using one shared environment for both repository modules, install this package and then install the risk manager into the same environment. That allows the risk manager to reuse builder storage adapters such as MongoDB.

## 4. Configuration model

A normal builder run is controlled by JSON configuration. The major sections/concepts are:

```text
sources
  which upstream/institutional adapters are enabled

identifier_kinds / reconciliation rules
  how authority identifiers may be used for canonical matching

criteria + criterion mappings
  how source-native fields become neutral criterion_claims

storage
  memory, file, MongoDB, or a plugin RegistryStore backend

exports
  optional JSON/JSONL/CSV/SQLite/Markdown review outputs

method profiles / institution config
  optional preservation-method and local context configuration
```

The main multi-source example is:

```text
config/sources.example.json
```

Useful source/storage examples include:

```text
config/sources.nara.mongodb.example.json
config/sources.pronom.mongodb.example.json
config/sources.loc.mongodb.example.json
config/sources.criterion-mapping.mongodb.example.json
config/qnl-institution-format-evidence.mongodb.example.json
config/storage.mongodb.example.json
config/storage.file.example.json
```

Do not put production secrets into committed example files.

## 5. Setup with MongoDB

Start MongoDB, then verify a storage block similar to:

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

The builder's MongoDB implementation is selected through `RegistryStore`; business logic should not depend directly on `pymongo`.

See:

- [`STORAGE_AND_EXPORT_CONFIG.md`](STORAGE_AND_EXPORT_CONFIG.md)
- [`MONGODB_STORAGE_SCHEMA.md`](MONGODB_STORAGE_SCHEMA.md)
- [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)

## 6. Full online pipeline run

From `qnl_format_registry_builder/`:

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out output
```

The CLI reports progress on stderr and prints the final run report JSON on stdout.

Typical flow:

```text
load config
open storage
acquire each enabled source
extract + normalize
load prior active source contributions where needed
reconcile canonical formats
assign method profiles
validate
build criterion claims
change detection
persist
write optional exports/reports
```

### What to inspect after the run

When exports are enabled, typical review files include:

```text
output/run_report.json
output/coverage_report.md
output/registry.json
output/registry.csv
```

With MongoDB/database-only configuration, MongoDB remains the authoritative runtime store and the output directory may contain few or no exports.

Check at minimum:

- run status;
- enabled source status and failure/optional-source notes;
- canonical format count;
- active source-record count;
- criterion-claim count;
- validation errors/warnings;
- change summary;
- collision/review flags where relevant.

## 7. Offline replay from cached snapshots

After an online/local acquisition has populated `work/snapshots/<source_id>/`, run without network fetching:

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out output `
  --offline
```

Offline mode uses cached snapshots only. It is useful for reproducible debugging and repeat processing, but it cannot acquire a source that has no suitable cached snapshot.

Read [`SOURCE_RETRIEVAL_AND_FALLBACKS.md`](SOURCE_RETRIEVAL_AND_FALLBACKS.md).

## 8. Run one source at a time

The registry is designed for source-by-source augmentation against the same persistent store.

### NARA

```powershell
python -m registry_builder run `
  --config config\sources.nara.mongodb.example.json `
  --workdir work `
  --out output\nara
```

### PRONOM

```powershell
python -m registry_builder run `
  --config config\sources.pronom.mongodb.example.json `
  --workdir work `
  --out output\pronom
```

### Library of Congress FDD

```powershell
python -m registry_builder run `
  --config config\sources.loc.mongodb.example.json `
  --workdir work `
  --out output\loc
```

### QNL institutional format evidence

```powershell
python -m registry_builder run `
  --config config\qnl-institution-format-evidence.mongodb.example.json `
  --workdir work `
  --out output\qnl-evidence
```

The current canonical view is recomputed from active source contributions; earlier source records remain available for provenance/history.

Read [`INCREMENTAL_SOURCE_UPDATES.md`](INCREMENTAL_SOURCE_UPDATES.md) before changing source replacement behavior.

## 9. Local/downloaded source files

Adapters can support local/admin-downloaded files where configured. This is useful when an upstream site cannot be acquired automatically or when a release must be manually staged.

Do not turn a manually downloaded file into a one-off parser outside the adapter framework. Configure the appropriate source adapter/local-file mode so snapshot/provenance and extraction behavior remain repeatable.

Read:

- [`ADDING_AND_RUNNING_DATA_SOURCES.md`](ADDING_AND_RUNNING_DATA_SOURCES.md)
- [`NARA_LOCAL_FILES.md`](NARA_LOCAL_FILES.md)
- [`SOURCE_RETRIEVAL_AND_FALLBACKS.md`](SOURCE_RETRIEVAL_AND_FALLBACKS.md)

## 10. Validate an exported registry

```powershell
python -m registry_builder validate `
  --registry output\registry.json
```

The command prints JSON containing `errors` and `warnings` and exits non-zero when validation errors exist.

Use this for exported-registry integrity checks. A successful pipeline also performs validation internally before persistence/export.

## 11. Identifier collision report

```powershell
python -m registry_builder collision-report `
  --registry output\registry.json `
  --sample-limit 50
```

Use this to inspect identifier collisions and heuristic bridges. Collision reports are review/diagnostic outputs; they should not be used to bypass conservative reconciliation rules.

Read [`IDENTIFIER_RECONCILIATION.md`](IDENTIFIER_RECONCILIATION.md).

## 12. Audit evidence/criterion coverage

Read-only source/criterion audit:

```powershell
python -m registry_builder criterion-evidence-audit `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --out output\criterion_evidence_audit.json
```

Optionally filter by source:

```powershell
python -m registry_builder criterion-evidence-audit `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --source loc_fdd_xml
```

This helps distinguish:

```text
source field absent
vs
source field present but not mapped
vs
mapping exists but coverage is limited
```

## 13. Validate criterion mapping configuration

```powershell
python -m registry_builder mapping validate `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings
```

Mapping files should be reviewed/approved deliberately. Do not promote draft mappings merely to increase evidence completeness.

Read [`criterion_mapping_workflow.md`](criterion_mapping_workflow.md).

## 14. Backfill criterion claims

Existing canonical/source records can be remapped without reacquiring every upstream source.

Using explicit inputs:

```powershell
python -m registry_builder criterion-claims backfill `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --dry-run
```

After reviewing a dry run, omit `--dry-run` to write claims.

Use `--include-drafts` only for projection/debugging, not routine production evidence.

Use `--replace-source-claims` when the intended operation is to supersede prior current claims from the mapped source(s) that are no longer generated by the new mapping set.

A combined backfill config is also supported via:

```powershell
python -m registry_builder criterion-claims backfill `
  --config config\criterion-claims-backfill.mongodb.example.json
```

## 15. Progress and quiet runs

Default runs show progress and a heartbeat during quiet stages.

Suppress progress/heartbeat:

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out output `
  --no-progress
```

Change heartbeat interval:

```powershell
--heartbeat-every 60
```

For claim backfill, `--progress-every` controls reporting frequency.

## 16. File-storage mode

Use `config/storage.file.example.json` or a full pipeline config whose storage block selects `file`.

File storage is useful for local persistent testing where MongoDB is unnecessary. The risk manager can consume the same backend as long as both packages are installed and it receives the same storage configuration.

## 17. Add a new source

Preferred approach:

```text
new source
 -> SourceAdapter
 -> SourceSnapshot
 -> RawFormatRecord/native_fields
 -> configured identifier rules
 -> declarative criterion mappings
 -> common RegistryStore
```

Do not put source-specific database writes into an adapter.

Read, in order:

1. [`ADDING_AND_RUNNING_DATA_SOURCES.md`](ADDING_AND_RUNNING_DATA_SOURCES.md)
2. [`ADAPTER_IMPLEMENTATION_GUIDE.md`](ADAPTER_IMPLEMENTATION_GUIDE.md)
3. [`ADAPTER_REFERENCE.md`](ADAPTER_REFERENCE.md)
4. [`IDENTIFIER_RECONCILIATION.md`](IDENTIFIER_RECONCILIATION.md)
5. [`criterion_mapping_workflow.md`](criterion_mapping_workflow.md)

## 18. Add a new storage backend

A storage plugin subclasses `RegistryStore` and implements at least `upsert` and `query`.

Example config:

```json
{
  "storage": {
    "type": "mypkg.storage.sql:SqlRegistryStore"
  }
}
```

Read the repository-wide contract first:

[`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)

Then implement/test using:

[`ADAPTER_IMPLEMENTATION_GUIDE.md`](ADAPTER_IMPLEMENTATION_GUIDE.md)

## 19. Tests before committing/deploying

```powershell
cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"
pytest -q
```

For changes that affect a source or mappings, also perform the smallest appropriate real/configured run and inspect the run report/coverage rather than relying only on unit tests.

## 20. Relationship to the risk manager

Once the builder has populated `canonical_formats` and `criterion_claims`, the risk manager can query the same storage backend:

```powershell
cd ..\preservation_risk_manager
python -m preservation_risk_manager ask `
  "What is the preservation risk of PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

The risk manager should not be given direct MongoDB-specific business logic. It uses `RegistryReader`, which delegates to the configured registry-builder store.

## Deeper references

- Builder documentation map: [`DOCUMENTATION_MAP.md`](DOCUMENTATION_MAP.md)
- Builder architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Source runbook: [`ADDING_AND_RUNNING_DATA_SOURCES.md`](ADDING_AND_RUNNING_DATA_SOURCES.md)
- Storage/export: [`STORAGE_AND_EXPORT_CONFIG.md`](STORAGE_AND_EXPORT_CONFIG.md)
- MongoDB schema: [`MONGODB_STORAGE_SCHEMA.md`](MONGODB_STORAGE_SCHEMA.md)
- Reconciliation: [`IDENTIFIER_RECONCILIATION.md`](IDENTIFIER_RECONCILIATION.md)
- Incremental updates: [`INCREMENTAL_SOURCE_UPDATES.md`](INCREMENTAL_SOURCE_UPDATES.md)
- Criterion mappings: [`criterion_mapping_workflow.md`](criterion_mapping_workflow.md)
- Shared data model/storage API: [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
