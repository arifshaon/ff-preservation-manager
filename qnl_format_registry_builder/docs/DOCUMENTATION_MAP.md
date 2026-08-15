# Documentation map

This map is the starting point for the documentation. Use it to avoid reading every file.

## Audiences

| Audience | Start here |
| --- | --- |
| New user or operator | `README.md` |
| Preservation officer reading outputs | `READING_THE_REGISTRY.md` |
| Administrator configuring sources/storage | `ADDING_AND_RUNNING_DATA_SOURCES.md`, `ADAPTER_REFERENCE.md`, `STORAGE_AND_EXPORT_CONFIG.md` |
| Developer adding an adapter | `ADDING_AND_RUNNING_DATA_SOURCES.md`, `ADAPTER_IMPLEMENTATION_GUIDE.md` |
| Developer changing matching/update logic | `IDENTIFIER_RECONCILIATION.md`, `INCREMENTAL_SOURCE_UPDATES.md` |
| Maintainer planning future work | `NEXT_STEPS.md` |

## Start here

| Need | Read |
| --- | --- |
| Understand the project goal and run the default multi-source quickstart | `README.md` |
| Navigate all documentation | `docs/DOCUMENTATION_MAP.md` |
| Add a new data source, choose downloaded-file/JSON/CSV/archive acquisition, or run NARA/PRONOM/LOC individually | `docs/ADDING_AND_RUNNING_DATA_SOURCES.md` |
| Add QNL-specific preservation-risk evidence for formats such as PDF and netCDF | `docs/QNL_INSTITUTION_FORMAT_EVIDENCE.md` |
| Interpret `registry.csv`, `registry.json`, MongoDB records, hazard fields, review flags, and change events | `docs/READING_THE_REGISTRY.md` |
| Understand the end-to-end architecture and source-adapter concept | `docs/ARCHITECTURE.md` |
| Understand source retrieval, cache, offline replay, local files, and fallback logic | `docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md` |
| Understand source-by-source augmentation and active evidence reuse | `docs/INCREMENTAL_SOURCE_UPDATES.md` |
| Understand verified-only strong identifier reconciliation | `docs/IDENTIFIER_RECONCILIATION.md` |
| Configure existing adapter types | `docs/ADAPTER_REFERENCE.md` |
| Build a new source/storage/export adapter | `docs/ADAPTER_IMPLEMENTATION_GUIDE.md` |
| Understand NARA release modes and local admin files | `docs/NARA_LOCAL_FILES.md` and `docs/NARA_ADAPTER_REQUIREMENTS.md` |
| Configure MongoDB, file storage, and exports | `docs/STORAGE_AND_EXPORT_CONFIG.md` |
| Understand MongoDB collections, fields, indexes, and queries | `docs/MONGODB_STORAGE_SCHEMA.md` |
| Understand institutional policy overlays such as QNL | `docs/INSTITUTIONAL_OVERLAYS.md` |
| Understand preservation method profiles | `docs/PRESERVATION_METHOD_PROFILES.md` |
| Understand method coverage states and caveats | `docs/METHOD_COVERAGE_NOTES.md` |
| Understand implementation decisions and constraints | `docs/DECISIONS.md` |
| Review current roadmap | `docs/NEXT_STEPS.md` |

## Live reference documents

