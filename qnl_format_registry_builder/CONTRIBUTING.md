# Contributing

This repository is a process for building a preservation-risk registry, not a place to commit generated registry outputs.

## Before pushing or merging

Run the test suite from the package directory:

```bash
cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"
pytest
```

A change should not be merged with a red test suite.

## What to test

At minimum, run all tests with `pytest` after changes to:

- source adapters;
- identifier normalization or reconciliation;
- incremental source update logic;
- hazard/risk assessment logic;
- storage backends;
- change detection;
- documentation examples that affect commands or config.

## Generated outputs

Do not commit normal pipeline outputs from `qnl_format_registry_builder/output/`.

These files are generated review/export products, not source material:

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

If a sample registry is needed for documentation, add it deliberately under `docs/examples/` with a note showing which config and command produced it.

## Local data

Do not commit local input files, work snapshots, MongoDB dumps, or institution-specific workbooks unless they are explicitly approved test fixtures.

Ignored local paths include:

```text
qnl_format_registry_builder/input/
qnl_format_registry_builder/work/
qnl_format_registry_builder/output/
```

## Documentation expectations

When behavior changes, update the document that matches the audience:

| Audience | Document |
| --- | --- |
| New user/operator | `README.md` |
| Preservation officer reading outputs | `docs/READING_THE_REGISTRY.md` |
| Developer implementing a source | `docs/ADAPTER_IMPLEMENTATION_GUIDE.md` |
| Operator configuring a built-in source | `docs/ADAPTER_REFERENCE.md` |
| Source-by-source update semantics | `docs/INCREMENTAL_SOURCE_UPDATES.md` |
| Identifier matching semantics | `docs/IDENTIFIER_RECONCILIATION.md` |
| MongoDB schema/details | `docs/MONGODB_STORAGE_SCHEMA.md` |
| Roadmap/future work | `docs/NEXT_STEPS.md` |

## Pull request checklist

Before requesting review, confirm:

- `pytest` passes locally;
- generated output files are not staged;
- new behavior has a regression test;
- user-facing terminology is consistent with the documentation map;
- source evidence, institutional decisions, and generated actions remain separate.
