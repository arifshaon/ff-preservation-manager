# QNL File Format Registry Builder

This project is a **registry-building system**, not a manually curated static registry.

It builds a local file-format registry by running a repeatable pipeline over configured sources such as an institutional policy spreadsheet, PRONOM registry data, PRONOM/DROID XML, LOC FDD XML, NARA Digital Preservation Framework data, and future adapters.

## Core principle

The registry is an output of the process. The deliverable is the workflow that can be rerun when upstream sources change.

Pipeline stages:

```text
Source acquisition → extraction/parsing → normalization → matching/reconciliation → storage → assessment/change detection → optional exports/reporting
```

## Why this structure

The pipeline follows the agreed preservation-risk model:

- An institution's current spreadsheet is treated as an **institutional policy overlay**, not as the boundary of all known file formats.
- QNL is the first configured institutional profile, not a hard-coded assumption in the core model.
- External sources and institutional criteria are not added together as one risk score.
- Hazard, trend, exposure, readiness, confidence, and provenance remain separate axes.
- Change reports generate review work from change events rather than mixing tasks into state labels.
- The queryable registry lives in one selected storage backend per run, with MongoDB implemented as the first production backend.
- JSON, JSONL, CSV, SQLite, Markdown and other files are optional exports; they are not staging files and not a second source of truth.
- Preservation methods are assigned through reusable method profiles by format family/domain, not by hand-writing a unique method for every file format.

## Documentation map

Start with [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md). It explains which document to read depending on whether you are running the registry, staging source files, configuring storage, or implementing a new adapter.

Key documents:

| Need | Read |
| --- | --- |
| Run the project and understand the common workflow | `README.md` |
| Navigate all documentation | [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md) |
| Understand the end-to-end design | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Understand source retrieval, cache, offline replay, local files, and fallback logic | [`docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md`](docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md) |
| Implement a new source/storage/export adapter | [`docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](docs/ADAPTER_IMPLEMENTATION_GUIDE.md) |
| Configure existing adapter types | [`docs/ADAPTER_REFERENCE.md`](docs/ADAPTER_REFERENCE.md) |
| Understand NARA-specific release modes and admin local files | [`docs/NARA_ADAPTER_REQUIREMENTS.md`](docs/NARA_ADAPTER_REQUIREMENTS.md) and [`docs/NARA_LOCAL_FILES.md`](docs/NARA_LOCAL_FILES.md) |
| Configure MongoDB, file storage, and exports | [`docs/STORAGE_AND_EXPORT_CONFIG.md`](docs/STORAGE_AND_EXPORT_CONFIG.md) |
| Understand institutional policy overlays such as QNL | [`docs/INSTITUTIONAL_OVERLAYS.md`](docs/INSTITUTIONAL_OVERLAYS.md) |
| Understand preservation method profiles | [`docs/PRESERVATION_METHOD_PROFILES.md`](docs/PRESERVATION_METHOD_PROFILES.md) |
| Review design decisions and open next steps | [`docs/DECISIONS.md`](docs/DECISIONS.md) and [`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md) |

## Current implementation status

This implementation includes:

- source-adapter architecture;
- repeatable local runs from a JSON config file;
- immutable source snapshots with SHA-256 hashes;
- content-addressed snapshot cache under `work/snapshots/<source_id>/`;
- offline replay from cached snapshots using `--offline`;
- local/admin file acquisition for staged source files;
- source extraction adapters for:
  - standardized JSON source packages;
  - institution policy XLSX files;
  - PRONOM registry GitHub JSON data;
  - PRONOM/DROID XML signature files;
  - LOC FDD XML records;
  - NARA Digital Preservation Framework data;
