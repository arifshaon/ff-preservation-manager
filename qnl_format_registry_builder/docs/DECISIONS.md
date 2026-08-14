# Design decisions

## 2026-08-14: Storage and export adapters

Decision: use adapter-based storage and export layers.

Rationale:

- The live registry must be queryable, so MongoDB will be the first production storage backend.
- The pipeline should not depend directly on MongoDB so that MySQL, PostgreSQL, SQLite, or another backend can be substituted later.
- JSON, JSONL, CSV, SQLite, Markdown, and future API bundles are export products, not separate sources of truth.
- Exports should be enabled through configuration only when their adapter exists.

Consequences:

- Add a `RegistryStore` interface.
- Add a `RegistryExporter` interface.
- Keep source acquisition, persistence, and export responsibilities separate.
- Refactor existing direct file writes out of `pipeline.py` in the next implementation phase.
