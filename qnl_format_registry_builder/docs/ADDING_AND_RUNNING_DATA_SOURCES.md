# Adding and running data sources

This runbook explains how to plug a new data source into the registry builder and how to run existing sources such as NARA, PRONOM, and LOC either together or individually.

For the shortest end-to-end source-onboarding route—from source boundary through criterion mapping and risk-manager verification—start with:

[`../../docs/HOW_TO_ADD_A_SOURCE.md`](../../docs/HOW_TO_ADD_A_SOURCE.md)

For narrative/PDF/unstructured sources, also read:

[`../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md)

The key point is this:

```text
A data source is not MongoDB.
A data source adapter reads source evidence and emits normalized records.
MongoDB stores the resulting registry state and source-record history.
```

A second key point is that **making a source load is not the end of onboarding**. If the source is intended to contribute to framework-driven risk analysis, its source-native observations must also be mapped into reviewed `criterion_claims` and verified through `preservation_risk_manager`.

## Core concepts

### Source adapter type

A source adapter type is the Python class that knows how to acquire and parse one kind of source.

Examples:

```text
nara_digital_preservation_framework
pronom_registry
loc_fdd_xml
institution_policy_xlsx
standard_json
```

A source adapter implements:

```python
def acquire(self) -> list[SourceSnapshot]: ...
def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]: ...
```

### Source instance

A source instance is one configured use of an adapter in a JSON config file.

Example:

```json
{
  "id": "pronom_registry",
  "type": "pronom_registry",
  "enabled": true,
  "required": false,
  "retrieval_mode": "github_archive"
}
```

The `id` is the configured source contribution. The `type` is the adapter implementation.

### Source snapshot

A source snapshot is the evidence input used for a run. It may be:

```text
one CSV file
one JSON file
one ZIP archive containing many records
one admin-downloaded local file
one temporary file read only for extraction
one reviewed JSON transcription derived from a narrative publication
```

Retained snapshots live under:

```text
work/snapshots/<source_id>/
```

Temporary snapshots live under:

```text
work/temporary_snapshots/<source_id>/
```

Temporary snapshots are deleted after extraction.

### Raw source record

A `RawFormatRecord` is the normalized source contribution emitted by an adapter. It is persisted through the selected storage backend, normally MongoDB.

A retained source snapshot is useful for audit replay. A temporary snapshot is useful when the source has thousands of small files and retaining all of them would waste disk space. In that case, the adapter should preserve the useful source payload in `RawFormatRecord.raw` before deleting the temporary file.

For sources that will feed criterion mapping, preserve source-native observations in `RawFormatRecord.native_fields` where practical. The mapping layer exists so adapters do not need to hard-code QNL criterion IDs or risk scores.

## End-to-end pipeline

For a structured source:

```text
configured source
  -> SourceAdapter.acquire()
  -> retained or temporary SourceSnapshot(s)
  -> SourceAdapter.extract()
  -> RawFormatRecord(s)
  -> normalization
  -> identifier reconciliation
  -> canonical registry
  -> declarative criterion mapping
  -> criterion_claims
  -> RegistryStore, for example MongoDB
  -> preservation_risk_manager verification/query
  -> optional exports/reports
```

For an unstructured source:

```text
PDF / HTML / narrative publication
  -> manual or AI-assisted transcription draft
  -> human-reviewed versioned JSON artifact
  -> normal SourceAdapter path above
```

The adapter should not write directly to MongoDB. The pipeline does that after normalization and reconciliation.

## Choosing the right acquisition pattern

### Pattern 1: one downloaded/admin file

Use this when an administrator has already downloaded the source file.

Examples:

```text
NARA CSV files downloaded manually
institutional policy workbook
local JSON source package
local XML files
LOC FDD XML ZIP downloaded manually
```

Use a retained snapshot. The file is source evidence for this run.

For local files in JSON config, prefer plain filesystem paths. On Windows, forward slashes are the simplest and avoid escaping problems:

```json
{
  "zip_uri": "C:/Users/Arif Shaon/Downloads/fddXML.zip"
}
```

Relative project paths are also good when you stage files inside the repository working tree:

```json
{
  "zip_uri": "input/loc/fddXML.zip"
}
```

`file://` URIs are supported by the URI reader, but plain Windows paths are easier to read and less error-prone in local config files.

Adapter implementation pattern:

```python
snapshot = self.acquire_file_snapshot(
    path,
    suffix=".csv",
    note="source_location=local_file",
    metadata={"source_location": "local_file", "admin_supplied": True},
)
```

