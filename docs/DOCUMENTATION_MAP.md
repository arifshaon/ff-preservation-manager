# Repository documentation map

This page is the starting point for documentation across the whole repository.

```text
qnl_format_registry_builder
        |
        v
shared registry data + RegistryStore contract
        |
        v
preservation_risk_manager
```

## Start by task

| Role / task | Start here |
| --- | --- |
| New user: clone → mapped registry → risk assessment | [`GETTING_STARTED.md`](GETTING_STARTED.md) |
| Understand the whole project | [`../README.md`](../README.md) |
| Understand the backend-neutral data model | [`DATA_MODEL.md`](DATA_MODEL.md) |
| Technical architect | [`REPOSITORY_ARCHITECTURE.md`](REPOSITORY_ARCHITECTURE.md) |
| Developer working with storage/query/update adapters | [`DATA_MODEL_AND_STORAGE_INTERFACE.md`](DATA_MODEL_AND_STORAGE_INTERFACE.md) |
| Add any new source | [`HOW_TO_ADD_A_SOURCE.md`](HOW_TO_ADD_A_SOURCE.md) |
| Add a PDF/narrative/unstructured source | [`TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](TRANSCRIBING_UNSTRUCTURED_SOURCES.md) |
| Registry operator | [`../qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md`](../qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md) |
| New-source / criterion-mapping operator | [`../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md) |
| Registry adapter developer | [`../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md) |
| Preservation analyst | [`../preservation_risk_manager/docs/RISK_ANALYSIS_WORKFLOW.md`](../preservation_risk_manager/docs/RISK_ANALYSIS_WORKFLOW.md) |
| Risk-manager operator | [`../preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md`](../preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md) |
| CLI user | [`../preservation_risk_manager/docs/CLI_REFERENCE.md`](../preservation_risk_manager/docs/CLI_REFERENCE.md) |
| Human-question / system-integration developer | [`../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md`](../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md) |
| Framework author/reviewer | [`../preservation_risk_manager/docs/FRAMEWORKS.md`](../preservation_risk_manager/docs/FRAMEWORKS.md) |
| 8-domain question-set reviewer | [`../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md`](../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md) |
| AI/local-model integrator | [`../preservation_risk_manager/docs/AI_ASSISTED_ANALYSIS.md`](../preservation_risk_manager/docs/AI_ASSISTED_ANALYSIS.md) |
| Periodic monitoring/reporting operator | [`../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md`](../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md) |
| Risk-manager developer | [`../preservation_risk_manager/docs/MODULE_REFERENCE.md`](../preservation_risk_manager/docs/MODULE_REFERENCE.md) |

## Repository-wide documents

| Document | Purpose |
| --- | --- |
| [`../README.md`](../README.md) | Repository overview, AI-assisted workflows, and short end-to-end example. |
| [`GETTING_STARTED.md`](GETTING_STARTED.md) | Tested conceptual path across both packages, including criterion-claim export handoff. |
| [`DATA_MODEL.md`](DATA_MODEL.md) | Canonical backend-neutral entity/collection/transformation model, including `criterion_claims` and in-flight Python types. |
| [`DATA_MODEL_AND_STORAGE_INTERFACE.md`](DATA_MODEL_AND_STORAGE_INTERFACE.md) | `RegistryStore`, adapters/backends, query/update boundary and `RegistryReader`. |
| [`HOW_TO_ADD_A_SOURCE.md`](HOW_TO_ADD_A_SOURCE.md) | Seven-step source onboarding router from acquisition to risk-manager verification. |
| [`TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](TRANSCRIBING_UNSTRUCTURED_SOURCES.md) | Manual/AI transcription of PDF/HTML/narrative sources into reviewed versioned JSON. |
| [`REPOSITORY_ARCHITECTURE.md`](REPOSITORY_ARCHITECTURE.md) | Module boundaries, data/control flow and deterministic-vs-AI responsibilities. |
| [`DOCUMENTATION_MAP.md`](DOCUMENTATION_MAP.md) | This navigation index. |

## Registry Builder documentation

The builder owns source acquisition, normalization, reconciliation, criterion mapping, persistence and registry updates.

