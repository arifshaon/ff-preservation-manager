# Adapter implementation guide

This guide explains how to add new adapters without reading the whole codebase.

The system has three adapter families:

```text
SourceAdapter   -> acquires and parses external or institutional source material
RegistryStore   -> persists the queryable registry and run history
Exporter        -> writes optional review/interchange files
```

The most common extension is a new `SourceAdapter`.

## Mental model

A source adapter does not create the final registry. It only turns one source into normalized input material for the pipeline.

```text
source material
  -> SourceAdapter.acquire()
  -> SourceSnapshot objects
  -> SourceAdapter.extract(snapshots)
  -> RawFormatRecord objects
  -> normalization
  -> reconciliation
  -> RegistryStore persistence
```

The adapter should know how to retrieve and parse its source. It should not know about MongoDB, file storage, change detection, or exports.

## Source adapter contract

All source adapters inherit from:

```python
registry_builder.adapters.base.SourceAdapter
```

A source adapter implements:

```python
def acquire(self) -> list[SourceSnapshot]:
    ...


def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
    ...
```

### `acquire()`

`acquire()` retrieves source material and records an immutable source snapshot.

It should return one or more `SourceSnapshot` objects. A snapshot records:

```text
source_id
source_type
uri
acquired_at
sha256
local_path
content_type
note
changed
from_cache
metadata
```

Use the base helper methods where possible:

```python
self.acquire_uri_snapshot(uri, suffix=".csv", note="retrieval_mode=published_csv", metadata={...})
self.acquire_file_snapshot(path, suffix=".csv", note="source_location=local_file", metadata={...})
```

These helpers copy source material into the content-addressed snapshot cache under:

```text
work/snapshots/<source_id>/
```

They also update:

```text
work/snapshots/<source_id>/.snapshot_index.json
```

### `extract()`

`extract()` parses the cached snapshots and returns `RawFormatRecord` objects.

It should not fetch network resources. It should only parse `snapshot.local_path`.

This is important because offline replay must be able to rebuild the registry from cached snapshots.

## Minimal source adapter skeleton

```python
from pathlib import Path
from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import RawFormatRecord, SourceSnapshot


class ExampleSourceAdapter(SourceAdapter):
    type_name = "example_source"

    def acquire(self) -> list[SourceSnapshot]:
        snapshots = []
        for uri in self.config.get("uris", []):
            snapshots.append(
                self.acquire_uri_snapshot(
                    uri,
                    suffix=Path(uri).suffix or ".json",
                    note="retrieval_mode=example_json",
                    metadata={"source_location": "online"},
                )
            )
        return snapshots

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        records = []
        for snap in snapshots:
            # parse snap.local_path here
            records.append(
                RawFormatRecord(
                    source_id=self.source_id,
                    source_type=self.type_name,
                    source_record_id="source-record-id",
                    name="Example Format",
                    extensions=["ex"],
                    evidence=[{"source_file": snap.uri, "snapshot_sha256": snap.sha256}],
                    raw={"snapshot_sha256": snap.sha256},
                )
            )
        return records
```

Register it in:

```text
registry_builder/adapters/__init__.py
```

```python
from registry_builder.adapters.example_source import ExampleSourceAdapter

ADAPTERS = {
    ...
    "example_source": ExampleSourceAdapter,
}
```

## Config convention

A source config block should use this common shape:

```json
{
  "id": "example_source_current",
  "type": "example_source",
  "enabled": true,
  "required": false,
  "retrieval_mode": "example_json",
  "uris": ["https://example.org/source.json"],
  "notes": "Short operational note."
}
```

Common fields:

| Field | Meaning |
| --- | --- |
| `id` | Unique configured source instance. Used in snapshots and evidence. |
| `type` | Adapter type registered in `ADAPTERS`. |
| `enabled` | Whether the pipeline runs this source. |
| `required` | Whether source failure aborts the whole run. Defaults to required when not set. |
| `retrieval_mode` | Human-readable source retrieval mode. |
| `uris` | Online or local URI inputs, depending on adapter. |
| `local_files` | Admin-supplied source files, when supported. |
| `notes` | Operational guidance for config maintainers. |