Config pattern:

```json
{
  "id": "example_local_csv",
  "type": "mypkg.adapters.example:ExampleCsvAdapter",
  "enabled": true,
  "required": true,
  "retrieval_mode": "local_files",
  "local_files": [
    {"path": "input/example/source.csv", "kind": "format_registry"}
  ]
}
```

### Pattern 2: one remote CSV or JSON file

Use this when the source publishes one stable file.

Examples:

```text
one JSON export
one CSV release file
one XML feed
```

Use a retained URI snapshot.

Adapter implementation pattern:

```python
snapshot = self.acquire_uri_snapshot(
    uri,
    suffix=".json",
    note="retrieval_mode=published_json",
    metadata={"source_location": "remote_uri"},
)
```

Config pattern:

```json
{
  "id": "example_remote_json",
  "type": "mypkg.adapters.example:ExampleJsonAdapter",
  "enabled": true,
  "required": false,
  "retrieval_mode": "published_json",
  "uris": ["https://example.org/file-formats.json"]
}
```

### Pattern 3: one archive containing many records

Use this when the source provides a ZIP archive or bundle containing many JSON/XML/CSV records.

Examples:

```text
PRONOM repository archive ZIP
LOC FDD XML ZIP
```

This is usually the best performance/audit tradeoff:

```text
one retained source snapshot
many emitted RawFormatRecord objects
MongoDB stores the normalized registry records
```

Config pattern:

```json
{
  "id": "pronom_registry",
  "type": "pronom_registry",
  "enabled": true,
  "required": false,
  "retrieval_mode": "github_archive",
  "archive_url": "https://github.com/nationalarchives/pronom/archive/refs/heads/develop.zip",
  "include_paths": ["signatures/fmt/", "signatures/x-fmt/"]
}
```

LOC remote ZIP example:

```json
{
  "id": "loc_fdd_xml",
  "type": "loc_fdd_xml",
  "enabled": true,
  "required": false,
  "retrieval_mode": "fdd_xml_zip",
  "zip_uri": "https://www.loc.gov/preservation/digital/formats/fddXML.zip"
}
```

LOC downloaded ZIP example on Windows:

```json
{
  "id": "loc_fdd_xml",
  "type": "loc_fdd_xml",
  "enabled": true,
  "required": false,
  "retrieval_mode": "fdd_xml_zip",
  "zip_uri": "C:/Users/Arif Shaon/Downloads/fddXML.zip"
}
```

### Pattern 4: many individual JSON or XML files

Use this when no archive exists and the source exposes many individual files.

Do not retain thousands of files by default. Use temporary snapshots.

Config pattern:

```json
{
  "id": "example_many_json_files",
  "type": "mypkg.adapters.example:ExampleJsonAdapter",
  "enabled": true,
  "required": false,
  "retrieval_mode": "json_tree",
  "tree_url": "https://example.org/api/file-list.json",
  "snapshot_policy": "temporary"
}
```

Required behavior:

```text
read/download file
write temporary snapshot
extract RawFormatRecord
copy useful raw payload into RawFormatRecord.raw
delete temporary file
pipeline stores RawFormatRecord in MongoDB
```

This avoids filling disk while keeping the source record available in MongoDB.

### Pattern 5: unstructured or narrative source

Use this when the authority publishes useful preservation evidence as prose rather than as a stable machine-readable feed.

Examples:

```text
DPC Bit List PDF/HTML
narrative preservation guidance
PDF reports
scanned/OCR'd risk/watch lists
web pages with prose entries
```

Do **not** call an LLM inside the production risk calculation and treat its transient answer as source evidence.

Use a reviewable intermediate artifact:

```text
original PDF/HTML
 -> manual or AI-assisted transcription draft
 -> versioned JSON
 -> human review
 -> reviewed JSON source artifact
 -> standard_json or thin source-specific adapter
 -> normal registry pipeline
```

The reviewed JSON should preserve:

```text
source edition
original source URL/file
transcription method
AI model/prompt version when applicable
human review status/reviewer/date
stable source_record_id
source-native fields
page/section/heading/URL locator for every record
```

The repository provides:

```text
../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md
config/schemas/unstructured_source_transcription.v1.schema.json
config/prompts/transcribe_unstructured_source/v1.0.md
config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md
```

For a reviewed transcription that already fits the standard JSON package shape, the built-in adapter can be used:

```json
{
  "id": "dpc_bit_list",
  "type": "standard_json",
  "enabled": true,
  "required": false,
  "uris": ["sources/dpc_bitlist/2026-08.reviewed.json"]
}
```

`standard_json` retains the full source record under `RawFormatRecord.raw`. If transcription-specific fields live in `record.native_fields`, criterion mappings can address them under paths such as:

```text
raw.native_fields.endangerment_category
raw.native_fields.trend
```

A thin source-specific adapter is preferred when you need automatic acquisition, edition handling, source-specific validation, or direct promotion into `RawFormatRecord.native_fields`.

AI transcription is a **drafting mechanism**. A named human/team must review the transcription before it is treated as approved production evidence.

## Seven-step source onboarding path

The original adapter-only workflow is expanded here so onboarding ends with risk-analysis usability, not merely successful parsing.

### Step 1: decide the source boundary

Name the adapter/source after the conceptual source, not the file representation, unless the representation is truly the source.

Good names:

```text
nara_digital_preservation_framework
pronom_registry
loc_fdd_xml
dpc_bit_list
```

Avoid names like this for a source-level adapter:

```text
nara_csv
pronom_json
dpc_pdf
```

CSV, JSON, HTML, or PDF is usually a publication format, not the conceptual authority/source.

### Step 2: transcribe if the source is unstructured

Skip this step for stable machine-readable CSV/JSON/XML/API sources.

For narrative/PDF sources:

```text
source publication
 -> transcription draft
 -> human-reviewed structured artifact
```

Use the transcription guide and schema. Preserve source-native wording and locators. Do not perform criterion mapping during transcription.

