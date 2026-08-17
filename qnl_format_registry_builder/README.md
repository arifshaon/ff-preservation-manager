# QNL File Format Registry Builder

`qnl_format_registry_builder` is the **evidence-ingestion and registry-construction module** in the File Format Preservation Manager repository.

It is not a manually maintained static registry. Its deliverable is a repeatable process that can be rerun when NARA, PRONOM, LOC, QNL, or other configured sources change.

At repository level:

```text
sources
  -> qnl_format_registry_builder
  -> common RegistryStore / evidence model
  -> preservation_risk_manager
```

See the repository architecture and shared data model first if you are working across modules:

- [`../docs/REPOSITORY_ARCHITECTURE.md`](../docs/REPOSITORY_ARCHITECTURE.md)
- [`../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)

## What this module does

```text
Source acquisition
  -> content-addressed snapshots
  -> adapter extraction
  -> RawFormatRecord
  -> normalization
  -> verified identifier reconciliation
  -> CanonicalFormat
  -> source-native evidence retention
  -> declarative criterion mapping
  -> criterion_claims
  -> RegistryStore persistence
  -> change detection
  -> optional exports/reports
```

The builder owns normal registry **writes and updates**. The risk manager reads the resulting registry through the same storage abstraction.

## Main capabilities

- NARA Digital Preservation Framework acquisition and parsing.
- PRONOM registry and DROID/signature evidence.
- Library of Congress FDD XML evidence.
- Structured JSON source packages.
- Institutional policy workbook ingestion.
- QNL institutional format evidence.
- Content-addressed source snapshot cache and offline replay.
- Conservative reconciliation using configured identifier authority rules.
- Source-by-source incremental augmentation against a persistent store.
- Declarative source-to-criterion mappings with review status/versioning.
- Criterion-claim audit and backfill workflows.
- Institutional evidence and policy overlays kept separate from global facts.
- Preservation method/readiness/trend evidence support.
- Change detection between registry states.
- Pluggable source adapters, storage backends, and exporters.
- Storage backends: memory, file/JSON, MongoDB, and trusted external plugins.
- Optional JSON, JSONL, CSV, SQLite, and Markdown outputs.

## Start here

For installation, setup, and every supported operator mode, use:

**[`docs/INSTALLATION_SETUP_AND_RUN.md`](docs/INSTALLATION_SETUP_AND_RUN.md)**

For the full builder documentation map:

**[`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md)**

## Installation

Python 3.10 or later is required.

```powershell
cd qnl_format_registry_builder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,mongo]"
pytest -q
```

If MongoDB is not required:

```powershell
python -m pip install -e ".[dev]"
```

## Quick run

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out output
```

The default/example workflow demonstrates multi-source registry construction. Exact record counts depend on the configured/pinned/current upstream data.

Offline replay after snapshots have been cached:

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out output `
  --offline
```

## Common CLI modes

| Command | Purpose |
| --- | --- |
| `registry_builder run` | Run source acquisition, reconciliation, mapping, persistence, change detection, and exports. |
| `registry_builder validate` | Validate an exported `registry.json`. |
| `registry_builder collision-report` | Inspect identifier collisions/heuristic bridges. |
| `registry_builder criterion-evidence-audit` | Read-only audit of source fields and projected criterion coverage. |
| `registry_builder mapping validate` | Validate criterion-mapping configuration. |
| `registry_builder criterion-claims backfill` | Rebuild criterion claims from existing stored evidence without reacquiring all sources. |

Full commands and examples: [`docs/INSTALLATION_SETUP_AND_RUN.md`](docs/INSTALLATION_SETUP_AND_RUN.md).

## Storage and the common interface

All persistence is behind `RegistryStore`.

A full backend implements:

```python
upsert(collection, key, document)
query(collection, filter)
```

Built-in names:

```text
memory
file / json_file
mongodb
```

Example MongoDB block:

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry"
  }
}
```

The sibling risk manager reuses the same configured store through `RegistryReader`; it does not duplicate MongoDB access logic.

Read:

- shared logical model/interface: [`../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
- builder storage/export config: [`docs/STORAGE_AND_EXPORT_CONFIG.md`](docs/STORAGE_AND_EXPORT_CONFIG.md)
- MongoDB physical schema: [`docs/MONGODB_STORAGE_SCHEMA.md`](docs/MONGODB_STORAGE_SCHEMA.md)

## Source-by-source augmentation

A persistent registry can be updated one source at a time:

```text
NARA run
 -> adds/refreshes NARA source contribution

PRONOM run later
 -> adds/refreshes verified PRONOM identity evidence
 -> current canonical view is recomputed from active source contributions

LOC run later
 -> adds/refreshes LOC FDD sustainability evidence
```

Earlier source records remain available for provenance/history. The current view uses active source contributions rather than blindly appending duplicates.

Read [`docs/INCREMENTAL_SOURCE_UPDATES.md`](docs/INCREMENTAL_SOURCE_UPDATES.md).

## Criterion claims

Source adapters should retain source-native vocabulary. Declarative mapping files then convert relevant source fields into neutral `criterion_claims` with provenance.

This is the bridge used by `preservation_risk_manager`:

```text
source-native field/value
 -> approved mapping rule
 -> criterion_claim
 -> framework question
 -> deterministic answer/risk analysis
```

Read [`docs/criterion_mapping_workflow.md`](docs/criterion_mapping_workflow.md).

## Adding sources/backends

Built-in adapters use short names. External trusted packages can use explicit plugin paths:

```json
{
  "id": "future_source",
  "type": "mypkg.adapters.future:FutureAdapter",
  "enabled": true
}
```

Storage plugins use the same pattern:

```json
{
  "storage": {
    "type": "mypkg.storage.sql:SqlRegistryStore"
  }
}
```

Plugin imports execute trusted code. Use only reviewed packages/configuration.

Read:

- [`docs/ADDING_AND_RUNNING_DATA_SOURCES.md`](docs/ADDING_AND_RUNNING_DATA_SOURCES.md)
- [`docs/ADAPTER_REFERENCE.md`](docs/ADAPTER_REFERENCE.md)
- [`docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](docs/ADAPTER_IMPLEMENTATION_GUIDE.md)

## Generated data

Normal runtime/export directories are not source documentation and should not be committed as ordinary generated output.

Source snapshots belong under the configured work directory, commonly:

```text
work/snapshots/<source_id>/
```

Optional review exports commonly appear under `output/` or `out/`.

## Tests

Before pushing changes:

```powershell
cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"
pytest -q
```

For source/mapping changes, also run the smallest relevant real/configured pipeline and inspect the run/coverage report.

## Related module

Once evidence is in the registry, `preservation_risk_manager` can perform deterministic or AI-assisted assessment without duplicating the ingestion/storage logic.

Start at [`../preservation_risk_manager/README.md`](../preservation_risk_manager/README.md).
