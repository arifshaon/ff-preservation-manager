# Source adapters

This document explains the source-adapter concept. For step-by-step implementation guidance, read:

1. [`ADAPTER_IMPLEMENTATION_GUIDE.md`](ADAPTER_IMPLEMENTATION_GUIDE.md)
2. [`ADAPTER_REFERENCE.md`](ADAPTER_REFERENCE.md)
3. [`SOURCE_RETRIEVAL_AND_FALLBACKS.md`](SOURCE_RETRIEVAL_AND_FALLBACKS.md)

## Principle

Source adapters are source-first, not file-format-first.

A source adapter represents an authority or institutional source such as PRONOM, NARA, LOC, or an institutional policy workbook. The source may currently publish CSV, XLSX, XML, JSON, API responses, linked data, or HTML. Those are retrieval/parsing modes, not the conceptual source boundary.

```text
source adapter
  -> acquire source material
  -> snapshot acquired source material
  -> parse current representation
  -> emit RawFormatRecord objects
```

The adapter does **not** write to MongoDB or any other database directly. Persistence belongs to the storage layer.

```text
RawFormatRecord        -> RegistryStore.save_source_record()
SourceSnapshot         -> RegistryStore.save_snapshot()
CanonicalFormat        -> RegistryStore.upsert_canonical_format()
Identifier claims      -> RegistryStore.upsert_identifier()
Institutional policy   -> RegistryStore.save_institution_policy_overlay()
Hazard assessment      -> RegistryStore.save_hazard_assessment()
```

## Adapter lifecycle

Every source adapter follows the same two-stage lifecycle:

```python
acquire() -> list[SourceSnapshot]
extract(snapshots) -> list[RawFormatRecord]
```

`acquire()` handles source material and snapshots it.

`extract()` parses only the snapshots it receives. It should not fetch the network. This keeps offline replay and audit runs reproducible.

## Snapshot cache and offline mode

Source acquisition uses a content-addressed snapshot cache under:

```text
work/snapshots/<source_id>/
```

Each source keeps a `.snapshot_index.json` mapping source URI or local source path to the latest cached SHA-256 and local snapshot path.

Online mode checks the upstream source and reports whether each snapshot changed:

```text
changed=true
changed=false
```

Unchanged snapshots are not rewritten. This lets the run report show per-source change status, for example:

```text
source_changed
snapshots_changed
snapshots_unchanged
snapshots_from_cache
```

Offline mode can be enabled from the CLI:

```bash
python -m registry_builder run --config config/sources.example.json --workdir work --out output --offline
```

or through config:

```json
{
  "offline": true
}
```

In offline mode, adapters read only from the cached snapshot index. If a requested URI is not already cached, the run fails loudly rather than silently fetching or substituting another source.

## Local/admin source files

Some sources, including NARA, can use admin-supplied local files as a first-class retrieval mode.

This is not the same as `--offline`:

```text
--offline
  replay previously cached snapshots

local_files
  treat local files as this run's source material and snapshot them
```

Local files should still go through the snapshot helper so the run records SHA-256, change status, and metadata such as:

```text
source_location: local_file
admin_supplied: true
release_date
file kind
```

## Required vs optional sources

Source config can declare whether a source is required:

```json
{
  "id": "nara_digital_preservation_framework",
  "required": false
}
```

A required source failure aborts the run. An optional source failure is recorded in the source summary and the run continues with the remaining sources.

Use `required:true` for sources that define the purpose of the run. Use `required:false` for enrichment or external authority sources that should not destroy an otherwise useful run during an outage.

## Preferred adapter naming

Use source-level names for new adapters:

```text
nara_digital_preservation_framework
pronom_registry
loc_fdd_xml
institution_policy_xlsx
```

Representation-specific names are acceptable only as compatibility aliases or narrow modes:

```text
nara_preservation_csv      # deprecated alias; CSV is current NARA retrieval mode
pronom_droid_xml           # representation-specific DROID signature XML parser
```

## Implemented adapter types

See [`ADAPTER_REFERENCE.md`](ADAPTER_REFERENCE.md) for detailed config and behavior for:

```text
standard_json
institution_policy_xlsx
nara_digital_preservation_framework
nara_preservation_csv      # deprecated alias
pronom_registry
pronom_droid_xml
loc_fdd_xml
qnl_policy_xlsx            # deprecated alias
```

## NARA summary

Preferred adapter:

```text
nara_digital_preservation_framework
```

Current implemented retrieval mode:

```text
published_csv
```

Supported release modes:

```text
explicit_uris
pinned
latest
local_files
```

`latest` mode fallback order:

```text
1. online latest discovery
2. cached .nara_release_index.json
3. fallback_local_files / manual_fallback_files / fallback_files
4. pinned fallback_release_date
```

Use [`NARA_ADAPTER_REQUIREMENTS.md`](NARA_ADAPTER_REQUIREMENTS.md) for detailed NARA hazard/rating behavior and [`NARA_LOCAL_FILES.md`](NARA_LOCAL_FILES.md) for admin-downloaded CSV workflows.

## PRONOM summary

Preferred adapter:

```text
pronom_registry
```

Current implemented retrieval mode:

```text
github_json
```

The adapter can acquire PRONOM JSON records through targeted PUIDs, explicit raw JSON URIs, or a recursive GitHub tree listing.

Use PRONOM when PUID verification matters. PUIDs emitted by PRONOM are verified authority identifiers; PUIDs copied from other sources are useful claims but not verified PRONOM identifiers.

## Future retrieval modes

Future work can add modes inside the same source adapters, for example:

```text
NARA API / linked-data mode
PRONOM individual XML mode
PRONOM DROID signature auto-discovery mode
LOC FDD website/API mode
DPC Bit List mode
```

Those should not change the source-level contract. They should still emit `RawFormatRecord` objects and leave persistence to `RegistryStore`.