| Document | Status | Purpose |
| --- | --- | --- |
| `DOCUMENTATION_MAP.md` | Live | This navigation map. |
| `ARCHITECTURE.md` | Live | Core design, source-adapter concept, storage/export boundaries. |
| `READING_THE_REGISTRY.md` | Live | User-facing glossary and examples for preservation officers. |
| `ADDING_AND_RUNNING_DATA_SOURCES.md` | Live | Practical runbook for adding source adapters, choosing downloaded-file/JSON/CSV/archive acquisition, and running sources together or individually. |
| `QNL_INSTITUTION_FORMAT_EVIDENCE.md` | Live | QNL-specific preservation-risk evidence source, seed data, template, and run instructions. |
| `SOURCE_RETRIEVAL_AND_FALLBACKS.md` | Live | Online, cached, offline, local-file, fallback and required/optional behavior. |
| `INCREMENTAL_SOURCE_UPDATES.md` | Live | Source-by-source augmentation model and active evidence reuse. |
| `IDENTIFIER_RECONCILIATION.md` | Live | Verified identifier rules and strong-key matching behavior. |
| `ADAPTER_IMPLEMENTATION_GUIDE.md` | Live | How to implement adapters. |
| `ADAPTER_REFERENCE.md` | Live | Existing adapter configuration and behavior. |
| `NARA_ADAPTER_REQUIREMENTS.md` | Live | Detailed NARA requirements and hazard/rating behavior. |
| `NARA_LOCAL_FILES.md` | Live | Admin-downloaded NARA CSV workflows. |
| `STORAGE_AND_EXPORT_CONFIG.md` | Live | Storage backends and optional exports. |
| `MONGODB_STORAGE_SCHEMA.md` | Live | MongoDB collection and field reference. |
| `INSTITUTIONAL_OVERLAYS.md` | Live | Institution-specific policy and decision overlays. |
| `PRESERVATION_METHOD_PROFILES.md` | Live | Method-profile assignment model. |
| `METHOD_COVERAGE_NOTES.md` | Live | Coverage-state interpretation and caveats. |
| `DECISIONS.md` | Live | Design decisions and rationale. |
| `NEXT_STEPS.md` | Live | Remaining work and roadmap. |

## Historical notes

Historical planning or refactor notes live under:

```text
docs/history/
```

They are kept for context, not as current implementation guidance.

| Historical note | Why it exists |
| --- | --- |
| `docs/history/ADAPTER_REFACTOR_PLAN.md` | Completed storage/export refactor tracking note. |

## How the documents fit together

```text
README.md
  -> quickstart and common operator path

DOCUMENTATION_MAP.md
  -> choose the right document

ADDING_AND_RUNNING_DATA_SOURCES.md
  -> practical source plug-in and runbook: downloaded file, JSON, CSV, archive, individual runs

QNL_INSTITUTION_FORMAT_EVIDENCE.md
  -> QNL-specific evidence template for future preservation-risk analysis

READING_THE_REGISTRY.md
  -> understand generated outputs and MongoDB records

ARCHITECTURE.md
  -> design model, adapter boundaries, storage/export separation

SOURCE_RETRIEVAL_AND_FALLBACKS.md
  -> acquisition modes, cache, offline, local files, required/optional sources

INCREMENTAL_SOURCE_UPDATES.md
  -> source-by-source registry augmentation

IDENTIFIER_RECONCILIATION.md
  -> verified identifiers and strong-key matching

ADAPTER_REFERENCE.md
  -> configure built-in adapters

ADAPTER_IMPLEMENTATION_GUIDE.md
  -> build a new adapter

STORAGE_AND_EXPORT_CONFIG.md + MONGODB_STORAGE_SCHEMA.md
  -> storage and database details
```

## Adapter documentation boundary

The adapter docs have a clean split:

| Document | Boundary |
| --- | --- |
| `ARCHITECTURE.md` | Concept: what a source adapter is and where it fits. |
| `ADDING_AND_RUNNING_DATA_SOURCES.md` | Runbook: how to plug in and run a source today, including MongoDB configs and acquisition patterns. |
| `ADAPTER_IMPLEMENTATION_GUIDE.md` | Build: how to implement a new adapter class. |
| `ADAPTER_REFERENCE.md` | Configure: how existing adapters work. |

## Naming rules

Use source-level names for adapters wherever possible:

```text
nara_digital_preservation_framework
pronom_registry
loc_fdd_xml
institution_policy_xlsx
qnl_institution_format_evidence
```

Avoid naming a new adapter after a temporary file representation unless that representation is truly the source boundary. For example, CSV is only NARA's current publication format, so the preferred adapter is `nara_digital_preservation_framework`, not `nara_csv`.

Compatibility aliases can remain for old names, but new configuration should use the source-level name.

## Documentation standard for each adapter

Each adapter section should answer the same questions:

- What source does it represent?
- When should it be used?
- What config fields does it accept?
- How does acquisition work?
- Does it support online, offline, cache, local files, pinned/latest release modes, or fallback files?
- What does it emit into `RawFormatRecord`?
- Which identifiers are verified by this adapter?
- What can fail, and whether it should be `required:true` or `required:false`?
- Which tests prove the adapter works?
