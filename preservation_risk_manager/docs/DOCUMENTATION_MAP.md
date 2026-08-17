# Preservation Risk Manager documentation map

This is the starting point for documentation specific to `preservation_risk_manager`.

For repository-wide architecture and the shared registry/storage model, also read:

- [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)

## Start by task

| Task | Start here |
| --- | --- |
| Understand the module | [`../README.md`](../README.md) |
| Install, configure, and run every mode | [`INSTALLATION_SETUP_AND_RUN.md`](INSTALLATION_SETUP_AND_RUN.md) |
| Understand internal architecture and safety boundaries | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Ask natural-language preservation questions | [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md) |
| Integrate using canonical JSON requests | [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md) |
| Review the 8 domains / 22 questions | [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md) |
| Configure or add AI providers | [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md) |
| Understand registry collections/storage adapters | [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md) |
| Understand MongoDB physical schema | [`../../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md) |

## Recommended reading paths

### Preservation analyst

```text
../README.md
 -> PRESERVATION_RISK_QUESTIONS.md
 -> HUMAN_AND_SYSTEM_QUERIES.md
```

### Operator

```text
../README.md
 -> INSTALLATION_SETUP_AND_RUN.md
 -> HUMAN_AND_SYSTEM_QUERIES.md
 -> AI_PROVIDER_INTERFACE.md (when AI is enabled)
```

### Integration/API developer

```text
../../docs/REPOSITORY_ARCHITECTURE.md
 -> ../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md
 -> ARCHITECTURE.md
 -> HUMAN_AND_SYSTEM_QUERIES.md
```

### Framework/AI developer

```text
ARCHITECTURE.md
 -> PRESERVATION_RISK_QUESTIONS.md
 -> AI_PROVIDER_INTERFACE.md
```

## Live documents

| Document | Purpose |
| --- | --- |
| `DOCUMENTATION_MAP.md` | This navigation page. |
| `ARCHITECTURE.md` | Resolver/evidence/framework/scoring/request/AI/human-rendering architecture. |
| `INSTALLATION_SETUP_AND_RUN.md` | Installation, storage/AI setup, and commands for every current mode. |
| `HUMAN_AND_SYSTEM_QUERIES.md` | Natural-language prompts, canonical request actions, JSON examples, scopes, and output behavior. |
| `PRESERVATION_RISK_QUESTIONS.md` | 8 assessment domains, 22 question IDs, human wording, applicability, and machine filtering. |
| `AI_PROVIDER_INTERFACE.md` | Provider-neutral AI configuration and capability validation. |

## Core runtime boundaries

```text
RegistryReader
 -> FormatResolver
 -> evidence pack
 -> RiskFramework
 -> deterministic answer derivation
 -> deterministic scoring / evidence-gap analysis
 -> canonical JSON
```

Human prompt mode adds:

```text
human question
 -> AI request router (intent/parameters only)
 -> same canonical request executor
 -> same deterministic JSON
 -> human_renderer
```

Machine integration bypasses the AI router:

```text
structured JSON request
 -> same canonical request executor
 -> same deterministic JSON
```

## Current framework files

| File | Purpose |
| --- | --- |
| `examples/qnl_sustainability.framework.example.json` | Small 3-question example used to exercise deterministic scoring/banding. |
| `examples/qnl_preservation_risk_questions.framework.draft.json` | Broad 8-domain / 22-question working set for evidence collection and targeted assessment. Overall banding is disabled because calibration is not approved. |

The broader framework is a QNL working synthesis informed by preservation sustainability concepts. It is **not** a verbatim official LOC/NARA questionnaire and is **not** approved QNL policy yet.

## Interface modes at a glance

| Mode | Input | Output | AI role |
| --- | --- | --- | --- |
| `ask` | Natural-language question | Detailed human-readable answer | Route request only |
| `ask --json` | Natural-language question | Canonical JSON + router audit metadata | Route request only |
| `query-json` | Structured request | Canonical JSON | None |
| `analyze-format` | Explicit format/framework/store | Detailed deterministic JSON | None |
| `analyze-format-ai --ai-mode fill-gaps` | Explicit format/framework/store | Deterministic + bounded AI-assisted JSON | Interpret unresolved evidence only |
| `analyze-format-ai --ai-mode review-all` | Explicit format/framework/store | Deterministic + independent review comparison | Raw-source evidence review only |
| `analyze-fixture` | Fixture files | Deterministic JSON | None |
| `propose-policy-change` | Explicit evidence context + human goal | Draft evidence-grounded proposal package | No automatic approval/write |

Full commands: [`INSTALLATION_SETUP_AND_RUN.md`](INSTALLATION_SETUP_AND_RUN.md).
