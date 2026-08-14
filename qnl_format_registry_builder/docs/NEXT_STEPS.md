# Next steps

## 1. Run the NARA-enabled pipeline against the real workbook

Enable both sources in `config/sources.example.json`:

```text
qnl_policy_current
nara_digital_preservation_framework
```

Then inspect:

- `hazard_assessment.basis` counts;
- `corroborated` records;
- `institution_override` records;
- `external_only` records;
- divergence/review-required records;
- unmatched institutional rows with no NARA bridge.

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

## 6. Add baseline/change reports

Run 1 should produce a baseline report. Later runs should produce change reports against prior runs.

## 7. Add trend evidence connectors

Trend should remain `Insufficient Evidence` until connectors exist for specification vitality, implementation vitality, and authority warnings.

## 8. Add more retrieval modes only when needed

Possible future modes:

- NARA linked-data/API retrieval if/when available and stable;
- PRONOM individual XML retrieval by appending `.xml` to format page URLs;
- PRONOM DROID signature auto-discovery;
- LOC FDD API or website retrieval;
- DPC Bit List adapter.

These should be added inside source-level adapters where possible rather than creating new source concepts for each file representation.