- deprecated compatibility aliases for older/narrower adapter names such as `qnl_policy_xlsx` and `nara_preservation_csv`;
- normalization of extensions, MIME types, PUIDs, LOC IDs, NARA IDs and related identifiers;
- conservative identifier-led reconciliation;
- institution policy overlays attached to canonical format records;
- external hazard reconciliation against institutional estimators where available;
- NARA native rating preservation with explicit native scale direction;
- baseline-vs-change detection across runs;
- bulk change collapse into source-level events when a source/configuration shift touches a large fraction of the registry;
- reusable preservation method profiles assigned after reconciliation;
- `RegistryStore` persistence with `memory`, `file`/`json_file`, and `mongodb` backends;
- MongoDB collections for runs, source snapshots, source records, canonical formats, identifiers, institutional overlays, hazard assessments, readiness assessments, trend observations, and change records;
- optional JSON, JSONL, CSV, SQLite and Markdown exports;
- coverage reporting;
- validation checks;
- tests for source adapters, reconciliation, hazard reconciliation, storage persistence, MongoDB-safe serialization, change detection, cache/offline behavior, and preservation method profiles.

## Installation

Requires Python 3.10 or later.

```bash
cd qnl_format_registry_builder
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -e .
```

For tests:

```bash
python -m pip install -e ".[dev]"
pytest
```

For MongoDB-backed runs:

```bash
python -m pip install -e ".[dev,mongo]"
```

## Running the sample pipeline

The default sample config uses in-memory storage and file exports so a clean clone can run without infrastructure:

```bash
python -m registry_builder run \
  --config config/sources.example.json \
  --workdir work \
  --out output
```

Default demonstration exports:

```text
output/registry.json
output/registry.jsonl
output/registry.csv
output/registry.sqlite
output/source_snapshots.json
output/run_report.json
output/coverage_report.md
```

These files are optional export products, not the registry storage layer.

## Source retrieval modes, cache, and fallback logic

Source retrieval is deliberately separated into four concepts:

```text
online acquisition
  fetch the upstream source now and snapshot it

snapshot cache
  keep content-addressed copies under work/snapshots/<source_id>/

offline mode
  replay already-cached snapshots without network access

local/admin files
  treat administrator-supplied files as this run's source material
```

Online runs check the upstream source. If the content is unchanged, the existing cached snapshot is reused and the report marks it as unchanged.

Offline mode is for audit replay or reproducibility checks:

```bash
python -m registry_builder run --config config/sources.example.json --workdir work --out output --offline
```

It does not fetch the network. If a requested source is not already cached, the run fails clearly.

Local/admin files are different from offline replay. They are used when an operator manually downloads or internally stages source files and wants the pipeline to use those files as the current source input. The adapter still copies them into the content-addressed snapshot cache and records metadata showing `source_location: local_file` and `admin_supplied: true`.

Each source can be marked as required or optional:

```json
{
  "id": "nara_digital_preservation_framework",
  "required": false
}
```

A required source failure aborts the run. An optional source failure is recorded in `run_report.json`, and the pipeline continues with the remaining sources.

## NARA release modes

The NARA source adapter supports four release modes:

```text
explicit_uris
  use the exact configured URIs

pinned
  construct the two dated NARA release CSV URLs from release_date

latest
  discover the newest matching action-plan and numbered-risk CSV pair through GitHub

local_files
  use administrator-supplied local CSV files
```

Use `pinned` for audit and repeatability:

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "required": false,
  "retrieval_mode": "published_csv",
  "release_mode": "pinned",
  "release_date": "20260320",
  "github_ref": "master"
}
```

Use `latest` for quarterly refresh runs. Its fallback order is:

```text
1. online latest discovery
2. cached .nara_release_index.json
3. fallback_local_files / manual_fallback_files / fallback_files
4. pinned fallback_release_date
```

If a fallback is used, the snapshot metadata records the fallback mode and original error. For example:

```text
release_mode: latest_cached_fallback
release_resolution_error: HTTPError: HTTP Error 403
```

or:

```text
release_mode: latest_local_fallback
source_location: local_file
admin_supplied: true
```

Use `local_files` when an admin has downloaded and staged the NARA CSVs:

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "required": false,
  "retrieval_mode": "published_csv",
  "release_mode": "local_files",
  "local_files": [
    {
      "path": "input/nara/NARA_PreservationActionPlan_FileFormats_20260320.csv",
      "kind": "preservation_action_plan",
      "release_date": "20260320"
    },
    {
      "path": "input/nara/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv",
      "kind": "risk_matrix_numbered",
      "release_date": "20260320"
    }
  ]
}
```