## Required vs optional sources

Use `required:true` for sources that must be present for the run to be meaningful.

Use `required:false` for enrichment sources or external authorities where outage should be reported but should not block a partial registry build.

Examples:

```text
QNL institutional workbook       required:true in a QNL production run
NARA external hazard source      required:false unless a review explicitly depends on it
PRONOM authority enrichment      required:false for early runs, possibly true for identity-quality runs
```

When an optional source fails, the pipeline records the error in the run report and continues. Required source failures still abort.

## Offline and local-file behavior

Do not implement offline behavior by bypassing the snapshot cache.

Use these distinctions:

```text
online mode
  fetch or read source material and snapshot it

--offline
  replay previously cached source snapshots only

local_files mode
  read admin-supplied files as source material and snapshot them
```

A local-file run is not the same as offline replay. Local files are new source inputs; offline mode reuses already-acquired snapshots.

## Release modes

If a source publishes dated releases, model the release explicitly.

Recommended fields:

```json
{
  "release_mode": "pinned",
  "release_date": "20260320"
}
```

Common release modes:

| Mode | Use |
| --- | --- |
| `pinned` | Reproducible audit run against a known release. |
| `latest` | Scheduled refresh that discovers the newest release. |
| `explicit_uris` | Tests or one-off comparisons using exact URIs. |
| `local_files` | Admin-downloaded release files staged locally. |

Snapshot metadata should record the resolved release details:

```text
release_mode
release_date
source_location
github_ref / git_ref where applicable
github_path / source_path where applicable
github_blob_sha or equivalent source identifier where available
```

## Identifier authority rule

Adapters should mark identifiers as verified only when the source owns that identifier namespace.

Examples:

```text
PRONOM adapter emits verified PUIDs.
NARA adapter emits verified NARA Format IDs.
LOC adapter emits verified LOC FDD IDs.
Institutional workbook copied PUIDs are useful claims but not verified authority identifiers.
```

Do not mark a PUID copied from a NARA row or an institutional spreadsheet as a verified PRONOM identifier. PRONOM must confirm it.

## RawFormatRecord fields

Use only the fields supported by `RawFormatRecord`:

```text
source_id
source_type
source_record_id
name
category
description
extensions
mime_types
puids
loc_ids
nara_ids
wikidata_ids
identifiers
urls
institution_policy
hazard
readiness
trend
evidence
raw
```

Prefer structured fields over burying data only in `raw`.

Always keep the original source row or a useful source subset in `raw` for audit/debugging.

Always include evidence linking the record to the snapshot:

```python
evidence=[{
    "type": "example_source_row",
    "source_file": snap.uri,
    "source_row": row_no,
    "snapshot_sha256": snap.sha256,
}]
```

## Testing checklist

Every new adapter should have tests for:

1. Acquisition from online/local input, using small fixtures or monkeypatching.
2. Extraction into expected `RawFormatRecord` fields.
3. Identifier verification behavior.
4. Snapshot metadata and SHA handling.
5. Offline/cache behavior if supported.
6. Failure behavior for missing required config.
7. Registration in `ADAPTERS`.
8. A pipeline-level smoke test if the adapter is expected to be used in production.

## Storage adapter contract

Storage adapters implement:

```python
registry_builder.storage.base.RegistryStore
```

They persist pipeline objects; they do not acquire source material.

Implemented storage backends include:

```text
memory
file / json_file
mongodb
```

A storage adapter must support these logical collections:

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

## Export adapter direction

Exports are optional review/interchange products. They are not registry storage.

Examples:

```text
registry.json
registry.jsonl
registry.csv
registry.sqlite
coverage_report.md
```

Do not build an adapter that writes an export and then imports it into MongoDB. The pipeline should persist directly through `RegistryStore`, then optionally export.

## Documentation checklist for new adapters

When adding an adapter, update:

1. `docs/ADAPTER_REFERENCE.md`
2. `config/sources.example.json`, if useful
3. `docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md`, if it introduces a new retrieval pattern
4. `README.md`, only if it changes common operator workflow
