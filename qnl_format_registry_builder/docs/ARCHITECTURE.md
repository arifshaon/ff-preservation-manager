# QNL File Format Registry Builder Architecture

## Purpose

This project does **not** manually curate a static file-format registry.

It implements a repeatable, configurable process that builds and updates a local file-format registry from authoritative and institution-specific sources. The registry is a generated, queryable product of the workflow, not the primary manual deliverable.

The design supports the core QNL requirement:

> Given a file format at any time, the system should be able to report its current QNL-aligned hazard/risk position, supporting evidence, trend signals where available, QNL readiness, exposure, and recommended follow-up actions.

The implementation must remain maintainable as sources, storage technologies, export formats, and assessment rules evolve.

---

## Architectural principles

### 1. The registry is built, not hand-maintained

The system should be rerunnable when upstream sources change, for example when PRONOM, LOC, NARA, DPC, or QNL policy data changes.

Each run should:

1. acquire configured sources;
2. extract source-specific file-format records;
3. normalize records into a common representation;
4. reconcile records across sources;
5. persist the queryable local registry;
6. calculate or refresh assessment outputs;
7. generate optional exports and reports.

### 2. QNL policy is an overlay, not the boundary of the registry

The QNL spreadsheet represents QNL's current institutional policy position for known formats. It is not the universe of all formats.

The canonical registry may include:

- formats from QNL policy;
- formats from PRONOM/DROID signatures;
- formats from LOC FDD records;
- formats from NARA Digital Preservation Framework data;
- formats from DPC or other preservation sources;
- formats discovered later in QNL collections;
- manually supplied source packages.

QNL-specific fields are stored as an overlay attached to canonical format records.

### 3. Keep risk dimensions separate

The system must not collapse hazard, exposure, readiness, trend, uncertainty, and work actions into a single opaque score.

The model keeps these axes separate:

- **Hazard**: intrinsic preservation hazard of the format.
- **Trend**: current observable direction of risk indicators, where evidence exists.
- **Exposure**: QNL holdings count, growth, and collection significance.
- **Readiness**: QNL's ability to identify, validate, render, migrate, or otherwise manage the format.
- **Confidence**: completeness and reliability of evidence.
- **Assessment changes**: event records that generate recommended work items.

This avoids common errors such as treating uncertainty as risk, using QNL holdings as intrinsic format risk, or allowing a tested conversion pathway to make the format itself appear safer.

### 4. Reconcile estimators; do not add them

External authoritative assessments and QNL criteria estimate the same underlying hazard. They should be reconciled, not summed.

Example:

```text
External hazard estimator: High
QNL criteria estimator: Moderate
Result: divergence detected; review required
```

Divergence is a finding. It should be surfaced rather than averaged away.

### 5. States and tasks are different

Stable states should not be mixed with work items.

Example stable readiness/coverage states:

```text
Covered
Partially Covered
Uncovered
Blocked
Not Assessed
```

Example event-driven recommended actions:

```text
Retest LibreOffice-to-PDF/A pathway
Update QNL action-plan note
Create and test preservation pathway
Review external-vs-QNL hazard divergence
```

Recommended actions belong in assessment/change records, not in the stable state enum.

---

## Pipeline overview

```text
Source adapters
  ↓
Source snapshots
  ↓
Extraction and normalization
  ↓
Source records with raw + normalized payloads
  ↓
Reconciliation service
  ↓
Storage adapter: queryable local registry
  ↓
Assessment and change-detection services
  ↓
Export adapters: optional file/API/report outputs
```

---

## Adapter-based design

The project uses three adapter families.

### 1. Source adapters

Source adapters acquire and parse upstream sources.

Examples:

- QNL policy XLSX
- standardized JSON source packages
- PRONOM/DROID XML signatures
- LOC FDD XML records
- future NARA Linked Open Data adapter
- future DPC Bit List adapter

Source adapters should not write directly to the registry. They only produce source snapshots and raw extracted records.

### 2. Storage adapters

Storage adapters persist the queryable registry and assessment history.

Initial backend:

- MongoDB

Possible future backends:

- PostgreSQL
- MySQL
- SQLite
- file-backed local store
- in-memory test store

Pipeline services must talk to the `RegistryStore` interface, not directly to MongoDB. This keeps the storage backend replaceable.

### 3. Export adapters

Export adapters generate optional outputs from the current registry view.

Examples:

- JSON
- JSONL
- CSV
- SQLite
- Markdown reports
- API bundle

Exports are not the source of truth. They are generated views used for review, sharing, auditing, offline use, or interoperability.

---

## Storage model

MongoDB is the initial live/queryable local registry store. File outputs remain optional exports.

Recommended collections:

```text
runs
source_snapshots
source_records
canonical_formats
format_identifiers
qnl_policy_overlays
hazard_assessments
readiness_assessments
trend_observations
assessment_changes
```

### `runs`

One document per pipeline execution.

Stores:

- run identifier;
- start and finish time;
- source configuration hash;
- pipeline version;
- status;
- counts and warnings.

### `source_snapshots`

Stores metadata about acquired sources.

For large upstream files, store file path, URI, hash, and retrieval metadata rather than duplicating the entire payload unnecessarily.

### `source_records`

Stores source-specific extracted records.

Each record should include both:

- `raw`: source-specific extraction payload;
- `normalized`: internal normalized representation.

This avoids maintaining separate raw and normalized staging collections unless later scale requires it.