| Need | Document |
| --- | --- |
| Module overview | [`../qnl_format_registry_builder/README.md`](../qnl_format_registry_builder/README.md) |
| Builder documentation map | [`../qnl_format_registry_builder/docs/DOCUMENTATION_MAP.md`](../qnl_format_registry_builder/docs/DOCUMENTATION_MAP.md) |
| Install/setup/run | [`../qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md`](../qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md) |
| Add/run structured sources and adapters | [`../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md) |
| Add/map external or institution source | [`../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md) |
| Criterion mapping lifecycle | [`../qnl_format_registry_builder/docs/criterion_mapping_workflow.md`](../qnl_format_registry_builder/docs/criterion_mapping_workflow.md) |
| Adapter reference | [`../qnl_format_registry_builder/docs/ADAPTER_REFERENCE.md`](../qnl_format_registry_builder/docs/ADAPTER_REFERENCE.md) |
| Adapter implementation | [`../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md) |
| Read registry data | [`../qnl_format_registry_builder/docs/READING_THE_REGISTRY.md`](../qnl_format_registry_builder/docs/READING_THE_REGISTRY.md) |
| Identifier reconciliation | [`../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md`](../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md) |
| Incremental updates | [`../qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md`](../qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md) |
| Storage/export config | [`../qnl_format_registry_builder/docs/STORAGE_AND_EXPORT_CONFIG.md`](../qnl_format_registry_builder/docs/STORAGE_AND_EXPORT_CONFIG.md) |
| MongoDB physical schema/indexes | [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md) |
| QNL institution evidence | [`../qnl_format_registry_builder/docs/QNL_INSTITUTION_FORMAT_EVIDENCE.md`](../qnl_format_registry_builder/docs/QNL_INSTITUTION_FORMAT_EVIDENCE.md) |
| Source cache/offline/fallbacks | [`../qnl_format_registry_builder/docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md`](../qnl_format_registry_builder/docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md) |

### Unstructured-source / DPC path

```text
DPC Bit List PDF/HTML
 -> AI-assisted or manual transcription draft
 -> human-reviewed JSON
 -> standard_json or thin DPC adapter
 -> RawFormatRecord
 -> canonical reconciliation
 -> DPC criterion mapping
 -> criterion_claims
 -> preservation_risk_manager
```

Use:

- [`TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](TRANSCRIBING_UNSTRUCTURED_SOURCES.md)
- transcription schema: `qnl_format_registry_builder/config/schemas/unstructured_source_transcription.v1.schema.json`
- DPC transcription prompt: `qnl_format_registry_builder/config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md`
- DPC mapping prompt: `qnl_format_registry_builder/config/prompts/propose_mapping/dpc_bit_list.v1.md`

Both AI outputs are drafts and require human review.

### Quickstart configuration distinction

```text
config/sources.example.json
  -> registry construction example
  -> criterion mapping not enabled

config/sources.criterion-mapping.quickstart.json
  -> no-database cross-package quickstart
  -> criterion mapping enabled
  -> exports registry.json + criterion_claims.jsonl
```

Use the second when testing the risk-manager handoff.

## Preservation Risk Manager documentation

The risk manager owns format resolution, evidence assembly, deterministic framework assessment, gap/remediation analysis, human rendering, machine request execution and bounded AI assistance.

| Need | Document |
| --- | --- |
| Module overview | [`../preservation_risk_manager/README.md`](../preservation_risk_manager/README.md) |
| Module documentation map | [`../preservation_risk_manager/docs/DOCUMENTATION_MAP.md`](../preservation_risk_manager/docs/DOCUMENTATION_MAP.md) |
| Architecture | [`../preservation_risk_manager/docs/ARCHITECTURE.md`](../preservation_risk_manager/docs/ARCHITECTURE.md) |
| Risk-analysis workflow / suppression reasons | [`../preservation_risk_manager/docs/RISK_ANALYSIS_WORKFLOW.md`](../preservation_risk_manager/docs/RISK_ANALYSIS_WORKFLOW.md) |
| Framework schema / calibration | [`../preservation_risk_manager/docs/FRAMEWORKS.md`](../preservation_risk_manager/docs/FRAMEWORKS.md) |
| Install/setup/run | [`../preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md`](../preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md) |
| CLI reference | [`../preservation_risk_manager/docs/CLI_REFERENCE.md`](../preservation_risk_manager/docs/CLI_REFERENCE.md) |
| Human questions / machine requests | [`../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md`](../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md) |
| AI modes / local + Azure model setup | [`../preservation_risk_manager/docs/AI_ASSISTED_ANALYSIS.md`](../preservation_risk_manager/docs/AI_ASSISTED_ANALYSIS.md) |
| Provider-level AI config | [`../preservation_risk_manager/docs/AI_PROVIDER_INTERFACE.md`](../preservation_risk_manager/docs/AI_PROVIDER_INTERFACE.md) |
| 8 domains / 22 questions | [`../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md`](../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md) |
| Monitoring/reporting | [`../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md`](../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md) |
| Module-by-module code reference | [`../preservation_risk_manager/docs/MODULE_REFERENCE.md`](../preservation_risk_manager/docs/MODULE_REFERENCE.md) |

## Cross-package handoff

Two supported paths exist.

### Persistent storage

```text
registry_builder -> RegistryStore -> RegistryReader -> risk manager
```

Use `--storage-config`.

### Export files

```text
registry_builder output/registry.json
registry_builder output/criterion_claims.jsonl
                 |
                 v
JsonRegistryStore
                 |
                 v
risk manager
```

When `--registry-json` points to `registry.json`, the risk manager auto-discovers sibling `criterion_claims.jsonl` or `criterion_claims.json`.

This handoff is covered by regression tests.

## Core design rules

1. Registry data is built from evidence; it is not a static manually maintained list.
2. Source-native evidence and provenance are preserved before normalization.
3. Unstructured sources become reviewed, versioned structured artifacts before normal ingestion.
4. Criterion claims are neutral observations; frameworks interpret them as risk.
5. Institutional evidence remains institution-scoped.
6. MongoDB is one storage adapter, not the data model or business-logic boundary.
7. The registry builder owns normal registry writes/updates.
8. The risk manager reads through `RegistryReader` and does not duplicate MongoDB logic.
9. Deterministic framework/scoring logic remains authoritative.
10. AI may transcribe, route, interpret bounded evidence, review raw evidence or draft mappings, but cannot silently alter approved evidence/scoring/policy.
11. AI transcription and AI criterion mapping are separate reviewable artifacts.
12. Human and machine interfaces share the same canonical request/execution layer.
13. A suppressed/unknown band must not be interpreted as Low risk.
