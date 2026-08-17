# Preservation Risk Manager documentation map

This is the starting point for documentation specific to `preservation_risk_manager`.

For the first cross-package run, use:

**[`../../docs/GETTING_STARTED.md`](../../docs/GETTING_STARTED.md)**

For repository-wide architecture/storage, also read:

- [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)

## Start by task

| Task | Start here |
| --- | --- |
| First end-to-end run | [`../../docs/GETTING_STARTED.md`](../../docs/GETTING_STARTED.md) |
| Understand the module | [`../README.md`](../README.md) |
| Understand evidence → derivation → score → suppression | [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md) |
| Author/review frameworks and calibration | [`FRAMEWORKS.md`](FRAMEWORKS.md) |
| Install/configure/run every mode | [`INSTALLATION_SETUP_AND_RUN.md`](INSTALLATION_SETUP_AND_RUN.md) |
| Look up CLI commands/options | [`CLI_REFERENCE.md`](CLI_REFERENCE.md) |
| Ask natural-language preservation questions | [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md) |
| Integrate using canonical JSON | [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md) |
| Configure AI/local models and understand `fill-gaps`/`review-all` | [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md) |
| Review provider configuration details | [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md) |
| Review the 8 domains / 22 questions | [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md) |
| Set up periodic source refresh / Top 10 / watchlist reports | [`RISK_MONITORING_AND_REPORTING.md`](RISK_MONITORING_AND_REPORTING.md) |
| Understand each Python module | [`MODULE_REFERENCE.md`](MODULE_REFERENCE.md) |
| Add/map a new evidence source | [`../../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md) |

## Reading paths

### Preservation analyst

```text
../README.md
 -> RISK_ANALYSIS_WORKFLOW.md
 -> PRESERVATION_RISK_QUESTIONS.md
 -> HUMAN_AND_SYSTEM_QUERIES.md
```

### Operator

```text
../../docs/GETTING_STARTED.md
 -> INSTALLATION_SETUP_AND_RUN.md
 -> CLI_REFERENCE.md
 -> RISK_MONITORING_AND_REPORTING.md
```

### Integration/API developer

```text
../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md
 -> ARCHITECTURE.md
 -> HUMAN_AND_SYSTEM_QUERIES.md
 -> CLI_REFERENCE.md
```

### Framework reviewer

```text
RISK_ANALYSIS_WORKFLOW.md
 -> FRAMEWORKS.md
 -> PRESERVATION_RISK_QUESTIONS.md
 -> ../../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md
```

### AI/model developer

```text
ARCHITECTURE.md
 -> AI_ASSISTED_ANALYSIS.md
 -> AI_PROVIDER_INTERFACE.md
 -> MODULE_REFERENCE.md
```

## Live documents

| Document | Purpose |
| --- | --- |
| `DOCUMENTATION_MAP.md` | This navigation page. |
| `ARCHITECTURE.md` | High-level resolver/evidence/framework/request/AI architecture and safety boundaries. |
| `MODULE_REFERENCE.md` | Responsibility of each Python module and AI submodule. |
| `RISK_ANALYSIS_WORKFLOW.md` | Detailed deterministic flow and band-suppression explanations. |
| `FRAMEWORKS.md` | Framework JSON schema, questions, answers, weights, bands, completeness, calibration and governance. |
| `INSTALLATION_SETUP_AND_RUN.md` | Installation, storage/AI setup and runnable modes. |
| `CLI_REFERENCE.md` | Command-by-command CLI reference. |
| `HUMAN_AND_SYSTEM_QUERIES.md` | Human prompts, canonical request actions, JSON examples, scopes and result behavior. |
| `AI_ASSISTED_ANALYSIS.md` | Human routing, `fill-gaps`, `review-all`, local/Azure configuration and guardrails. |
| `AI_PROVIDER_INTERFACE.md` | Provider-neutral AI contract and provider diagnostics. |
| `PRESERVATION_RISK_QUESTIONS.md` | 8 domains / 22 stable question IDs and applicability. |
| `RISK_MONITORING_AND_REPORTING.md` | Periodic source refresh, watchlists, Top 10/high-risk/evidence-gap reports and external reporting service patterns. |

## Export handoff

Registry-builder export mode produces canonical formats and normalized claims separately.

```text
output/registry.json
output/criterion_claims.jsonl
```

When `--registry-json` points to `registry.json`, `JsonRegistryStore` automatically discovers sibling `criterion_claims.jsonl` or `criterion_claims.json`.

If the builder used a config with criterion mapping disabled, there may be no usable claim export; the risk manager can then correctly report incomplete/Not Assessed status.

For the no-database cross-package quickstart use:

```text
qnl_format_registry_builder/config/sources.criterion-mapping.quickstart.json
```

## Core runtime boundaries

```text
RegistryReader
 -> FormatResolver
 -> evidence pack
 -> RiskFramework
 -> deterministic answer derivation
 -> deterministic scoring / gap analysis
 -> canonical result
```

Human prompt mode adds:

```text
human question
 -> AI request router (intent/parameters only)
 -> same canonical request executor
 -> same deterministic result
 -> human_renderer
```

Machine integration bypasses the router:

```text
structured JSON request
 -> same canonical request executor
 -> canonical JSON
```

## Current framework files

| File | Purpose |
| --- | --- |
| `examples/qnl_sustainability.framework.example.json` | Small three-question example used to exercise deterministic scoring/banding. |
| `examples/qnl_preservation_risk_questions.framework.draft.json` | Broad 8-domain / 22-question working set for evidence collection/targeted assessment; overall banding disabled pending calibration. |

The broad framework is a QNL working synthesis, not a verbatim official LOC/NARA questionnaire and not approved QNL policy yet.

## AI examples

| File | Purpose |
| --- | --- |
| `examples/ai.azure.example.json` | Azure OpenAI configuration template. |
| `examples/ai.local.example.json` | OpenAI-compatible/local inference server template. |

## Interface modes at a glance

| Mode | Input | Output | AI role |
| --- | --- | --- | --- |
| `ask` | Natural-language question | Detailed human-readable answer | Route request only |
| `ask --json` | Natural-language question | Canonical JSON + router audit metadata | Route request only |
| `query-json` | Structured request | Canonical JSON | None |
| `analyze-format` | Explicit format/framework/store | Deterministic JSON | None |
| `analyze-format-ai --ai-mode fill-gaps` | Explicit format/framework/store | Deterministic + bounded AI-assisted JSON | Interpret unresolved evidence only |
| `analyze-format-ai --ai-mode review-all` | Explicit format/framework/store | Deterministic + independent review comparison | Raw-source-only review |
| `analyze-fixture` | Fixture files | Deterministic JSON | None |
| `propose-policy-change` | Evidence context + human goal | Draft proposal package | No automatic approval/write |

Full options: [`CLI_REFERENCE.md`](CLI_REFERENCE.md).
