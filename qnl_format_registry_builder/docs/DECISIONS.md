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

## 2026-08-14: Institutional policy overlays

Decision: make the core policy overlay model institution-neutral.

Rationale:

- QNL is the first use case, but the registry builder should also support other libraries, archives, repositories, and memory institutions.
- A local policy spreadsheet represents one institution's view of a format; it is not the canonical universe of formats.
- Local risk terms, local identifiers, local actions, and local tools differ by institution and must be supplied as configuration/data.
- QNL-specific terminology should not appear in the core domain model except as a backwards-compatible alias or example configuration.

Consequences:

- Prefer `institution_policy_xlsx` over `qnl_policy_xlsx`.
- Prefer `institution_policy_overlays` over `qnl_policy_overlay`.
- Prefer `institution_format_id` over `qnl_format_id`.
- Store local policy terms as `local_risk_level`, `local_preservation_action`, `local_preservation_plan`, `local_preferred_tools`, and `local_conversion_process`.
- Keep `qnl_policy_xlsx` only as a deprecated compatibility alias.
- Add `config/institutions/qnl.example.json` as the first institutional profile example.
