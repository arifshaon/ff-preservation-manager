# Repository documentation map

This page is the starting point for documentation across the whole repository.

The project has two active modules with a shared registry/data-access boundary:

```text
qnl_format_registry_builder
        |
        v
shared registry data + RegistryStore contract
        |
        v
preservation_risk_manager
```

Use this map to choose the correct level of documentation instead of reading every file.

## Start by role

| Role / task | Start here |
| --- | --- |
| New user: understand the whole project | [`../README.md`](../README.md) |
| Technical architect | [`REPOSITORY_ARCHITECTURE.md`](REPOSITORY_ARCHITECTURE.md) |
| Developer working with data/storage | [`DATA_MODEL_AND_STORAGE_INTERFACE.md`](DATA_MODEL_AND_STORAGE_INTERFACE.md) |
| Registry operator | [`../qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md`](../qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md) |
| Registry adapter developer | [`../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md) |
| Preservation analyst / risk-manager user | [`../preservation_risk_manager/README.md`](../preservation_risk_manager/README.md) |
| Risk-manager operator | [`../preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md`](../preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md) |
| Human-question / system-integration developer | [`../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md`](../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md) |
| Framework/question-set reviewer | [`../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md`](../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md) |
| AI provider / model integrator | [`../preservation_risk_manager/docs/AI_PROVIDER_INTERFACE.md`](../preservation_risk_manager/docs/AI_PROVIDER_INTERFACE.md) |

## Repository-wide documents

| Document | Purpose |
| --- | --- |
| [`../README.md`](../README.md) | Concise repository overview, active modules, quickstart, and end-to-end flow. |
| [`REPOSITORY_ARCHITECTURE.md`](REPOSITORY_ARCHITECTURE.md) | Module boundaries, end-to-end control/data flow, deterministic-vs-AI boundaries, and ownership. |
| [`DATA_MODEL_AND_STORAGE_INTERFACE.md`](DATA_MODEL_AND_STORAGE_INTERFACE.md) | Shared logical data model, `RegistryStore`, adapters/backends, query/update model, MongoDB example, and risk-manager reader. |

## `qnl_format_registry_builder` documentation

The builder owns source acquisition, normalization, reconciliation, criterion mapping, persistence, and registry updates.

| Need | Document |
| --- | --- |
| Module overview | [`../qnl_format_registry_builder/README.md`](../qnl_format_registry_builder/README.md) |
| Install, configure, and run all builder modes | [`../qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md`](../qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md) |
| Builder-specific documentation map | [`../qnl_format_registry_builder/docs/DOCUMENTATION_MAP.md`](../qnl_format_registry_builder/docs/DOCUMENTATION_MAP.md) |
| Architecture | [`../qnl_format_registry_builder/docs/ARCHITECTURE.md`](../qnl_format_registry_builder/docs/ARCHITECTURE.md) |
| Add/run source adapters | [`../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md) |
| Existing adapter reference | [`../qnl_format_registry_builder/docs/ADAPTER_REFERENCE.md`](../qnl_format_registry_builder/docs/ADAPTER_REFERENCE.md) |
| Implement a source/storage/export adapter | [`../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md) |
| Storage and export configuration | [`../qnl_format_registry_builder/docs/STORAGE_AND_EXPORT_CONFIG.md`](../qnl_format_registry_builder/docs/STORAGE_AND_EXPORT_CONFIG.md) |
| MongoDB physical schema | [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md) |
| Read/interpret the registry | [`../qnl_format_registry_builder/docs/READING_THE_REGISTRY.md`](../qnl_format_registry_builder/docs/READING_THE_REGISTRY.md) |
| Identifier reconciliation | [`../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md`](../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md) |
| Incremental source updates | [`../qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md`](../qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md) |
| Criterion mapping workflow | [`../qnl_format_registry_builder/docs/criterion_mapping_workflow.md`](../qnl_format_registry_builder/docs/criterion_mapping_workflow.md) |
| QNL institutional evidence | [`../qnl_format_registry_builder/docs/QNL_INSTITUTION_FORMAT_EVIDENCE.md`](../qnl_format_registry_builder/docs/QNL_INSTITUTION_FORMAT_EVIDENCE.md) |
| Institutional policy overlays | [`../qnl_format_registry_builder/docs/INSTITUTIONAL_OVERLAYS.md`](../qnl_format_registry_builder/docs/INSTITUTIONAL_OVERLAYS.md) |
| Source retrieval/cache/offline behavior | [`../qnl_format_registry_builder/docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md`](../qnl_format_registry_builder/docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md) |

## `preservation_risk_manager` documentation

The risk manager owns format resolution, evidence assembly, framework-driven deterministic assessment, evidence-gap/remediation analysis, human rendering, machine request execution, and bounded AI assistance.

| Need | Document |
| --- | --- |
| Module overview | [`../preservation_risk_manager/README.md`](../preservation_risk_manager/README.md) |
| Risk-manager documentation map | [`../preservation_risk_manager/docs/DOCUMENTATION_MAP.md`](../preservation_risk_manager/docs/DOCUMENTATION_MAP.md) |
| Architecture and module responsibilities | [`../preservation_risk_manager/docs/ARCHITECTURE.md`](../preservation_risk_manager/docs/ARCHITECTURE.md) |
| Install, setup, and run all modes | [`../preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md`](../preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md) |
| Human questions and machine requests | [`../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md`](../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md) |
| Preservation-risk domains/questions | [`../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md`](../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md) |
| AI provider interface | [`../preservation_risk_manager/docs/AI_PROVIDER_INTERFACE.md`](../preservation_risk_manager/docs/AI_PROVIDER_INTERFACE.md) |

## Documentation boundaries

Some subjects appear in more than one place. Use these boundaries:

| Subject | Canonical documentation |
| --- | --- |
| What each top-level module does | `README.md` + `docs/REPOSITORY_ARCHITECTURE.md` |
| Shared logical data model and backend contract | `docs/DATA_MODEL_AND_STORAGE_INTERFACE.md` |
| MongoDB collection/index details | `qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md` |
| How to write a new backend | `qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md` |
| Builder commands/configuration | `qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md` |
| Risk-manager commands/configuration | `preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md` |
| Human vs machine query semantics | `preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md` |
| Meaning of the 8-domain question set | `preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md` |

## Key design rules repeated across the documentation

1. The registry is built from evidence; it is not manually maintained as one authoritative spreadsheet.
2. Source-native data and provenance are retained before normalization/mapping.
3. Strong identifier reconciliation is conservative and authority-aware.
4. Institutional evidence is scoped and does not silently become global evidence.
5. The common storage contract is backend-neutral; MongoDB is one adapter.
6. The registry builder owns normal registry writes/updates.
7. The risk manager reads the same store through `RegistryReader` and does not directly couple assessment logic to MongoDB.
8. Deterministic scoring/framework rules are authoritative for risk calculation.
9. AI can route, interpret bounded evidence, or review; it cannot invent evidence or silently change deterministic policy/scoring.
10. Human and machine interfaces use the same canonical request/execution layer; only presentation differs.
