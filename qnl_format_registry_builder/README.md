# QNL File Format Registry Builder

`qnl_format_registry_builder` is the **evidence-ingestion and registry-construction module** in the File Format Preservation Manager repository.

It is not a manually maintained static registry. Its deliverable is a repeatable process that can be rerun when NARA, PRONOM, LOC, QNL, or other configured sources change.

For the first cross-package run from source acquisition to risk assessment, use:

**[`../docs/GETTING_STARTED.md`](../docs/GETTING_STARTED.md)**

## Repository role

```text
sources
  -> qnl_format_registry_builder
  -> canonical formats + criterion claims
  -> RegistryStore / exports
  -> preservation_risk_manager
```

Repository architecture/data model:

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
  -> RegistryStore persistence / exports
  -> change detection
```

The builder owns normal registry **writes and updates**. The risk manager reads the resulting registry through the same storage abstraction or the paired export files.

## Main capabilities

- NARA Digital Preservation Framework acquisition/parsing.
- PRONOM registry and DROID/signature evidence.
- Library of Congress FDD XML evidence.
- Structured JSON source packages.
- Institutional policy workbook ingestion.
- QNL institutional format evidence.
- Content-addressed source snapshot cache and offline replay.
- Conservative reconciliation using configured identifier authority rules.
- Source-by-source incremental augmentation against persistent storage.
- Declarative source-to-criterion mappings with review status/versioning.
- Criterion-claim audit and backfill workflows.
- Institution-scoped evidence separated from global facts.
- Preservation method/readiness/trend evidence support.
- Change detection between registry states.
- Pluggable source adapters, storage backends, and exporters.
- Storage backends: memory, file/JSON, MongoDB, and trusted external plugins.
- Optional JSON, JSONL, CSV, SQLite, and Markdown outputs.

## Start here

| Need | Document |
| --- | --- |
| First build + risk assessment across both packages | [`../docs/GETTING_STARTED.md`](../docs/GETTING_STARTED.md) |
| Installation/setup/all builder modes | [`docs/INSTALLATION_SETUP_AND_RUN.md`](docs/INSTALLATION_SETUP_AND_RUN.md) |
| Full builder documentation map | [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md) |
| Add/map a new source or institution evidence | [`docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md) |
| Detailed criterion mapping workflow | [`docs/criterion_mapping_workflow.md`](docs/criterion_mapping_workflow.md) |
| Periodic source refresh + risk-report orchestration | [`../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md`](../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md) |

## Installation

Python 3.10 or later is required.

```powershell
cd qnl_format_registry_builder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,mongo]"
pytest -q
```

Without MongoDB:

```powershell
python -m pip install -e ".[dev]"
```

## Two different quickstart configurations

### Registry-construction example

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out output
```

This demonstrates multi-source registry construction. **Criterion mapping is not enabled in this config.** It is therefore valid for learning/building the registry, but its outputs are not sufficient by themselves to demonstrate framework-driven risk assessment.

### Cross-package risk-assessment quickstart

Use:

```powershell
python -m registry_builder run `
  --config config\sources.criterion-mapping.quickstart.json `
  --workdir work `
  --out output
```

This no-database config explicitly enables approved criterion mappings and exports:

```text
output\registry.json
output\criterion_claims.jsonl
```

The risk manager uses these together. When given `output\registry.json`, it automatically discovers the sibling criterion-claim export.

Verify:

```powershell
Test-Path output\registry.json
Test-Path output\criterion_claims.jsonl
(Get-Content output\criterion_claims.jsonl | Measure-Object -Line).Lines
```

Full path: [`../docs/GETTING_STARTED.md`](../docs/GETTING_STARTED.md).

## Offline replay

After snapshots have been cached:

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out output `
  --offline
```

Offline mode replays previously acquired evidence; it cannot discover a new upstream release that has never been fetched.

## Periodic source updates

For operational monitoring, an external scheduler/service can rerun an integrated source configuration periodically.

Example:

