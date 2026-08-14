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

## 2. Move export logic into exporters

The current pipeline writes JSON, JSONL, CSV, SQLite, and Markdown directly. Move that logic into exporter adapters so exports are enabled through configuration.

## 3. Refactor pipeline to use RegistryStore

The pipeline should write snapshots, source records, canonical formats, identifiers, institutional overlays, assessments, and changes through `RegistryStore`.

## 4. Implement MongoRegistryStore

Use PyMongo to implement the collections described in `ARCHITECTURE.md`.

## 5. Add baseline/change reports

Run 1 should produce a baseline report. Later runs should produce change reports against prior runs.

## 6. Add trend evidence connectors

Trend should remain `Insufficient Evidence` until connectors exist for specification vitality, implementation vitality, and authority warnings.
