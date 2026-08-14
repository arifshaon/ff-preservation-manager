# Next steps

## 1. Add baseline/change reports

The NARA-enabled run has proved that the registry is no longer bounded by the institutional workbook and that all `reconcile_hazard()` branches can execute against real data.

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

## 2. Run a targeted PRONOM registry test

For a small PRONOM source test, enable `pronom_registry` and use targeted PUIDs first:

```json
{
  "type": "pronom_registry",
  "puids": ["fmt/18", "fmt/95"]
}
```

Then move to the recursive GitHub tree mode once the targeted run is clean.

## 3. Move export logic into exporters

The current pipeline writes JSON, JSONL, CSV, SQLite, and Markdown directly. Move that logic into exporter adapters so exports are enabled through configuration.

## 4. Refactor pipeline to use RegistryStore

The pipeline should write snapshots, source records, canonical formats, identifiers, institutional overlays, assessments, and changes through `RegistryStore`.

## 5. Implement MongoRegistryStore

Use PyMongo to implement the collections described in `ARCHITECTURE.md`.

## 6. Add trend evidence connectors

Trend should remain `Insufficient Evidence` until connectors exist for specification vitality, implementation vitality, and authority warnings.

The first usable trend input should be NARA native-rating movement between runs, because it can move within a band before the band itself changes.

## 7. Add more retrieval modes only when needed

Possible future modes:

- NARA linked-data/API retrieval if/when available and stable;
- PRONOM individual XML retrieval by appending `.xml` to format page URLs;
- PRONOM DROID signature auto-discovery;
- LOC FDD API or website retrieval;
- DPC Bit List adapter.

These should be added inside source-level adapters where possible rather than creating new source concepts for each file representation.