### `canonical_formats`

Stores stable canonical format identity.

This collection should contain stable summary fields and a current query summary, not all historical evidence.

Example summary fields:

```json
{
  "canonical_id": "puid-fmt-353",
  "preferred_name": "Tagged Image File Format",
  "category": "Still Image",
  "current_summary": {
    "has_qnl_policy": true,
    "hazard_band": "Low",
    "readiness_state": "Covered",
    "trend_direction": "Insufficient Evidence"
  }
}
```

### `format_identifiers`

Stores identifiers separately so a format can have multiple extensions, MIME types, PUIDs, LOC IDs, NARA IDs, and other identifiers.

### `qnl_policy_overlays`

Stores QNL's policy position imported from the spreadsheet or future QNL policy sources.

This is where QNL format IDs, existing QNL risk terms, preservation action, proposed plan, preferred tools, and conversion process belong.

### `hazard_assessments`

Stores intrinsic hazard assessments.

Do not mix hazard with exposure, readiness, or work priority.

### `readiness_assessments`

Stores QNL readiness/coverage information.

Examples:

- pathway exists;
- pathway tested;
- tool/version;
- last verification date;
- tool health.

### `trend_observations`

Stores trend evidence, where connectors exist.

Minimum trend indicators:

- specification vitality;
- implementation vitality;
- authority warnings.

Until trend connectors exist, trend should truthfully report `Insufficient Evidence`.

### `assessment_changes`

Stores change events and recommended actions.

This is where work items belong.

---

## Export model

Exports are generated from the storage adapter's current registry view.

The export layer should be configuration-driven:

```json
{
  "exports": [
    { "type": "json", "enabled": true, "path": "output/latest/registry.json" },
    { "type": "jsonl", "enabled": true, "path": "output/latest/registry.jsonl" },
    { "type": "csv", "enabled": true, "path": "output/latest/registry.csv" },
    { "type": "sqlite", "enabled": false, "path": "output/latest/registry.sqlite" },
    { "type": "markdown_report", "enabled": true, "path": "output/latest/coverage_report.md" }
  ]
}
```

If an export adapter exists and is enabled, the pipeline writes that export. Otherwise it does not.

No export should update the registry.

---

## Proposed package structure

```text
registry_builder/
  adapters/
    base.py
    standard_json.py
    qnl_policy_xlsx.py
    pronom_droid_xml.py
    loc_fdd_xml.py

  storage/
    __init__.py
    base.py
    mongo.py
    memory.py

  exporters/
    __init__.py
    base.py
    json_exporter.py
    jsonl_exporter.py
    csv_exporter.py
    sqlite_exporter.py
    markdown_reporter.py

  services/
    normalization.py
    reconciliation.py
    assessment.py
    change_detection.py

  domain/
    models.py
    hazard.py
    enums.py
    provenance.py

  pipeline.py
  cli.py
```

The current implementation may still keep some modules at top level while it is being refactored. The target structure above should guide the next development phase.

---

## Configuration model

A single pipeline config may contain:

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "qnl_format_registry"
  },
  "sources": [
    {
      "id": "qnl_policy_current",
      "type": "qnl_policy_xlsx",
      "enabled": true,
      "uris": ["input/QNL File Format Policy and Action Plan_27_November_2025.xlsx"]
    }
  ],
  "exports": [
    {
      "type": "json",
      "enabled": true,
      "path": "output/latest/registry.json"
    }
  ]
}
```

---

## Interfaces

### RegistryStore

The pipeline should depend on a storage interface like this:

```python
class RegistryStore:
    def create_run(self, run): ...
    def save_snapshot(self, snapshot): ...
    def save_source_record(self, record): ...
    def upsert_canonical_format(self, record): ...
    def upsert_identifier(self, record): ...
    def save_qnl_policy_overlay(self, record): ...
    def save_hazard_assessment(self, record): ...
    def save_readiness_assessment(self, record): ...
    def save_trend_observation(self, record): ...
    def save_assessment_change(self, record): ...
    def get_current_registry_view(self): ...
    def find_by_identifier(self, identifier_type, value): ...
    def list_qnl_policy_formats(self): ...
    def list_changes_since(self, since): ...
```

### RegistryExporter

Exporters should implement:

```python
class RegistryExporter:
    def export(self, registry_view, context): ...
```

---

## Rules to prevent redundancy

1. MongoDB is the initial source of truth for the queryable local registry.
2. File outputs are exports only.
3. SQLite is an export adapter unless explicitly configured as a storage adapter in the future.
4. Source adapters never write directly to canonical registry collections.
5. Export adapters never update storage.
6. Pipeline orchestration should be thin; storage/export details belong in adapters.
7. Historical evidence and assessments should be stored separately from canonical format summaries.
8. `canonical_formats` may store current summary fields for fast lookup, but not full historical assessment history.

---

## Immediate next implementation tasks

1. Add `storage/base.py`, `storage/memory.py`, and `storage/mongo.py`.
2. Add `exporters/base.py` and move JSON/CSV/SQLite/Markdown output into export adapters.
3. Refactor `pipeline.py` so it writes through `RegistryStore`.
4. Update config to include `storage` and `exports` sections.
5. Keep the existing output files as demo exports, not registry authority.
6. Add tests for the in-memory store and exporter registry.
7. Add a MongoDB integration test that can be skipped when MongoDB is unavailable.
