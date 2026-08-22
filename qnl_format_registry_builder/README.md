# QNL File Format Registry Builder

`qnl_format_registry_builder` is the evidence-ingestion and registry-maintenance module of File Format Preservation Manager.

It acquires preservation-data sources, retains source snapshots/provenance, extracts source-native records, reconciles file-format identities conservatively, maps reviewed evidence, and persists the current registry while retaining history.

For repository-wide documentation, start at **[`../docs/README.md`](../docs/README.md)**.

## What this module owns

```text
source acquisition
 -> SourceSnapshot
 -> RawFormatRecord
 -> authority-aware identifier reconciliation
 -> CanonicalFormat
 -> criterion / risk / relationship evidence
 -> RegistryStore
 -> change detection + provenance
```

Normal registry writes and source updates belong here. The sibling Risk Manager normally reads the resulting registry and does not rewrite source evidence.

## Install

Python 3.10+.

With MongoDB support:

```powershell
cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"
pytest -q
```

Without MongoDB:

```powershell
python -m pip install -e ".[dev]"
```

Unified installation guide: [`../docs/INSTALLATION.md`](../docs/INSTALLATION.md).

## Current integrated sources

| Source | Source ID | Primary role |
| --- | --- | --- |
| PRONOM | `pronom_registry` | PUID identity / technical format data |
| LOC FDD | `loc_fdd_xml` | FDD identity + reviewed sustainability evidence |
| NARA | `nara_digital_preservation_framework` | NARA identity + native preservation risk/action evidence |
| DPC Global Bit List | `dpc_bit_list_2025` | Risk/context evidence only |
| Wikidata | controlled `wikidata_file_formats` workflow | Contextual cross-registry relationships only |
| QNL/local | institution-specific workflows | Local policy/readiness/evidence |

Exact upstream URLs, release policies and refresh procedures: [`../docs/sources/README.md`](../docs/sources/README.md).

## Refresh a selected source

Example:

```powershell
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source pronom_registry `
  --workdir work `
  --out output `
  --report monitoring\pronom-refresh.json
```

The refresh is incremental: it replaces the refreshed source's active contribution and reuses the latest successful evidence from sources not refreshed in the run.

Wikidata uses a separate guarded preflight/apply refresh. See [`../docs/sources/WIKIDATA.md`](../docs/sources/WIKIDATA.md).

Full operator workflow: [`../docs/OPERATIONS.md`](../docs/OPERATIONS.md).

## Add a source

Use the A-to-Z onboarding guide:

**[`../docs/HOW_TO_ADD_A_SOURCE.md`](../docs/HOW_TO_ADD_A_SOURCE.md)**

A complete source integration must document authority/scope, exact upstream location, update semantics, native fields, identifier rules, mappings, tests and Risk Manager consumer behavior.

## Core configuration

```text
config/sources.qnl.json
config/criteria/v1.json
config/criterion_mappings/
```

The source configuration controls acquisition and storage. Criteria/mapping configuration controls reviewed normalization of preservation observations. Overall Risk Manager synthesis policy lives in the Risk Manager module and does not belong in source adapter code.

## Storage

Normal persistent database:

```text
MongoDB database: qnl_format_registry
```

The logical persistence boundary is `RegistryStore`; file/memory/plugin backends are also supported.

- Data model: [`../docs/DATA_MODEL.md`](../docs/DATA_MODEL.md)
- MongoDB physical schema: [`docs/MONGODB_STORAGE_SCHEMA.md`](docs/MONGODB_STORAGE_SCHEMA.md)

## Advanced reference

The module `docs/` directory contains deep implementation references rather than a second documentation starting point.

Useful documents include:

- [`docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](docs/ADAPTER_IMPLEMENTATION_GUIDE.md)
- [`docs/IDENTIFIER_RECONCILIATION.md`](docs/IDENTIFIER_RECONCILIATION.md)
- [`docs/criterion_mapping_workflow.md`](docs/criterion_mapping_workflow.md)
- [`docs/INCREMENTAL_SOURCE_UPDATES.md`](docs/INCREMENTAL_SOURCE_UPDATES.md)
- [`docs/PERSISTENT_INTEGRATION.md`](docs/PERSISTENT_INTEGRATION.md) — clean-room/current production integration detail
- [`docs/WIKIDATA_PRODUCTION_INTEGRATION.md`](docs/WIKIDATA_PRODUCTION_INTEGRATION.md)

## Tests

```powershell
pytest -q
```

After a source/config change, also run the smallest relevant real/configured acquisition and review its source/run/change report before touching the maintained production registry.
