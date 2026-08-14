# Next steps

## 1. Move export logic into exporters

The current pipeline writes JSON, JSONL, CSV, SQLite, and Markdown directly. Move that logic into exporter adapters so exports are enabled through configuration.

## 2. Refactor pipeline to use RegistryStore

The pipeline should write snapshots, source records, canonical formats, identifiers, QNL overlays, assessments, and changes through `RegistryStore`.

## 3. Implement MongoRegistryStore

Use PyMongo to implement the collections described in `ARCHITECTURE.md`.

## 4. Add NARA source adapter

NARA should be the first serious external hazard estimator to reconcile against QNL criteria and policy overlays.

## 5. Add baseline/change reports

Run 1 should produce a baseline report. Later runs should produce change reports against prior runs.

## 6. Add trend evidence connectors

Trend should remain `Insufficient Evidence` until connectors exist for specification vitality, implementation vitality, and authority warnings.