See [`../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md).

### Step 3: create the adapter class or use `standard_json`

Minimal JSON adapter skeleton:

```python
from pathlib import Path
import json

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import Identifier, RawFormatRecord, SourceSnapshot


class ExampleJsonAdapter(SourceAdapter):
    type_name = "example_json_source"

    def acquire(self) -> list[SourceSnapshot]:
        snapshots = []
        for uri in self.config.get("uris", []):
            snapshots.append(
                self.acquire_uri_snapshot(
                    uri,
                    suffix=".json",
                    note="retrieval_mode=published_json",
                    metadata={"source_location": "remote_uri"},
                )
            )
        return snapshots

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records = []
        for snap in snapshots:
            payload = json.loads(Path(snap.local_path).read_text(encoding="utf-8"))
            rows = payload.get("formats", payload if isinstance(payload, list) else [])
            for row in rows:
                source_record_id = str(row.get("id") or row.get("name"))
                records.append(
                    RawFormatRecord(
                        source_id=self.source_id,
                        source_type=self.type_name,
                        source_record_id=source_record_id,
                        name=row.get("name"),
                        extensions=row.get("extensions", []),
                        mime_types=row.get("mime_types", []),
                        identifiers=[
                            Identifier("example", source_record_id, self.type_name, True, source_record_id)
                        ],
                        native_fields=row.get("native_fields", {}) or {},
                        evidence=[{
                            "type": "example_json_record",
                            "source_file": snap.uri,
                            "snapshot_sha256": snap.sha256,
                        }],
                        raw={"snapshot_sha256": snap.sha256, "record": row},
                    )
                )
        return records
```

Minimal CSV adapter skeleton:

```python
from pathlib import Path
import csv

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import Identifier, RawFormatRecord, SourceSnapshot
from registry_builder.utils import split_multi


class ExampleCsvAdapter(SourceAdapter):
    type_name = "example_csv_source"

    def acquire(self) -> list[SourceSnapshot]:
        snapshots = []
        for uri in self.config.get("uris", []):
            snapshots.append(
                self.acquire_uri_snapshot(
                    uri,
                    suffix=".csv",
                    note="retrieval_mode=published_csv",
                    metadata={"source_location": "remote_uri"},
                )
            )
        for item in self.config.get("local_files", []):
            snapshots.append(
                self.acquire_file_snapshot(
                    item["path"],
                    suffix=".csv",
                    note="retrieval_mode=local_files",
                    metadata={"source_location": "local_file", "admin_supplied": True, "kind": item.get("kind")},
                )
            )
        return snapshots

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records = []
        for snap in snapshots:
            with Path(snap.local_path).open(newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row_number, row in enumerate(reader, start=2):
                    source_record_id = row.get("ID") or row.get("Format ID") or row.get("Name")
                    records.append(
                        RawFormatRecord(
                            source_id=self.source_id,
                            source_type=self.type_name,
                            source_record_id=source_record_id,
                            name=row.get("Name"),
                            category=row.get("Category"),
                            extensions=split_multi(row.get("Extensions")),
                            mime_types=split_multi(row.get("MIME Types")),
                            identifiers=[
                                Identifier("example", source_record_id, self.type_name, True, source_record_id)
                            ] if source_record_id else [],
                            native_fields=dict(row),
                            evidence=[{
                                "type": "example_csv_row",
                                "source_file": snap.uri,
                                "source_row": row_number,
                                "snapshot_sha256": snap.sha256,
                            }],
                            raw={"snapshot_sha256": snap.sha256, "row": row, "row_number": row_number},
                        )
                    )
        return records
```

### Step 4: register the adapter and define identifier rules

Built-in adapter registration is in:

```text
registry_builder/adapters/__init__.py
```

Add the class to the built-in registry if it belongs in the core package.

For external/internal institutional packages, avoid editing the core and use a plugin path:

```json
{
  "id": "dpc_bit_list",
  "type": "mypkg.adapters.dpc:DpcBitListAdapter",
  "enabled": true,
  "required": false
}
```

If the source owns an identifier namespace, declare it in config:

```json
{
  "identifier_kinds": {
    "example": {
      "strength": "strong",
      "verified_from": ["example_source"]
    }
  }
}
```

Only do this when the source genuinely owns/stably defines the namespace.

If the source merely repeats another source's identifier, emit it as a claim but do not treat it as verified unless that source is in `verified_from`.

Examples:

```text
PUID from PRONOM adapter      -> verified PRONOM identifier
PUID copied from NARA row     -> useful claim, not verified by PRONOM
LOC FDD ID from LOC adapter   -> verified LOC identifier
LOC URL copied from workbook  -> useful claim, not verified by LOC
```

### Step 5: define criterion mappings

If the source should contribute to framework-driven risk analysis, map source-native observations into the neutral criteria vocabulary.

```text
RawFormatRecord.native_fields / raw
 -> reviewed mapping JSON
 -> criterion_claims
```

Do not force composite source risk bands or recommended actions into primitive sustainability/technical criteria.

Start with:

[`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)

Detailed mapping lifecycle:

[`criterion_mapping_workflow.md`](criterion_mapping_workflow.md)

AI may draft the mapping, but it cannot approve it.

### Step 6: validate, review, and generate claims

Run mapping validation:

```powershell
python -m registry_builder mapping validate `
  --criteria config\criteria\v1.json `
  --mappings drafts\my_source.mapping.json
```

After human review/approval, use an integrated build or criterion-claim backfill.

Verify that `criterion_claims` are generated and preserve source/mapping provenance.

### Step 7: test adapter + risk-manager consumption

Every source should test:

```text
acquisition from a fixture or mocked URI
extraction into RawFormatRecord
identifier verification
snapshot metadata
large-source snapshot policy, if applicable
offline/local-file behavior, if applicable
transcription review behavior, if applicable
criterion mapping/claim production, if the source is used for framework assessment
risk-manager visibility for at least one intended criterion/question
```

Onboarding is not complete until the evidence can be retrieved by the intended `preservation_risk_manager` query or evidence-gap analysis.

## Running existing sources together

The default config runs NARA, PRONOM, and LOC together.

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out output
```

Remember: `sources.example.json` is primarily a registry-construction example. If you need criterion claims for the risk manager, use a config with `criterion_mapping.enabled=true`.

For MongoDB, make sure the config has:

```json
"storage": {
  "type": "mongodb",
  "uri": "mongodb://localhost:27017",
  "database": "format_registry"
}
```

## Running NARA only with MongoDB

```json
{
  "pipeline_version": "0.1.0",
  "incremental_source_updates": true,
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry"
  },
  "exports": {"enabled": true},
  "method_profiles": {"enabled": false},
  "sources": [
    {
      "id": "nara_digital_preservation_framework",
      "type": "nara_digital_preservation_framework",
      "enabled": true,
      "required": true,
      "retrieval_mode": "published_csv",
      "release_mode": "pinned",
      "release_date": "20260320",
      "fallback_release_date": "20260320",
      "github_ref": "master"
    }
  ]
}
```

Run:

```powershell
python -m registry_builder run `
  --config config\nara.mongodb.local.json `
  --workdir work\nara `
  --out output\nara
```

## Running PRONOM only with MongoDB, archive mode

Use this when the GitHub archive is available. It keeps one archive snapshot and extracts many records from it.

