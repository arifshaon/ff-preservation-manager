# Source adapters

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

## Snapshot cache and offline mode

Source acquisition now uses a content-addressed snapshot cache under:

```text
work/snapshots/<source_id>/
```

Each source keeps a `.snapshot_index.json` mapping source URI to the latest cached SHA-256 and local snapshot path.

Online mode still checks the upstream source, but it reports whether each snapshot changed:

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

## NARA

Preferred adapter:

```text
nara_digital_preservation_framework
```

Current implemented retrieval mode:

```text
published_csv
```

The adapter currently retrieves and parses NARA's published Digital Preservation Framework CSV files from the public GitHub/raw dataset. It preserves NARA native numeric ratings and also emits normalized Low/Moderate/High values for current hazard reconciliation.

The old adapter name remains available:

```text
nara_preservation_csv
```

but new configurations should not use it.

## PRONOM

Preferred adapter:

```text
pronom_registry
```

Current implemented retrieval mode:

```text
github_json
```

The adapter can acquire PRONOM JSON records in three ways:

1. Targeted PUIDs:

```json
{
  "type": "pronom_registry",
  "puids": ["fmt/18", "x-fmt/111"]
}
```

2. Explicit raw JSON URIs:

```json
{
  "type": "pronom_registry",
  "uris": [
    "https://raw.githubusercontent.com/nationalarchives/pronom/develop/signatures/fmt/18.json"
  ]
}
```

3. Recursive GitHub tree listing:

```json
{
  "type": "pronom_registry",
  "github_tree_url": "https://api.github.com/repos/nationalarchives/pronom/git/trees/develop?recursive=1",
  "raw_base_url": "https://raw.githubusercontent.com/nationalarchives/pronom/develop",
  "include_paths": ["signatures/fmt/", "signatures/x-fmt/"]
}
```

The tree mode is the closest current equivalent to a source-level retrieval workflow without scraping PRONOM web pages.

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
