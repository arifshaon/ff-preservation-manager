# QNL File Format Registry Builder

This project is a **registry-building system**, not a manually curated static registry.

It builds a local file-format preservation registry by running a repeatable pipeline over configured evidence sources such as NARA, PRONOM, LOC FDD, institutional policy spreadsheets, and future adapters.

The registry is the output of the process. The reusable workflow is the deliverable.

## What the pipeline does

```text
Source acquisition
  -> source snapshots
  -> extraction/parsing
  -> normalization
  -> identifier reconciliation
  -> canonical registry records
  -> storage
  -> assessment/change detection
  -> optional exports/reports
```

The system keeps these things separate:

- external source evidence;
- institutional policy and local decisions;
- hazard/risk assessment;
- trend evidence;
- readiness/method coverage;
- change events and review actions;
- optional export files.

## Documentation map

Start with [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md). It tells each audience where to go.

Key documents:

| Need | Read |
| --- | --- |
| Add or run a data source, including downloaded files, JSON, CSV, archives, and individual NARA/PRONOM/LOC runs | [`docs/ADDING_AND_RUNNING_DATA_SOURCES.md`](docs/ADDING_AND_RUNNING_DATA_SOURCES.md) |
| Interpret generated registry outputs | [`docs/READING_THE_REGISTRY.md`](docs/READING_THE_REGISTRY.md) |
| Understand architecture and adapter boundaries | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Understand source-by-source augmentation | [`docs/INCREMENTAL_SOURCE_UPDATES.md`](docs/INCREMENTAL_SOURCE_UPDATES.md) |
| Understand identifier matching and verified keys | [`docs/IDENTIFIER_RECONCILIATION.md`](docs/IDENTIFIER_RECONCILIATION.md) |
| Configure existing adapters | [`docs/ADAPTER_REFERENCE.md`](docs/ADAPTER_REFERENCE.md) |
| Build a new adapter | [`docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](docs/ADAPTER_IMPLEMENTATION_GUIDE.md) |
| Configure storage and exports | [`docs/STORAGE_AND_EXPORT_CONFIG.md`](docs/STORAGE_AND_EXPORT_CONFIG.md) |
| Understand MongoDB collections and fields | [`docs/MONGODB_STORAGE_SCHEMA.md`](docs/MONGODB_STORAGE_SCHEMA.md) |
| Understand institutional overlays | [`docs/INSTITUTIONAL_OVERLAYS.md`](docs/INSTITUTIONAL_OVERLAYS.md) |
| Review remaining roadmap | [`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md) |

## Installation

Requires Python 3.10 or later.

```bash
cd qnl_format_registry_builder
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -e ".[dev,mongo]"
pytest
```

## Quickstart: run a real multi-source registry build

The default config now enables three real evidence sources:

```text
NARA   -> pinned external preservation hazard evidence
PRONOM -> verified PUID and format-identity evidence
LOC    -> FDD XML sustainability/evidence records
```

NARA is required in the sample config. PRONOM and LOC are enabled but optional, so a temporary network or upstream issue is recorded in `run_report.json` without destroying the baseline run.

Full PRONOM acquisition uses one GitHub archive snapshot and extracts JSON records from it. It should not create thousands of per-record source snapshot files.

```bash
python -m registry_builder run \
  --config config/sources.example.json \
  --workdir work \
  --out output
```

On success, check the summary printed by the CLI and the report at:

```text
output/run_report.json
output/coverage_report.md
output/registry.csv
output/registry.json
```

The exact count depends on the pinned NARA release and the current PRONOM/LOC data. The run should produce a real external-evidence registry, not a two-record toy example.

Read the outputs with:

```text
docs/READING_THE_REGISTRY.md
```

For source-specific examples, including MongoDB configs for NARA-only, PRONOM-only, LOC-only, downloaded files, JSON, CSV, archives, and temporary many-file acquisition, read:

```text
docs/ADDING_AND_RUNNING_DATA_SOURCES.md
```

## What `--workdir` and `--out` mean

```text
--workdir work
```

