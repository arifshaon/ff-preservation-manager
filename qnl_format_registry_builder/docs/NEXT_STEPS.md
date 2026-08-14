# Next steps

## 1. Test baseline/change detection with file storage, then MongoDB

Change detection is now implemented. The first run against an empty selected store is a `baseline` run. Later runs against the same store path/database compare the previous current registry view to the new build and persist typed events in `assessment_changes`.

Test with file storage first:

```json
{
  "storage": {
    "type": "file",
    "path": "output/change_test_store"
  },
  "exports": {
    "enabled": true
  }
}
```

Run once with one NARA source version, then run again with another NARA source version or edited test source. The second run should produce change counts such as:

```text
record_added
record_removed
preferred_name_changed
category_changed
identifiers_changed
hazard_band_changed
hazard_basis_changed
external_rating_native_changed
divergence_opened
divergence_resolved
```

Then repeat with MongoDB by changing only the storage block:

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry_change_test"
  },
  "exports": {
    "enabled": false
  }
}
```

Verify:

```text
assessment_changes
canonical_formats current:false records for removals
runs.change_detection
```

## 2. Run the MongoDB-backed QNL + NARA build

Install the MongoDB dependency:

```bash
python -m pip install -e ".[dev,mongo]"
```

Use `storage.type: mongodb` and enable the QNL and NARA sources. For a database-only run, set:

```json
{
  "exports": {
    "enabled": false
  }
}
```

Then verify MongoDB collection counts:

```text
runs
source_snapshots
source_records
canonical_formats
format_identifiers
institution_policy_overlays
hazard_assessments
assessment_changes
```

The key validation is that MongoDB, not JSON/CSV files, contains the registry state.

## 3. Run a targeted PRONOM registry test

For a small PRONOM source test, enable `pronom_registry` and use targeted PUIDs first:

```json
{
  "type": "pronom_registry",
  "puids": ["fmt/18", "fmt/95"]
}
```

Then move to the recursive GitHub tree mode once the targeted run is clean.

## 4. Move remaining export logic into exporter adapters

The pipeline now treats file outputs as optional exports and can run database-only. The remaining cleanup is to move the implementation of JSON, JSONL, CSV, SQLite, and Markdown writing out of `pipeline.py` into exporter adapters.

## 5. Add trend evidence connectors

Trend should remain `Insufficient Evidence` until connectors exist for specification vitality, implementation vitality, and authority warnings.

The first usable trend input is now NARA native-rating movement between runs, because it can move within a band before the band itself changes. The change detector already surfaces `external_rating_native_changed`.

## 6. Add more retrieval modes only when needed

Possible future modes:

- NARA linked-data/API retrieval if/when available and stable;
- PRONOM individual XML retrieval by appending `.xml` to format page URLs;
- PRONOM DROID signature auto-discovery;
- LOC FDD API or website retrieval;
- DPC Bit List adapter.

These should be added inside source-level adapters where possible rather than creating new source concepts for each file representation.
