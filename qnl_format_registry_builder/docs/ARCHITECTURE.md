# File Format Registry Builder Architecture

## Purpose

This project does **not** manually curate a static file-format registry.

It implements a repeatable, configurable process that builds and updates a local file-format registry from authoritative and institution-specific sources. The registry is a generated, queryable product of the workflow, not the primary manual deliverable.

The design supports a general institutional requirement:

> Given a file format at any time, the system should report its current hazard/risk position, supporting evidence, trend signals where available, local institutional readiness, local exposure, and recommended follow-up actions.

QNL is the first institutional profile, but the core architecture must also support other libraries, archives, repositories, and memory institutions.

---

## Architectural principles

### 1. The registry is built, not hand-maintained

The system should be rerunnable when upstream sources change, for example when PRONOM, LOC, NARA, DPC, or institutional policy data changes.

Each run should:

1. acquire configured sources;
2. extract source-specific file-format records;
3. normalize records into a common representation;
4. reconcile records across sources;
5. persist the queryable local registry;
6. calculate or refresh assessment outputs;
7. generate optional exports and reports.

### 2. Institutional policy is an overlay, not the boundary of the registry

A local spreadsheet represents one institution's current policy position for known formats. It is not the universe of all formats.

The canonical registry may include:

- formats from an institutional policy workbook;
- formats from PRONOM/DROID signatures;
- formats from LOC FDD records;
- formats from NARA Digital Preservation Framework data;
- formats from DPC or other preservation sources;
- formats discovered later in local collections;
- manually supplied source packages.

Institution-specific fields are stored as `institution_policy_overlays` attached to canonical format records.

See [`INSTITUTIONAL_OVERLAYS.md`](INSTITUTIONAL_OVERLAYS.md) for details.

### 3. Keep risk dimensions separate

The system must not collapse hazard, exposure, readiness, trend, uncertainty, and work actions into a single opaque score.

The model keeps these axes separate:

- **Hazard**: intrinsic preservation hazard of the format.
- **Trend**: current observable direction of risk indicators, where evidence exists.
- **Exposure**: institutional holdings count, growth, and collection significance.
- **Readiness**: the institution's ability to identify, validate, render, migrate, or otherwise manage the format.
- **Confidence**: completeness and reliability of evidence.
- **Assessment changes**: event records that generate recommended work items.

This avoids common errors such as treating uncertainty as risk, using holdings as intrinsic format risk, or allowing a tested conversion pathway to make the format itself appear safer.

### 4. Reconcile estimators; do not add them

External authoritative assessments and local institutional criteria estimate the same underlying hazard. They should be reconciled, not summed.

Example:

```text
External hazard estimator: High
Institutional estimator: Moderate
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
Retest conversion pathway
Update institutional action-plan note
Create and test preservation pathway
Review external-vs-institutional hazard divergence
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

- institution policy XLSX files;
- standardized JSON source packages;
- PRONOM/DROID XML signatures;
- LOC FDD XML records;
- future NARA Linked Open Data adapter;
- future DPC Bit List adapter.

Source adapters should not write directly to the registry. They only produce source snapshots and raw extracted records.

The preferred policy spreadsheet adapter is:

```text
institution_policy_xlsx
```

The old `qnl_policy_xlsx` adapter name remains as a deprecated compatibility alias.

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
institution_policy_overlays
hazard_assessments
readiness_assessments
trend_observations
assessment_changes
```

### `canonical_formats`

Stores stable canonical format identity.

Example summary fields:

```json
{
  "canonical_id": "puid-fmt-353",
  "preferred_name": "Tagged Image File Format",
  "category": "Still Image",
  "current_summary": {
    "has_institution_policy": true,
    "hazard_band": "Low",
    "readiness_state": "Covered",
    "trend_direction": "Insufficient Evidence"
  }
}
```

### `institution_policy_overlays`

Stores an institution's local policy position imported from a spreadsheet or future local policy source.

This is where local format IDs, local risk terms, preservation action, proposed plan, preferred tools, and conversion process belong.

QNL-specific values belong here only as data:

```json
{
  "institution_id": "qnl",
  "institution_name": "Qatar National Library",
  "institution_format_id": "QNL_095_Chemical_Markup_Language_(CML)",
  "local_risk_level": "Moderate Risk"
}
```

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
    institution_policy_xlsx.py
    qnl_policy_xlsx.py        # deprecated compatibility alias
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
    "database": "format_registry"
  },
  "sources": [
    {
      "id": "qnl_policy_current",
      "type": "institution_policy_xlsx",
      "enabled": true,
      "institution_id": "qnl",
      "institution_name": "Qatar National Library",
      "uris": ["input/QNL File Format Policy and Action Plan_27_November_2025.xlsx"],
      "field_map": {
        "institution_format_id": ["QNL Format ID"],
        "name": ["Digital file"],
        "extensions": ["File Extension(s)"]
      }
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
    def save_institution_policy_overlay(self, record): ...
    def save_hazard_assessment(self, record): ...
    def save_readiness_assessment(self, record): ...
    def save_trend_observation(self, record): ...
    def save_assessment_change(self, record): ...
    def get_current_registry_view(self): ...
    def find_by_identifier(self, identifier_type, value): ...
    def list_institution_policy_formats(self, institution_id=None): ...
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

1. Finish refactoring `pipeline.py` so it writes through `RegistryStore` rather than file writers directly.
2. Implement the MongoDB storage adapter.
3. Move JSON/CSV/SQLite/Markdown output into export adapters.
4. Add the NARA adapter while preserving NARA's native numeric rating alongside normalized bands.
5. Add tests for the MongoDB adapter and configurable export registry.
