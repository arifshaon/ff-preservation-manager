# File Format Registry Builder Architecture

## Purpose

This project does **not** manually curate a static file-format registry.

It implements a repeatable, configurable process that builds and updates a local file-format registry from authoritative and institution-specific sources. The registry is a generated, queryable product of the workflow, not the primary manual deliverable.

The design supports a general institutional requirement:

> Given a file format at any time, the system should report its current hazard/risk position, supporting evidence, trend signals where available, local institutional readiness, local exposure, and recommended follow-up actions.

QNL is the first institutional profile, but the core architecture must also support other libraries, archives, repositories, and memory institutions.

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

The canonical registry may include formats from an institutional workbook, PRONOM, LOC FDD, NARA, DPC, local collection discovery, or manually supplied source packages.

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

## Adapter-based design

The project uses three adapter families: source adapters, storage adapters, and export adapters.

### Source adapters

Source adapters are **source-first, not file-format-first**.

A source adapter represents an authority or institutional source such as PRONOM, NARA, LOC, DPC, or an institutional policy workbook. The source may currently publish CSV, XLSX, XML, JSON, API responses, linked data, or HTML. Those are retrieval/parsing modes, not the conceptual source boundary.

```text
source adapter
  -> acquire source material
  -> snapshot acquired source material
  -> parse current representation
  -> emit RawFormatRecord objects
```

Every source adapter follows the same two-stage lifecycle:

```python
acquire() -> list[SourceSnapshot]
extract(snapshots) -> list[RawFormatRecord]
```

`acquire()` handles source material and snapshots it. `extract()` parses only the snapshots it receives and should not fetch the network. This keeps offline replay and audit runs reproducible.

Source adapters do **not** write to MongoDB, JSON, CSV, or SQLite directly. They only produce source snapshots and raw extracted records. Persistence belongs to the storage layer.

Preferred source-level names include:

```text
nara_digital_preservation_framework
pronom_registry
loc_fdd_xml
institution_policy_xlsx
```

Representation-specific names are acceptable only as compatibility aliases or deliberately narrow modes:

```text
nara_preservation_csv      # deprecated alias; CSV is NARA's current retrieval mode
pronom_droid_xml           # representation-specific DROID signature XML parser
qnl_policy_xlsx            # deprecated alias for institution_policy_xlsx
```

For building a new adapter, read [`ADAPTER_IMPLEMENTATION_GUIDE.md`](ADAPTER_IMPLEMENTATION_GUIDE.md). For configuring existing adapters, read [`ADAPTER_REFERENCE.md`](ADAPTER_REFERENCE.md).

### Snapshot cache, offline mode, and local files

Source acquisition uses a content-addressed snapshot cache under:

```text
work/snapshots/<source_id>/
```

Each source keeps a `.snapshot_index.json` mapping source URI or local source path to the latest cached SHA-256 and local snapshot path.

Online mode checks the upstream source and reports whether each snapshot changed. Offline mode replays only already-cached snapshots and fails clearly if requested material is not cached.

Local/admin files are different from offline replay:

```text
--offline
  replay previously cached snapshots

local_files
  treat local files as this run's source material and snapshot them
```

Read [`SOURCE_RETRIEVAL_AND_FALLBACKS.md`](SOURCE_RETRIEVAL_AND_FALLBACKS.md) for the full retrieval model.

### Required and optional sources

A required source failure aborts the run. An optional source failure is recorded in the source summary and the run continues with the remaining sources.

Use `required:true` for sources that define the purpose of the run. Use `required:false` for enrichment or external authority sources that should not destroy an otherwise useful run during an outage.

### Storage adapters

Storage adapters persist the queryable registry and assessment history.

Implemented backends:

```text
memory
file / json_file
mongodb
```

Pipeline services depend on the `RegistryStore` interface, not directly on MongoDB. This keeps the storage backend replaceable.

Read [`STORAGE_AND_EXPORT_CONFIG.md`](STORAGE_AND_EXPORT_CONFIG.md) and [`MONGODB_STORAGE_SCHEMA.md`](MONGODB_STORAGE_SCHEMA.md) for current storage behavior.

### Export adapters and file outputs

Exports are optional outputs from the current run. They are used for review, sharing, auditing, offline use, or interoperability.

Examples:

```text
JSON
JSONL
CSV
SQLite
Markdown reports
```

Exports are not the source of truth. No export should update the registry.

## Storage model

MongoDB is the initial production live/queryable local registry store. File outputs remain optional exports.

Core collections:

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

Stores stable canonical format identity and the current embedded assessment summary.

Example summary fields:

```json
{
  "canonical_id": "puid-fmt-353",
  "preferred_name": "Tagged Image File Format",
  "category": "Still Image",
  "identifiers": {"puid": ["fmt/353"], "extension": ["tif", "tiff"]},
  "hazard_assessment": {"band": "Low", "basis": "external_only"},
  "current": true
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

## Incremental source updates

Source-by-source registry population is supported. A NARA run can contribute NARA evidence, a later PRONOM run can contribute PRONOM evidence, and the canonical registry is recomputed from active evidence contributions.

The current run contributes new evidence. Stored evidence from sources that did not run this time can be used for augmentation. Earlier source records remain preserved as run history and provenance.

Read [`INCREMENTAL_SOURCE_UPDATES.md`](INCREMENTAL_SOURCE_UPDATES.md) before changing this behavior.

## Identifier reconciliation

Identifiers are evidence claims with provenance. Strong reconciliation is allowed only for configured strong identifier namespaces and verified authority sources.

For example, a PUID from PRONOM can be a verified strong key. A PUID copied from an institutional spreadsheet is still useful evidence, but it should not automatically have the same authority.

Read [`IDENTIFIER_RECONCILIATION.md`](IDENTIFIER_RECONCILIATION.md) before changing identifier normalization or adapter identifier output.

## Reading outputs

The registry outputs contain terms that are easy to misread, including `institution_override`, `no_estimator_available`, `Partially Covered`, `Insufficient Evidence`, and source-native ratings such as NARA numeric scores.

Preservation officers should start with [`READING_THE_REGISTRY.md`](READING_THE_REGISTRY.md).

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
      "id": "nara_digital_preservation_framework",
      "type": "nara_digital_preservation_framework",
      "enabled": true,
      "release_mode": "pinned",
      "release_date": "20260320"
    }
  ],
  "exports": {
    "enabled": true
  }
}
```

## Rules to prevent redundancy

1. The registry is generated by the pipeline, not hand-maintained.
2. MongoDB or another selected `RegistryStore` is the source of truth for the queryable local registry.
3. File outputs are exports only.
4. Source adapters never write directly to canonical registry collections.
5. Export adapters never update storage.
6. Pipeline orchestration should be thin; storage/export details belong in adapters.
7. Historical evidence and assessments should be stored separately from canonical format summaries.
8. `canonical_formats` may store current summary fields for fast lookup, but not full historical assessment history.
