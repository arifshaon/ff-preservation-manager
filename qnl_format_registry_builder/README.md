# QNL File Format Registry Builder

This project is a **registry-building system**, not a manually curated static registry.

It builds a local file-format registry by running a repeatable pipeline over configured source datasets such as the QNL policy spreadsheet, PRONOM/DROID XML, LOC FDD XML, NARA or other standardized source packages, and future adapters.

## Core principle

The registry is an output of the process. The deliverable is the workflow that can be rerun when upstream sources change.

Pipeline stages:

```text
Source acquisition → extraction/parsing → normalization → matching/reconciliation → validation → registry generation → reporting
```

## Why this structure

The pipeline follows the agreed QNL model:

- QNL's current spreadsheet is treated as a **QNL policy overlay**, not as the boundary of all known file formats.
- External sources and QNL criteria are not added together as one risk score.
- Hazard, trend, exposure, readiness, confidence, and provenance remain separate axes.
- Future change reports should generate work items from change events rather than mixing tasks into state labels.

## Current implementation status

This starter implementation includes:

- source-adapter architecture;
- repeatable local runs from a JSON config file;
- immutable source snapshots with SHA-256 hashes;
- source extraction adapters for:
  - standardized JSON source packages;
  - QNL policy XLSX files;
  - PRONOM/DROID XML signature files;
  - LOC FDD XML records;
- normalization of extensions, MIME types, PUIDs, LOC IDs and related identifiers;
- conservative identifier-led reconciliation;
- JSON, JSONL, CSV and SQLite registry outputs;
- coverage reporting;
- validation checks;
- tests for reconciliation and hazard-reconciliation logic.

## Installation

Requires Python 3.10 or later. The runtime uses only the Python standard library.

```bash
cd qnl_format_registry_builder
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e .
```

For tests:

```bash
python -m pip install -e .[dev]
pytest
```

## Running the sample pipeline

```bash
python -m registry_builder run \
  --config config/sources.example.json \
  --workdir work \
  --out output
```

Outputs:

```text
output/registry.json
output/registry.jsonl
output/registry.csv
output/registry.sqlite
output/source_snapshots.json
output/coverage_report.md
output/run_report.json
```

## Running against the QNL policy workbook

1. Copy the workbook into `input/`, for example:

```text
input/QNL File Format Policy and Action Plan_27_November_2025.xlsx
```

2. Edit `config/sources.example.json` and set this source to `enabled: true`:

```json
{
  "id": "qnl_policy_current",
  "type": "qnl_policy_xlsx",
  "enabled": true,
  "uris": ["input/QNL File Format Policy and Action Plan_27_November_2025.xlsx"]
}
```

3. Run the pipeline:

```bash
python -m registry_builder run --config config/sources.example.json --workdir work --out output
```

The QNL workbook content will be imported as `qnl_policy_overlay` attached to canonical format records.

## Source adapter pattern

Each adapter implements two methods:

```python
acquire() -> list[SourceSnapshot]
extract(snapshots) -> list[RawFormatRecord]
```

This keeps source-specific behaviour isolated. To add NARA, DPC, COPTR, PAR, or other sources later, add a new adapter and register it in `registry_builder/adapters/__init__.py`.

## Standardized source package

Manual, tool-generated, or AI-extracted source data can be supplied through the `standard_json` adapter.

Example structure:

```json
{
  "records": [
    {
      "name": "PDF/A-1",
      "category": "Document",
      "identifiers": {
        "extension": ["pdf"],
        "mime": ["application/pdf"],
        "puid": ["fmt/95"],
        "loc": ["fdd000125"]
      },
      "urls": {
        "loc": "https://www.loc.gov/preservation/digital/formats/fdd/fdd000125.shtml"
      },
      "hazard": {
        "external_band": "Low",
        "external_rating": 1.0
      },
      "readiness": {
        "coverage_state": "Covered"
      },
      "trend": {
        "direction": "Insufficient Evidence"
      }
    }
  ]
}
```

## Important next implementation steps

This starter system builds the registry foundation. The next stages should add:

1. NARA Linked Open Data adapter, with hazard labels imported as external hazard estimators.
2. DPC Bit List adapter, preferably as category-level authority warnings rather than direct format hazard.
3. QNL hazard-rubric engine using hazard-answer tables.
4. Assessment-run and change-detection logic.
5. Trend connectors for specification vitality, implementation vitality and authority warnings.
6. Provenance logging for any AI-assisted extraction, including model, prompt version, source IDs, citations, confidence and abstentions.
7. FastAPI service over the generated registry and assessment outputs.

## Design note on risk terminology

The generated registry should not collapse all decision axes into a single operational risk number.

Use:

```text
hazard.band         = Low / Moderate / High
trend.direction     = Stable / Increasing / Decreasing / Insufficient Evidence
readiness.coverage  = Covered / Partially Covered / Uncovered / Blocked / Not Assessed
exposure            = holdings and significance data
recommended_action  = generated from change events
```

A policy sentence should be composed from separate axes, for example:

```text
High hazard; currently covered by a tested pathway; monitor implementation vitality.
```

not:

```text
Moderate operational risk.
```
