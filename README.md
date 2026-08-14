# File Format Preservation Manager

File Format Preservation Manager is a repository for tools and workflows that help institutions record, assess, monitor, and manage file-format preservation risks. The focus is not only on listing file formats, but on maintaining evidence, risk assessments, decisions, recommended actions, change history, and operational follow-up work in a repeatable way.

The repository is intended to hold multiple related components. Each component should be self-contained, documented in its own directory, and usable on its own where possible.

## Repository structure

| Path | Status | Purpose |
| --- | --- | --- |
| [`qnl_format_registry_builder/`](qnl_format_registry_builder/) | Active implementation | Builds and updates a local preservation risk and action registry for file formats from authoritative and institutional sources. |
| Future modules | Planned as needed | Additional preservation-management tools can be added as separate top-level components. |

At the moment, `qnl_format_registry_builder` is the main implemented component.

## Component: `qnl_format_registry_builder`

`qnl_format_registry_builder` is a registry-building system, not a manually curated static registry.

It runs a repeatable pipeline over configured sources such as:

- NARA Digital Preservation Framework releases;
- PRONOM registry data;
- PRONOM/DROID XML signature data;
- LOC FDD XML records;
- institutional file-format policy workbooks;
- structured JSON source packages;
- future third-party adapters loaded by explicit `module:ClassName` plugin path.

The output is a queryable local registry for preservation risk management, action planning, source evidence, and change tracking, plus optional review/export files.

### What it does

```text
Source acquisition
  -> content-addressed snapshots
  -> extraction into RawFormatRecord objects
  -> identifier normalization
  -> conservative reconciliation
  -> hazard/readiness/trend assessment
  -> method-profile assignment
  -> storage through a selected RegistryStore backend
  -> baseline/change detection
  -> optional exports and reports
```

### Main capabilities

- Source-adapter architecture for institutional and external sources.
- Snapshot cache under `work/snapshots/<source_id>/`.
- Offline replay from cached snapshots using `--offline`.
- Admin/local-file source mode for manually downloaded source files.
- NARA release modes: `pinned`, `latest`, `explicit_uris`, and `local_files`.
- Optional-source handling using `required:true/false`.
- Configurable identifier authority and strong-key matching rules.
- Generic identifier namespaces, so new sources do not need new model fields.
- Source-owned native hazard scale/direction metadata.
- Source-by-source augmentation using active evidence contributions.
- Pluggable source adapters and storage backends through short names or explicit `module:ClassName` plugin paths.
- Storage backends: memory, file/JSON document store, and MongoDB.
- Optional exports: JSON, JSONL, CSV, SQLite, Markdown reports.
- Change detection between runs, including bulk-change collapse into source-level events.

## Where to start

| Need | Document |
| --- | --- |
| Run the format registry builder | [`qnl_format_registry_builder/README.md`](qnl_format_registry_builder/README.md) |
| Find the right documentation page | [`qnl_format_registry_builder/docs/DOCUMENTATION_MAP.md`](qnl_format_registry_builder/docs/DOCUMENTATION_MAP.md) |
| Interpret registry outputs and review fields | [`qnl_format_registry_builder/docs/READING_THE_REGISTRY.md`](qnl_format_registry_builder/docs/READING_THE_REGISTRY.md) |
| Understand architecture and source-adapter boundaries | [`qnl_format_registry_builder/docs/ARCHITECTURE.md`](qnl_format_registry_builder/docs/ARCHITECTURE.md) |
| Understand source-by-source augmentation | [`qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md`](qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md) |
| Understand verified identifier reconciliation | [`qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md`](qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md) |
| Configure existing adapters | [`qnl_format_registry_builder/docs/ADAPTER_REFERENCE.md`](qnl_format_registry_builder/docs/ADAPTER_REFERENCE.md) |
| Implement a new adapter/backend | [`qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md) |
| Understand source retrieval, cache, offline mode, and fallbacks | [`qnl_format_registry_builder/docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md`](qnl_format_registry_builder/docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md) |
| Configure storage and exports | [`qnl_format_registry_builder/docs/STORAGE_AND_EXPORT_CONFIG.md`](qnl_format_registry_builder/docs/STORAGE_AND_EXPORT_CONFIG.md) |
| Understand MongoDB collections and fields | [`qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md) |
| Contribute safely | [`qnl_format_registry_builder/CONTRIBUTING.md`](qnl_format_registry_builder/CONTRIBUTING.md) |

## Quick start for the current component

```bash
cd qnl_format_registry_builder
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -e ".[dev,mongo]"
pytest
```

Run the default NARA quickstart:

```bash
python -m registry_builder run \
  --config config/sources.example.json \
  --workdir work \
  --out output
```

The default config downloads the pinned public NARA Digital Preservation Framework CSVs from GitHub and produces a real registry with external hazard evidence.

Read the generated outputs with:

```text
qnl_format_registry_builder/docs/READING_THE_REGISTRY.md
```

Run from cached snapshots only after an online run has populated the cache:

```bash
python -m registry_builder run \
  --config config/sources.example.json \
  --workdir work \
  --out output \
  --offline
```

## Development conventions for new modules

New top-level modules should follow this pattern:

```text
module_name/
  README.md
  docs/
  config/
  tests/
  src or package directory
```

Each module README should explain:

1. what the module does;
2. what problem it solves;
3. how to install and run it;
4. expected inputs and outputs;
5. configuration examples;
6. how it relates to other modules in this repository;
7. where the deeper implementation documentation lives.

The root README should then be updated with one concise row in the repository-structure table and a short component summary.

## Current maturity

This repository currently contains one active, implemented component: `qnl_format_registry_builder`.

That component is suitable for local testing and iterative registry population. Production use should pin configuration, run the test suite, use a persistent storage backend such as MongoDB or file storage, and keep source snapshots for audit and replay.