```json
{
  "pipeline_version": "0.1.0",
  "incremental_source_updates": true,
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry"
  },
  "exports": {"enabled": true},
  "method_profiles": {"enabled": false},
  "identifier_kinds": {
    "puid": {"strength": "strong", "verified_from": ["pronom_registry", "pronom_droid_xml"]}
  },
  "sources": [
    {
      "id": "pronom_registry",
      "type": "pronom_registry",
      "enabled": true,
      "required": true,
      "retrieval_mode": "github_archive",
      "archive_url": "https://github.com/nationalarchives/pronom/archive/refs/heads/develop.zip",
      "include_paths": ["signatures/fmt/", "signatures/x-fmt/"],
      "progress": true,
      "progress_interval": 100
    }
  ]
}
```

Run:

```powershell
python -m registry_builder run `
  --config config\pronom.mongodb.local.json `
  --workdir work\pronom `
  --out output\pronom
```

## Running PRONOM only with MongoDB, individual JSON mode

Use this when the source exposes individual JSON files and no archive is available. This keeps only the tree/list snapshot and deletes each temporary JSON file after extraction.

```json
{
  "pipeline_version": "0.1.0",
  "incremental_source_updates": true,
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry"
  },
  "exports": {"enabled": true},
  "method_profiles": {"enabled": false},
  "identifier_kinds": {
    "puid": {"strength": "strong", "verified_from": ["pronom_registry", "pronom_droid_xml"]}
  },
  "sources": [
    {
      "id": "pronom_registry",
      "type": "pronom_registry",
      "enabled": true,
      "required": true,
      "retrieval_mode": "github_json",
      "github_tree_url": "https://api.github.com/repos/nationalarchives/pronom/git/trees/develop?recursive=1",
      "raw_base_url": "https://raw.githubusercontent.com/nationalarchives/pronom/develop",
      "include_paths": ["signatures/fmt/", "signatures/x-fmt/"],
      "snapshot_policy": "temporary",
      "progress": true,
      "progress_interval": 100
    }
  ]
}
```

## Running LOC only with MongoDB

Use the official LOC FDD XML ZIP when downloading directly from LOC. This keeps one ZIP snapshot and extracts many LOC records from it.

```json
{
  "pipeline_version": "0.1.0",
  "incremental_source_updates": true,
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry"
  },
  "exports": {"enabled": true},
  "method_profiles": {"enabled": false},
  "identifier_kinds": {
    "loc": {"strength": "strong", "verified_from": ["loc_fdd_xml"]},
    "puid": {"strength": "strong", "verified_from": ["pronom_registry", "pronom_droid_xml"]},
    "wikidata": {"strength": "weak", "verified_from": ["wikidata"]}
  },
  "sources": [
    {
      "id": "loc_fdd_xml",
      "type": "loc_fdd_xml",
      "enabled": true,
      "required": true,
      "retrieval_mode": "fdd_xml_zip",
      "zip_uri": "https://www.loc.gov/preservation/digital/formats/fddXML.zip",
      "progress": true,
      "progress_interval": 25
    }
  ]
}
```

If the LOC ZIP has already been downloaded locally, use a normal Windows path in `zip_uri`:

```json
{
  "id": "loc_fdd_xml",
  "type": "loc_fdd_xml",
  "enabled": true,
  "required": true,
  "retrieval_mode": "fdd_xml_zip",
  "zip_uri": "C:/Users/Arif Shaon/Downloads/fddXML.zip",
  "progress": true,
  "progress_interval": 25
}
```

The path above is preferable to a `file://` URI in local Windows configs. It is clear, readable, and works with spaces in the user profile path.

Run:

```powershell
python -m registry_builder run `
  --config config\loc.mongodb.local.json `
  --workdir work\loc `
  --out output\loc
```

## Running an admin-downloaded source file today

Use local/admin files when the source file has already been reviewed or staged locally.

NARA local-file example:

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "required": true,
  "retrieval_mode": "published_csv",
  "release_mode": "local_files",
  "local_files": [
    {
      "path": "input/nara/NARA_PreservationActionPlan_FileFormats_20260320.csv",
      "kind": "preservation_action_plan",
      "release_date": "20260320"
    },
    {
      "path": "input/nara/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv",
      "kind": "risk_matrix_numbered",
      "release_date": "20260320"
    }
  ]
}
```

A local-file run is not the same as offline replay:

```text
local_files
  reads admin-supplied files as source evidence for this run

--offline
  replays already-cached source snapshots without touching the original source
```

