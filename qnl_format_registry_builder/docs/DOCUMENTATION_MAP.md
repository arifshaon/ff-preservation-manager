# Registry Builder documentation map

This map is the starting point for documentation specific to `qnl_format_registry_builder`.

For repository-wide concepts, start with:

- canonical backend-neutral data model: [`../../docs/DATA_MODEL.md`](../../docs/DATA_MODEL.md)
- repository architecture: [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- storage/query/update interface: [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
- single source-onboarding router: [`../../docs/HOW_TO_ADD_A_SOURCE.md`](../../docs/HOW_TO_ADD_A_SOURCE.md)

## Start by task

| Task | Start here |
| --- | --- |
| Install, configure, and run the builder | [`INSTALLATION_SETUP_AND_RUN.md`](INSTALLATION_SETUP_AND_RUN.md) |
| Understand what the module does | [`../README.md`](../README.md) |
| Understand the canonical data model | [`../../docs/DATA_MODEL.md`](../../docs/DATA_MODEL.md) |
| Interpret generated registry data | [`READING_THE_REGISTRY.md`](READING_THE_REGISTRY.md) |
| Add any new data source end-to-end | [`../../docs/HOW_TO_ADD_A_SOURCE.md`](../../docs/HOW_TO_ADD_A_SOURCE.md) |
| Add/run a structured data source | [`ADDING_AND_RUNNING_DATA_SOURCES.md`](ADDING_AND_RUNNING_DATA_SOURCES.md) |
| Add a PDF/HTML/narrative source | [`../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md) |
| Add criteria/map a new external source | [`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md) |
| Add institution-scoped criteria/evidence | [`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md) |
| Generate a DPC Bit List transcription draft with AI | [`../config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md`](../config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md) |
| Generate a DPC Bit List criterion-mapping draft with AI | [`../config/prompts/propose_mapping/dpc_bit_list.v1.md`](../config/prompts/propose_mapping/dpc_bit_list.v1.md) |
| Configure existing adapters | [`ADAPTER_REFERENCE.md`](ADAPTER_REFERENCE.md) |
| Implement a new source/storage/export adapter | [`ADAPTER_IMPLEMENTATION_GUIDE.md`](ADAPTER_IMPLEMENTATION_GUIDE.md) |
| Understand internal builder architecture | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Configure storage and exports | [`STORAGE_AND_EXPORT_CONFIG.md`](STORAGE_AND_EXPORT_CONFIG.md) |
| Inspect MongoDB physical collections/indexes | [`MONGODB_STORAGE_SCHEMA.md`](MONGODB_STORAGE_SCHEMA.md) |
| Understand identifier matching | [`IDENTIFIER_RECONCILIATION.md`](IDENTIFIER_RECONCILIATION.md) |
| Understand incremental source replacement/augmentation | [`INCREMENTAL_SOURCE_UPDATES.md`](INCREMENTAL_SOURCE_UPDATES.md) |
| Develop/review detailed criterion mappings | [`criterion_mapping_workflow.md`](criterion_mapping_workflow.md) |
| Add QNL institutional format evidence | [`QNL_INSTITUTION_FORMAT_EVIDENCE.md`](QNL_INSTITUTION_FORMAT_EVIDENCE.md) |
| Understand institutional policy overlays | [`INSTITUTIONAL_OVERLAYS.md`](INSTITUTIONAL_OVERLAYS.md) |
| Understand source cache/offline/fallback behavior | [`SOURCE_RETRIEVAL_AND_FALLBACKS.md`](SOURCE_RETRIEVAL_AND_FALLBACKS.md) |
| Review preservation method profiles | [`PRESERVATION_METHOD_PROFILES.md`](PRESERVATION_METHOD_PROFILES.md) |
| Review method coverage caveats | [`METHOD_COVERAGE_NOTES.md`](METHOD_COVERAGE_NOTES.md) |
| Review design decisions | [`DECISIONS.md`](DECISIONS.md) |
| Review remaining roadmap | [`NEXT_STEPS.md`](NEXT_STEPS.md) |

## Operator path

For a new operator, read:

```text
../README.md
  -> ../../docs/HOW_TO_ADD_A_SOURCE.md (when onboarding a source)
  -> INSTALLATION_SETUP_AND_RUN.md
  -> READING_THE_REGISTRY.md
  -> source/storage specialist docs as needed
```

`INSTALLATION_SETUP_AND_RUN.md` is the canonical runbook for installation, MongoDB/file setup, online/offline runs, source-specific runs, validation, audits, mapping validation, criterion-claim backfill, and deployment checks.

For onboarding a source all the way into risk analysis, use this sequence:

```text
../../docs/HOW_TO_ADD_A_SOURCE.md
  -> ADDING_AND_RUNNING_DATA_SOURCES.md
  -> ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md
  -> criterion_mapping_workflow.md
  -> ../../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md
```

For an unstructured source, insert:

```text
../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md
```

before normal adapter ingestion.

## Architecture/developer path

For code changes that cross components:

```text
../../docs/REPOSITORY_ARCHITECTURE.md
  -> ../../docs/DATA_MODEL.md
  -> ../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md
  -> ARCHITECTURE.md
  -> ADAPTER_IMPLEMENTATION_GUIDE.md
```

Important boundary:

```text
SourceAdapter
 -> SourceSnapshot / RawFormatRecord
 -> reconciliation / criterion mapping
 -> RegistryStore
```

Adapters should not issue source-specific database writes. Storage is selected through `RegistryStore`.

## Data/storage documentation boundary

| Document | Scope |
| --- | --- |
| [`../../docs/DATA_MODEL.md`](../../docs/DATA_MODEL.md) | **Canonical backend-neutral data model:** in-flight types, logical collections including `criterion_claims`, evidence→framework transformation chain. |
| [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md) | Common `query`/`upsert` contract, backend adapters, read/write ownership, risk-manager `RegistryReader`. |
| [`STORAGE_AND_EXPORT_CONFIG.md`](STORAGE_AND_EXPORT_CONFIG.md) | Builder configuration for memory/file/MongoDB and optional exports. |
| [`MONGODB_STORAGE_SCHEMA.md`](MONGODB_STORAGE_SCHEMA.md) | **MongoDB physical implementation:** fields, indexes, Mongo-safe key handling, and verification queries. |
| [`ADAPTER_IMPLEMENTATION_GUIDE.md`](ADAPTER_IMPLEMENTATION_GUIDE.md) | How to implement a new source/storage/export backend/plugin. |

Do not treat the MongoDB document layout as the data-model definition or the only supported application interface.

## Source-adapter documentation boundary

| Document | Boundary |
| --- | --- |
| [`../../docs/HOW_TO_ADD_A_SOURCE.md`](../../docs/HOW_TO_ADD_A_SOURCE.md) | One obvious end-to-end onboarding route through risk-manager verification. |
| [`../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md) | Manual/AI transcription of narrative sources into reviewed, versioned JSON. |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Concept and pipeline placement. |
| [`ADDING_AND_RUNNING_DATA_SOURCES.md`](ADDING_AND_RUNNING_DATA_SOURCES.md) | Source acquisition/configuration patterns and adapter implementation path. |
| [`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md) | Evidence-to-criterion onboarding, institution scope, new-criterion rules, AI mapping. |
| [`ADAPTER_REFERENCE.md`](ADAPTER_REFERENCE.md) | Built-in adapter configuration/behavior. |
| [`ADAPTER_IMPLEMENTATION_GUIDE.md`](ADAPTER_IMPLEMENTATION_GUIDE.md) | Developer implementation contract. |
| [`SOURCE_RETRIEVAL_AND_FALLBACKS.md`](SOURCE_RETRIEVAL_AND_FALLBACKS.md) | Acquisition/cache/offline/local-file semantics. |

## Evidence and mapping path

The builder intentionally separates source-native data from assessment frameworks:

```text
upstream structured data
 -> RawFormatRecord.native_fields / raw
 -> criterion mapping
 -> criterion_claim
 -> preservation_risk_manager framework question
```

For narrative sources:

```text
PDF / HTML
 -> manual or AI-assisted transcription draft
 -> human-reviewed JSON artifact
 -> RawFormatRecord.native_fields / raw
 -> criterion mapping
 -> criterion_claim
 -> preservation_risk_manager framework question
```

Read:

- [`../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md)
- [`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)
- [`criterion_mapping_workflow.md`](criterion_mapping_workflow.md)
- [`QNL_INSTITUTION_FORMAT_EVIDENCE.md`](QNL_INSTITUTION_FORMAT_EVIDENCE.md)
- sibling risk framework docs: [`../../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md`](../../preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md)

## AI-assisted source onboarding

There are **two distinct AI stages** for DPC/narrative sources.

### Stage 1 — transcription

```text
config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md
```

Purpose:

```text
DPC PDF/HTML -> source-native JSON draft with source locators
```

The transcription must be human-reviewed before production ingestion.

### Stage 2 — criterion mapping

```text
config/prompts/propose_mapping/dpc_bit_list.v1.md
```

Purpose:

```text
reviewed source-native fields -> proposed neutral criterion mapping JSON
```

AI produces an **unreviewed mapping draft**. It does not approve mappings. Use the actual adapter field audit/profile whenever possible so `from_field` paths are real rather than guessed.

Generic prompts:

```text
config/prompts/transcribe_unstructured_source/v1.0.md
config/prompts/propose_mapping/v1.0.md
```

Machine-readable transcription schema:

```text
config/schemas/unstructured_source_transcription.v1.schema.json
```

## Live reference documents

| Document | Status | Purpose |
| --- | --- | --- |
| `../../docs/DATA_MODEL.md` | Live | Canonical backend-neutral data model. |
| `../../docs/HOW_TO_ADD_A_SOURCE.md` | Live | End-to-end source onboarding router. |
| `../../docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md` | Live | Unstructured source transcription/review workflow. |
| `INSTALLATION_SETUP_AND_RUN.md` | Live | Primary installation/setup/operator runbook. |
| `DOCUMENTATION_MAP.md` | Live | This navigation map. |
| `ARCHITECTURE.md` | Live | Builder internals and adapter/storage boundaries. |
| `READING_THE_REGISTRY.md` | Live | Registry/output interpretation. |
| `ADDING_AND_RUNNING_DATA_SOURCES.md` | Live | Source acquisition/configuration/run patterns, including unstructured Pattern 5. |
| `ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md` | Live | Source/institution criterion onboarding and AI mapping guide. |
| `ADAPTER_REFERENCE.md` | Live | Built-in source adapter reference. |
| `ADAPTER_IMPLEMENTATION_GUIDE.md` | Live | Source/storage/export extension guide. |
| `SOURCE_RETRIEVAL_AND_FALLBACKS.md` | Live | Retrieval/cache/offline behavior. |
| `INCREMENTAL_SOURCE_UPDATES.md` | Live | Active source contribution/update model. |
| `IDENTIFIER_RECONCILIATION.md` | Live | Authority-aware reconciliation. |
| `criterion_mapping_workflow.md` | Live | Detailed mapping lifecycle and claims. |
| `QNL_INSTITUTION_FORMAT_EVIDENCE.md` | Live | QNL local evidence source. |
| `INSTITUTIONAL_OVERLAYS.md` | Live | Local policy decisions. |
| `STORAGE_AND_EXPORT_CONFIG.md` | Live | Storage/export configuration. |
| `MONGODB_STORAGE_SCHEMA.md` | Live | MongoDB physical implementation. |
| `PRESERVATION_METHOD_PROFILES.md` | Live | Preservation method-profile model. |
| `METHOD_COVERAGE_NOTES.md` | Live | Coverage interpretation/caveats. |
| `DECISIONS.md` | Live | Design rationale. |
| `NEXT_STEPS.md` | Live | Builder roadmap. |

## Historical notes

Historical plans/refactors live under `docs/history/`. They are context, not current operator instructions.

## Documentation standard for an adapter

Each adapter's documentation should state:

- what upstream source it represents;
- whether the upstream source is structured or requires a transcription artifact;
- supported acquisition modes;
- required/optional configuration;
- snapshot behavior;
- what it emits into `RawFormatRecord`;
- which identifier namespaces it verifies;
- which source-native fields are retained;
- which criterion mappings apply;
- failure/required-vs-optional behavior;
- tests that prove adapter and risk-consumer behavior.

Prefer source-level names such as `nara_digital_preservation_framework`, `pronom_registry`, `loc_fdd_xml`, and `dpc_bit_list` rather than naming an adapter after a temporary transport format.