```powershell
python -m registry_builder run `
  --config config\sources.criterion-mapping.mongodb.example.json `
  --workdir work `
  --out output
```

Release behavior is source/configuration-specific. The committed integrated example intentionally pins NARA for reproducibility. For NARA follow-latest monitoring, use:

```json
"release_mode": "latest"
```

A deployment may keep separate pinned baseline and follow-latest monitoring configurations.

See:

- [`docs/NARA_ADAPTER_REQUIREMENTS.md`](docs/NARA_ADAPTER_REQUIREMENTS.md)
- [`../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md`](../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md)

## Common CLI modes

| Command | Purpose |
| --- | --- |
| `registry_builder run` | Source acquisition, reconciliation, mapping, persistence, change detection, exports. |
| `registry_builder validate` | Validate exported `registry.json`. |
| `registry_builder collision-report` | Inspect identifier collisions/heuristic bridges. |
| `registry_builder criterion-evidence-audit` | Read-only audit of source fields/projected criterion coverage. |
| `registry_builder mapping validate` | Validate criterion-mapping configuration. |
| `registry_builder criterion-claims backfill` | Rebuild criterion claims from stored evidence without reacquiring sources. |

Full command guide: [`docs/INSTALLATION_SETUP_AND_RUN.md`](docs/INSTALLATION_SETUP_AND_RUN.md).

## Storage and common interface

All persistence is behind `RegistryStore`:

```python
upsert(collection, key, document)
query(collection, filter)
```

Built-in backends:

```text
memory
file / json_file
mongodb
```

The sibling risk manager reuses the same store through `RegistryReader`; it does not duplicate MongoDB access logic.

Read:

- [`../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
- [`docs/STORAGE_AND_EXPORT_CONFIG.md`](docs/STORAGE_AND_EXPORT_CONFIG.md)
- [`docs/MONGODB_STORAGE_SCHEMA.md`](docs/MONGODB_STORAGE_SCHEMA.md)

## Source-by-source augmentation

A persistent registry can be updated one source at a time:

```text
NARA run -> refresh NARA contribution
PRONOM run -> refresh verified PUID/identity contribution
LOC run -> refresh FDD sustainability evidence
```

The current canonical view is recomputed from active source contributions; source history/provenance is retained.

Read [`docs/INCREMENTAL_SOURCE_UPDATES.md`](docs/INCREMENTAL_SOURCE_UPDATES.md).

## Criterion claims

Source adapters retain source-native vocabulary. Declarative mapping files convert only preservation-relevant source fields into neutral `criterion_claims` with provenance.

```text
source-native field/value
 -> approved mapping rule
 -> criterion_claim
 -> risk framework question
 -> deterministic answer/risk analysis
```

For a new source:

```text
ingest -> audit -> compare with criteria -> draft mapping -> validate
-> human approve -> dry-run backfill -> write claims -> verify in risk manager
```

Use [`docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md).

That guide also covers:

- external vs institution-scoped evidence;
- when to add a genuinely new neutral criterion;
- binding criteria into framework questions;
- AI-assisted mapping drafts;
- the dedicated DPC Bit List prompt.

Reusable DPC prompt:

```text
config/prompts/propose_mapping/dpc_bit_list.v1.md
```

## Adding sources/backends

External trusted source adapter:

```json
{
  "id": "future_source",
  "type": "mypkg.adapters.future:FutureAdapter",
  "enabled": true
}
```

Storage plugin:

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

Runtime/export directories are generated output and should not normally be committed.

Common paths:

```text
work/snapshots/<source_id>/
output/
```

## Tests

```powershell
cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"
pytest -q
```

For source/mapping changes, also run the smallest relevant real/configured pipeline and inspect the run/coverage report.

## Related module

Once criterion evidence is available, `preservation_risk_manager` can perform deterministic or AI-assisted assessment without duplicating ingestion/storage logic.

Start at [`../preservation_risk_manager/README.md`](../preservation_risk_manager/README.md).