Working/cache directory. Source snapshots are stored under `work/snapshots/<source_id>/` with hashes so acquisition is auditable and replayable.

For large bundled sources such as PRONOM and LOC, the snapshot should be one ZIP/archive, not thousands of individual files.

```text
--out output
```

Export/report directory. When `exports.enabled` is true, the pipeline writes files such as `registry.csv`, `registry.json`, `run_report.json`, and `coverage_report.md` there.

If the selected storage backend is MongoDB, MongoDB remains the registry store; `output/` is only the export/report folder.

## Add an institutional workbook after the external-evidence quickstart

The default NARA + PRONOM + LOC run shows that the pipeline works with real external evidence.

To make it institutional, enable the institutional workbook source in `config/sources.example.json` or in a local copied config:

```json
{
  "id": "qnl_policy_current",
  "type": "institution_policy_xlsx",
  "enabled": true,
  "institution_id": "qnl",
  "institution_name": "Qatar National Library",
  "uris": ["input/QNL File Format Policy and Action Plan_27_November_2025.xlsx"]
}
```

Copy the workbook into `input/`, then rerun the pipeline. The workbook data is imported as `institution_policy_overlays` attached to canonical format records.

For another institution, use the same adapter with that institution's own field mapping and terminology.

## Run with local MongoDB

Start MongoDB locally, then use a config with this storage block:

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry"
  },
  "exports": {
    "enabled": true
  }
}
```

Run:

```bash
python -m registry_builder run \
  --config config/sources.example.json \
  --workdir work \
  --out output
```

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

See [`docs/MONGODB_STORAGE_SCHEMA.md`](docs/MONGODB_STORAGE_SCHEMA.md) for fields, indexes, and verification queries.

## Source-by-source augmentation

The default behavior supports running sources one by one against the same store.

Example:

```text
Run NARA
  -> contributes external preservation hazard evidence

Run PRONOM later
  -> contributes verified PUID/format identity evidence
  -> reuses latest successful NARA evidence
  -> recomputes canonical records from active evidence contributions

Run LOC later
  -> contributes LOC FDD identifiers and sustainability evidence
  -> reuses latest successful NARA and PRONOM evidence
```

Earlier source records remain in storage as provenance/history. The current canonical view uses the active contribution from each source.

Read [`docs/INCREMENTAL_SOURCE_UPDATES.md`](docs/INCREMENTAL_SOURCE_UPDATES.md) before changing this behavior.

## External plugin loading

Built-in adapters and storage backends can be referenced by short names:

```json
{
  "type": "nara_digital_preservation_framework"
}
```

External packages can be referenced with an explicit `module:ClassName` plugin path:

```json
{
  "id": "dpc_bit_list",
  "type": "mypkg.adapters.dpc:DpcBitListAdapter",
  "enabled": true,
  "required": false
}
```

External storage backends use the same pattern:

```json
{
  "storage": {
    "type": "mypkg.storage.sql:SqlRegistryStore"
  }
}
```

Plugin paths are trusted-code configuration. Importing a plugin executes the plugin module's top-level Python code, so plugin paths should come only from reviewed packages and trusted configuration.

The resolver validates source plugins as `SourceAdapter` subclasses and storage plugins as `RegistryStore` subclasses.

## Identifier rules

New identifier namespaces are configured, not hardcoded:

```json
{
  "identifier_kinds": {
    "dpc": {
      "strength": "strong",
      "verified_from": ["dpc_bit_list"]
    }
  }
}
```

A third-party adapter can emit a DPC identifier claim without core model edits. Reconciliation will treat it according to the configured identifier rules.

Read [`docs/IDENTIFIER_RECONCILIATION.md`](docs/IDENTIFIER_RECONCILIATION.md) before changing matching behavior.

## Generated outputs are not committed

`output/` is ignored. It is a runtime/export directory.

Do not commit normal generated files such as:

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

If a sample is needed for documentation, commit it deliberately under `docs/examples/` and state which config and command produced it.

## Tests and contribution rules

Before pushing or merging:

```bash
cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"
pytest
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md). GitHub Actions also runs `pytest` on pushes to `main` and pull requests.
