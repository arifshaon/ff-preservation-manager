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
- Future change reports should generate work items from change events rather than mixing tasks into state labels.
- The queryable registry lives in one selected storage backend per run, with MongoDB implemented as the first production backend.
- JSON, JSONL, CSV, SQLite, Markdown and other files are optional exports; they are not staging files and not a second source of truth.
- Preservation methods are assigned through reusable method profiles by format family/domain, not by hand-writing a unique method for every file format.

## Architecture documentation

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the detailed design and logic covering source adapters, storage adapters, export adapters, MongoDB-first queryable registry design, hazard/readiness/trend/exposure separation, and reconciliation rather than additive scoring.

See [`docs/SOURCE_ADAPTERS.md`](docs/SOURCE_ADAPTERS.md) for the source-first adapter model. Source adapters retrieve and parse source material, emit `RawFormatRecord` objects, and leave persistence to the storage layer.

See [`docs/STORAGE_AND_EXPORT_CONFIG.md`](docs/STORAGE_AND_EXPORT_CONFIG.md) for MongoDB and export configuration.

See [`docs/INSTITUTIONAL_OVERLAYS.md`](docs/INSTITUTIONAL_OVERLAYS.md) for the institution-neutral model used to support QNL and future institutional policy spreadsheets.

See [`docs/PRESERVATION_METHOD_PROFILES.md`](docs/PRESERVATION_METHOD_PROFILES.md) for the method-profile model used to generate scalable action-plan templates.

## Current implementation status

This implementation includes:

- source-adapter architecture;
- repeatable local runs from a JSON config file;
- immutable source snapshots with SHA-256 hashes;
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
- reusable preservation method profiles assigned after reconciliation;
- `RegistryStore` persistence with `memory` and `mongodb` backends;
- MongoDB collections for runs, source snapshots, source records, canonical formats, identifiers, institutional overlays, hazard assessments, readiness assessments, trend observations, and change records;
- optional JSON, JSONL, CSV, SQLite and Markdown exports;
- coverage reporting;
- validation checks;
- tests for source adapters, reconciliation, hazard reconciliation, storage persistence, MongoDB-safe serialization, and preservation method profiles.

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
  "enabled": true
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

## External source adapters

The preferred NARA adapter is source-level:

```text
nara_digital_preservation_framework
```

Its current retrieval mode is `published_csv`, using NARA's public Digital Preservation Framework CSV files. The deprecated `nara_preservation_csv` adapter name remains available only as a compatibility alias.

The preferred PRONOM adapter is:

```text
pronom_registry
```

Its current retrieval mode is `github_json`, using PRONOM's public GitHub JSON dataset. The existing `pronom_droid_xml` adapter remains available for DROID signature XML.

## Source adapter pattern

Each source adapter implements two methods:

```python
acquire() -> list[SourceSnapshot]
extract(snapshots) -> list[RawFormatRecord]
```

Source adapters understand source acquisition and parsing. They do not persist directly to MongoDB. Persistence belongs to `RegistryStore`; exports belong to exporter adapters.

## Storage adapter pattern

Storage adapters persist the live/queryable registry and assessment history.

Implemented backends:

```text
memory
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