## Running a custom source today with a plugin path

If your adapter is in an installed Python package, you can run it without editing the core registry.

```json
{
  "pipeline_version": "0.1.0",
  "incremental_source_updates": true,
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry"
  },
  "exports": {"enabled": true},
  "sources": [
    {
      "id": "dpc_bit_list",
      "type": "mypkg.adapters.dpc:DpcBitListAdapter",
      "enabled": true,
      "required": false,
      "uris": ["sources/dpcbitlist/2026-08.reviewed.json"],
      "progress": true
    }
  ]
}
```

## Source-by-source operation

The pipeline supports source-by-source augmentation when `incremental_source_updates` is true.

Example:

```text
Run NARA today
  -> MongoDB stores NARA source records and canonical formats

Run PRONOM tomorrow against the same MongoDB database
  -> PRONOM contributes verified PUID evidence
  -> latest successful NARA evidence is reused
  -> canonical registry is recomputed from active evidence contributions

Run LOC later
  -> LOC contributes FDD evidence
  -> latest NARA and PRONOM evidence are reused
```

This means an individual source run is not isolated unless `incremental_source_updates` is false. It augments the current registry view using latest successful contributions from sources that did not run this time.

## Operator checklist

Before running a source:

```text
1. Decide whether the source should be required or optional.
2. Decide whether snapshots should be retained or temporary.
3. If unstructured, verify the transcription artifact is human-reviewed.
4. Use persistent storage for real registry population.
5. Set progress/progress_interval for large sources.
6. Use a distinct workdir per experimental source run if testing.
7. Check output/run_report.json after completion.
8. Audit actual source fields before writing criterion mappings.
9. Validate/human-review mapping rules.
10. Verify generated criterion claims in the risk manager.
```

Useful MongoDB checks:

```javascript
use format_registry
db.runs.find().sort({finished_at: -1}).limit(1).pretty()
db.source_records.countDocuments({source_id: "pronom_registry"})
db.source_records.countDocuments({source_id: "loc_fdd_xml"})
db.canonical_formats.countDocuments({current: {$ne: false}})
db.criterion_claims.countDocuments()
```

## Common mistakes to avoid

### Mistake: stopping when the adapter loads

A source intended for framework assessment is not fully onboarded until reviewed mappings produce `criterion_claims` and the risk manager can consume them.

### Mistake: using transient AI output as evidence

For narrative sources, do not make the adapter/risk manager depend on a one-off chat response.

Use:

```text
AI/manual transcription -> versioned draft JSON -> human review -> reviewed JSON -> adapter
```

### Mistake: mixing transcription and criterion mapping

Transcription preserves what the source says. Criterion mapping translates reviewed source-native fields into the neutral vocabulary. Keep them as separate reviewed artifacts.

### Mistake: using memory for real source population

```json
"storage": {"type": "memory"}
```

Memory is useful for smoke tests/quickstarts. Use persistent file/MongoDB storage for operational registries.

### Mistake: using awkward local file URIs on Windows

For downloaded local files, prefer this:

```json
"zip_uri": "C:/Users/Arif Shaon/Downloads/fddXML.zip"
```

Avoid this unless there is a specific reason to use URI syntax:

```json
"zip_uri": "file:///C:/Users/Arif%20Shaon/Downloads/fddXML.zip"
```

### Mistake: retaining thousands of individual source files

For many-file JSON/XML sources, use:

```json
"snapshot_policy": "temporary"
```

or prefer a single archive snapshot when available.

### Mistake: fetching inside `extract()`

`extract()` should parse snapshots. Network acquisition belongs in `acquire()`.

### Mistake: treating copied identifiers as verified

A PUID copied into NARA/DPC/institutional material is a claim. A PUID emitted by PRONOM is verified.

### Mistake: confusing exports with storage

`output/` files are review/interchange products. Persistent storage backends are the operational registry store.

## Where to document a new source

When adding a source, update:

```text
../../docs/HOW_TO_ADD_A_SOURCE.md
  only when the source introduces a genuinely new onboarding pattern

docs/ADAPTER_REFERENCE.md
  how to configure and run the adapter

docs/ADDING_AND_RUNNING_DATA_SOURCES.md
  if the source introduces a new acquisition pattern or useful run example

docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md
  mapping/criterion implications

docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md
  if the source introduces new fallback/offline/local-file behavior

config/sources.example.json
  only if the source should be part of the default example run
```

For an unstructured source, also document the transcription schema/prompt and review expectations.
