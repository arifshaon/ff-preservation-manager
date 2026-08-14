# Next steps

## 1. Run the MongoDB-backed QNL + NARA build

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
```

The key validation is that MongoDB, not JSON/CSV files, contains the registry state.

## 2. Add baseline/change reports

The NARA-enabled run has proved that the registry is no longer bounded by the institutional workbook and that all `reconcile_hazard()` branches can execute against real data. MongoDB now gives the place to compare runs.

The next architectural gap is change detection:

- Run 1 should be stored as a baseline.
- Run 2 should compare against the prior baseline.
- Source-snapshot hashes should show whether upstream evidence changed.
- Canonical format diffs should show added/removed/changed formats.
- Hazard diffs should show band changes, basis changes, divergence changes, and NARA native-rating movement within the same band.
- Native NARA movement should be reported even when the normalized Low/Moderate/High band is unchanged.

Minimum first report:

```text
added canonical formats
removed canonical formats
changed preferred names/categories/identifiers
changed hazard bands
changed hazard basis
changed external_rating_native
new/resolved divergence flags
new recommended review actions
```

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

The first usable trend input should be NARA native-rating movement between runs, because it can move within a band before the band itself changes.

## 6. Add more retrieval modes only when needed

Possible future modes:

- NARA linked-data/API retrieval if/when available and stable;
- PRONOM individual XML retrieval by appending `.xml` to format page URLs;
- PRONOM DROID signature auto-discovery;
- LOC FDD API or website retrieval;
- DPC Bit List adapter.

These should be added inside source-level adapters where possible rather than creating new source concepts for each file representation.
