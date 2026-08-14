# Adapter implementation guide

This guide explains how to add new adapters and storage backends without reading the whole codebase.

The system has three extension families:

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

## Loading adapters without editing core

Built-in adapters still have short names such as:

```text
standard_json
institution_policy_xlsx
nara_digital_preservation_framework
pronom_registry
```

Third-party adapters can be loaded directly from config with an explicit `module:ClassName` plugin path:

```json
{
  "id": "dpc_bit_list",
  "type": "mypkg.adapters.dpc:DpcBitListAdapter",
  "enabled": true,
  "required": false
}
```

The resolver first checks the built-in registry. If the value is not a built-in short name, it imports the `module:ClassName` path and validates that the resolved class is a `SourceAdapter` subclass. This means external packages can ship adapters without changing `registry_builder/adapters/__init__.py`.

Use the colon form only. The older-looking `module.ClassName` form is intentionally not supported because it is ambiguous: the final component may be either a module or a class attribute.

### Plugin trust boundary

Plugin configuration is a trusted-code boundary. Importing a plugin module executes that module's top-level Python code. Only use plugin paths from configuration controlled by trusted maintainers, and install third-party plugin packages through the same review process used for other executable dependencies.

Bad plugin specs fail early:

```text
wrong module path      -> Plugin module ... not found
missing dependency     -> plugin exists but one of its dependencies is missing
missing class name     -> Module ... has no attribute ...
wrong base class       -> not a subclass of SourceAdapter / RegistryStore
```

The same pattern works for storage backends:

```json
{
  "storage": {
    "type": "mypkg.storage.sql:SqlRegistryStore",
    "dsn": "postgresql://..."
  }
}
```

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

`acquire()` retrieves source material and records immutable source snapshots.

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
from registry_builder.models import Identifier, RawFormatRecord, SourceSnapshot


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
            records.append(
                RawFormatRecord(
                    source_id=self.source_id,
                    source_type=self.type_name,
                    source_record_id="source-record-id",
                    name="Example Format",
                    identifiers=[Identifier("example", "EX-001", self.type_name, False, "source-record-id")],
                    evidence=[{"source_file": snap.uri, "snapshot_sha256": snap.sha256}],
                    raw={"snapshot_sha256": snap.sha256},
                )
            )
        return records
```

You can either add this adapter to the built-in registry, or use the `module:ClassName` plugin path directly in config:

```json
{
  "type": "mypkg.adapters.example:ExampleSourceAdapter"
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
| `type` | Built-in adapter short name or `module:ClassName` plugin path. |
| `enabled` | Whether the pipeline runs this source. |
| `required` | Whether source failure aborts the whole run. Defaults to required when not set. |
| `retrieval_mode` | Human-readable source retrieval mode. |
| `uris` | Online or local URI inputs, depending on adapter. |
| `local_files` | Admin-supplied source files, when supported. |
| `notes` | Operational guidance for config maintainers. |

## Required vs optional sources

Use `required:true` for sources that must be present for the run to be meaningful.

Use `required:false` for enrichment sources or external authorities where outage should be reported but should not block a partial registry build.

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

## Identifier authority rules

New source-specific identifier namespaces no longer require model changes.

Adapters should emit generic identifiers:

```python
Identifier("dpc", "DPC-001", "dpc_bit_list", False, source_record_id)
```

Then config declares whether that namespace is strong and which source types verify it:

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

Normalization marks the identifier verified when the record's `source_type` appears in `verified_from`. Reconciliation uses configured `strength: strong` namespaces as primary grouping keys.

Compatibility fields such as `puids`, `loc_ids`, and `nara_ids` still work, but new adapters should prefer `identifiers` so the core model does not need one field per namespace.

## Hazard scale metadata

Adapters must emit normalized hazard values for reconciliation:

```json
{
  "rating": 2.0,
  "band": "Moderate"
}
```

If the source has a native scale, carry it separately:

```json
{
  "external_rating_native": 4.0,
  "external_rating_native_scale": "dpc_bitlist_scale",
  "external_rating_native_direction": "lower_is_safer"
}
```

Reconciliation copies these native fields for audit/explanation but does not treat native ratings as normalized hazard scores. Source-specific threshold explanations should live in the adapter payload unless the core explicitly knows that source scale.

## RawFormatRecord fields

Prefer generic `identifiers` for source-specific identifiers. Compatibility typed fields remain available for existing adapters:

```text
extensions
mime_types
puids
loc_ids
nara_ids
wikidata_ids
identifiers
```

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

## Storage adapter contract

Storage adapters implement:

```python
registry_builder.storage.base.RegistryStore
```

A new backend only needs the generic core:

```python
def upsert(self, collection: str, key: str | None, doc: dict) -> str: ...
def query(self, collection: str, filt: dict | None = None) -> list[dict]: ...
def begin(self) -> None: ...   # optional
def close(self) -> None: ...   # optional
```

`RegistryStore` supplies concrete helper methods such as `save_snapshot`, `save_source_record`, `save_hazard_assessment`, and `list_changes_since`. Backends may override helpers for performance, indexes, or database-native query behavior, but they do not have to.

Logical collections:

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

## Testing checklist

Every new adapter should have tests for:

1. Acquisition from online/local input, using small fixtures or monkeypatching.
2. Extraction into expected `RawFormatRecord` fields.
3. Identifier verification behavior.
4. Snapshot metadata and SHA handling.
5. Offline/cache behavior if supported.
6. Failure behavior for missing required config.
7. `module:ClassName` plugin loading if it ships outside this repo.
8. A pipeline-level smoke test if the adapter is expected to be used in production.

Every new storage backend should have tests for:

1. `upsert()` and `query()`.
2. Current registry view filtering.
3. Identifier lookup.
4. Change event persistence.
5. `module:ClassName` plugin loading.

## Export adapter direction

Exports are optional review/interchange products. They are not registry storage.

Do not build an adapter that writes an export and then imports it into MongoDB. The pipeline should persist directly through `RegistryStore`, then optionally export.

## Documentation checklist for new adapters

When adding an adapter, update:

1. `docs/ADAPTER_REFERENCE.md`
2. `config/sources.example.json`, if useful
3. `docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md`, if it introduces a new retrieval pattern
4. `README.md`, only if it changes common operator workflow
