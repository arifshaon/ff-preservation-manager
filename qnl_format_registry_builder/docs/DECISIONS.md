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
- The pipeline should write through the selected storage backend and generate optional exports separately.

## 2026-08-14: MongoDB as first real storage backend

Decision: implement MongoDB as the first production `RegistryStore` backend.

Rationale:

- The registry needs a queryable, durable backend for canonical formats, identifiers, institutional overlays, hazard assessments, source records and run history.
- JSON/CSV/SQLite/Markdown outputs are useful exports, but they should not be required staging files before MongoDB persistence.
- A common storage interface keeps future MySQL, PostgreSQL, SQLite, or file-backed stores possible without changing source adapters or reconciliation logic.

Consequences:

- `storage.type: mongodb` now persists directly to MongoDB through `MongoRegistryStore`.
- The pipeline creates exactly one active storage backend per run through `create_store()`.
- The pipeline persists `SourceSnapshot`, `RawFormatRecord`, `CanonicalFormat`, identifier claims, institutional overlays, hazard assessments, readiness records and trend records through `RegistryStore`.
- File exports are controlled by `exports.enabled`; database-only runs can set `exports.enabled: false`.
- PyMongo is an optional dependency installed with `python -m pip install -e ".[mongo]"`.
- `storage.type: memory` remains the default in the sample config so a clean clone can still run without infrastructure.

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

## 2026-08-14: Source-first adapter names

Decision: source adapters should be named for the authority/source, not for the current file representation.

Rationale:

- Sources such as NARA, PRONOM and LOC may expose CSV, XLSX, XML, JSON, APIs, linked data, or web pages at different times.
- The architecture needs a stable source-level boundary: the adapter understands the source and can add retrieval modes internally.
- Representation-specific names make the project look like it expects every source to provide a CSV or XML file.

Consequences:

- Prefer `nara_digital_preservation_framework` over `nara_preservation_csv`.
- Prefer `pronom_registry` over representation-specific PRONOM names for new PRONOM work.
- Keep `nara_preservation_csv` as a deprecated compatibility alias because it already existed.
- Keep `pronom_droid_xml` as a representation-specific adapter for DROID signature XML.
- Document retrieval modes such as `published_csv` and `github_json` separately from source identity.

## 2026-08-14: NARA source adapter and conservative external matching

Decision: add `nara_digital_preservation_framework` as the first real external hazard-source adapter, with `published_csv` as the current retrieval mode.

Rationale:

- Institutional policy workbooks alone produce `institution_only` hazard assessments.
- NARA provides an external preservation-risk baseline that can activate `external_only`, `corroborated`, `institution_override`, and divergence outputs.
- NARA's native numeric rating is useful for later trend/calibration work and must not be lost when mapping to Low/Moderate/High.
- Institutional rows often do not carry NARA Format IDs, so they need a safe way to connect to NARA records.

Consequences:

- Parse both NARA preservation action plan CSV and NARA numbered risk matrix CSV under the source-level NARA adapter.
- Treat NARA Format IDs as verified NARA identifiers.
- Keep PUIDs found in NARA PRONOM URLs as unverified PUID claims unless PRONOM confirms them.
- Store NARA native numeric risk rating and `native_direction: higher_is_safer` alongside normalized hazard rating.
- Allow `name + extension` weak matching only when it uniquely bridges a non-authority/institutional group to exactly one verified authority group.

## 2026-08-14: PRONOM registry GitHub JSON adapter

Decision: add `pronom_registry` as the source-level PRONOM adapter, with `github_json` as the current implemented retrieval mode.

Rationale:

- PRONOM data is available as a GitHub JSON dataset, which avoids scraping PRONOM web pages.
- PUID authority should come from PRONOM source data, not from PUID strings copied into unrelated spreadsheets or URLs.
- Targeted PUID retrieval and full tree-based retrieval are both useful: targeted runs are fast for tests; tree-based runs support source refresh.

Consequences:

- `pronom_registry` can retrieve explicit PUIDs, explicit raw JSON URIs, or the recursive GitHub tree listing.
- PUIDs emitted by `pronom_registry` are verified PUID identifiers.
- `pronom_droid_xml` remains available as a DROID XML representation-specific adapter.