For scheduled `latest` jobs, set `GITHUB_TOKEN` to avoid unauthenticated GitHub API limits:

```bash
GITHUB_TOKEN=<token>
```

## Running with MongoDB

Use one active storage backend per run. For MongoDB:

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

With `exports.enabled: false`, the run persists the registry directly to MongoDB and does not write registry JSON/CSV/SQLite/Markdown exports.

MongoDB collections populated by the pipeline:

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

The pipeline writes directly from in-memory pipeline objects into `RegistryStore`. It does **not** build JSON files first and then import them into MongoDB.

A starter MongoDB storage block is available at:

```text
config/storage.mongodb.example.json
```

## Running with file storage

File storage is a real storage backend, not an export. It persists the same logical collections as MongoDB, but as JSON documents under collection directories.

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

Use this when you want to test the storage contract without MongoDB, or when you want a simple portable registry store for review.

## Running against an institutional policy workbook

The preferred spreadsheet adapter is:

```text
institution_policy_xlsx
```

QNL uses this same generic adapter with QNL metadata and QNL column mappings supplied in configuration.

1. Copy the workbook into `input/`, for example:

```text
input/QNL File Format Policy and Action Plan_27_November_2025.xlsx
```

2. Edit `config/sources.example.json` and set this source to `enabled: true`:

```json
{
  "id": "qnl_policy_current",
  "type": "institution_policy_xlsx",
  "enabled": true,
  "institution_id": "qnl",
  "institution_name": "Qatar National Library"
}
```

3. Enable NARA if you want external-vs-institutional reconciliation:

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "release_mode": "pinned",
  "release_date": "20260320"
}
```

4. Run the pipeline:

```bash
python -m registry_builder run --config config/sources.example.json --workdir work --out output
```

The workbook content will be imported as `institution_policy_overlays` attached to canonical format records.

The older adapter name remains available as a compatibility alias:

```text
qnl_policy_xlsx
```

New configurations should use `institution_policy_xlsx`.

## Implementing or configuring adapters

For implementation logic, read these in order:

1. [`docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](docs/ADAPTER_IMPLEMENTATION_GUIDE.md)
2. [`docs/ADAPTER_REFERENCE.md`](docs/ADAPTER_REFERENCE.md)
3. [`docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md`](docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md)

The source adapter contract is:

```python
acquire() -> list[SourceSnapshot]
extract(snapshots) -> list[RawFormatRecord]
```

Source adapters acquire and parse source material. They do not persist directly to MongoDB or write exports. Persistence belongs to `RegistryStore`; optional files belong to exporters.

The implemented source adapter types are documented in `docs/ADAPTER_REFERENCE.md`:

```text
standard_json
institution_policy_xlsx
nara_digital_preservation_framework
nara_preservation_csv      # deprecated alias
pronom_registry
pronom_droid_xml
loc_fdd_xml
qnl_policy_xlsx            # deprecated alias
```

## Storage adapter pattern

Storage adapters persist the live/queryable registry and assessment history.

Implemented backends:

```text
memory
file / json_file
mongodb
```

Future backends can be added without changing source adapters or assessment logic by implementing the `RegistryStore` interface in `registry_builder/storage/base.py`.

## Export direction

File outputs are optional exports from the current run.

Examples:

```text
JSON
JSONL
CSV
SQLite
Markdown reports
API bundles
```

Exports must not update the registry and must not be required for MongoDB population.
