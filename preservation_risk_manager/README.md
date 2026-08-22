# Preservation Risk Manager

`preservation_risk_manager` is the assessment, monitoring and presentation module of File Format Preservation Manager.

It reads the registry produced by `qnl_format_registry_builder`, resolves file formats, applies configurable governed source-risk synthesis, reports framework/evidence diagnostics, optionally asks an AI provider for a separate synthesis, and exposes results through CLI, batch reports and FastAPI.

For repository-wide documentation, start at **[`../docs/README.md`](../docs/README.md)**.

## Current analysis model

```text
format identifier
 -> resolve canonical format
 -> collect current governed source evidence
 -> config-driven overall risk synthesis
 -> framework/evidence diagnostics
 -> optional AI-assisted synthesis
 -> human / JSON / batch / web output
```

The governed source-level result, framework diagnostics and AI result are different layers. Missing evidence is not silently treated as Low risk.

## Install

Deterministic/governed CLI only:

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev]"
pytest -q
```

With AI:

```powershell
python -m pip install -e ".[dev,ai]"
```

With AI and web UI/API:

```powershell
python -m pip install -e ".[dev,ai,web]"
```

Unified installation: [`../docs/INSTALLATION.md`](../docs/INSTALLATION.md).

## Assess one format

Without AI:

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-mode off
```

With AI:

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --ai-mode synthesize
```

Curator examples and identifier explanation: [`../docs/USE_CASES.md`](../docs/USE_CASES.md).

## Batch/watchlist report

Runnable examples are committed under [`monitoring/`](monitoring/).

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\sample `
  --ai-mode off
```

AI batch:

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\sample-ai `
  --ai-mode synthesize `
  --ai-config config\ai.local.json
```

Artifacts:

```text
risk-report.html
risk-report.csv
risk-report.json
risk-report.zip
```

Full operational flow: [`../docs/OPERATIONS.md`](../docs/OPERATIONS.md).

## Governed risk configuration

The overall source-risk synthesis is controlled by the versioned policy under:

```text
src/preservation_risk_manager/config/qnl_preservation_risk_synthesis.v1.json
```

It configures:

- semantic risk vocabulary/rank;
- source-native terminology mappings;
- source roles;
- scope precedence;
- selection/aggregation operators;
- broader-scope policy;
- missing-assessment behavior;
- numeric aggregation policy.

Detailed guide: [`docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md`](docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md).

## AI providers

Native/current provider types:

```text
azure_openai
openai_compatible
```

Azure OpenAI supports the validated single-call Responses path with optional hosted web search. Generic OpenAI-compatible endpoints use one-call structured Chat Completions and do not assume vendor-hosted web search.

Setup/examples for Azure OpenAI, OpenAI API, Gemini, Claude compatibility and local servers: [`../docs/AI_PROVIDERS.md`](../docs/AI_PROVIDERS.md).

AI output does not automatically rewrite MongoDB or source-native evidence.

## Web UI/API/Swagger

```powershell
python -m preservation_risk_manager.web_cli `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --host 127.0.0.1 `
  --port 8080
```

Open:

```text
Curator UI: http://127.0.0.1:8080/
Swagger:    http://127.0.0.1:8080/api/docs
```

Guide: [`../docs/API_AND_SWAGGER.md`](../docs/API_AND_SWAGGER.md).

## Framework status

The broad working framework:

```text
examples/qnl_preservation_risk_questions.framework.draft.json
```

contains 8 domains / 22 questions and remains draft/unvalidated with operational question-framework banding disabled. This does not prevent governed source-level NARA/DPC/etc. synthesis or optional AI synthesis from being reported.

Framework questions/completeness should not be confused with the governed overall source-risk headline.

## Machine integration

Use `query-json` or the REST API rather than parsing human-rendered text.

Detailed references:

- [`docs/CLI_REFERENCE.md`](docs/CLI_REFERENCE.md)
- [`docs/HUMAN_AND_SYSTEM_QUERIES.md`](docs/HUMAN_AND_SYSTEM_QUERIES.md)
- [`../docs/API_AND_SWAGGER.md`](../docs/API_AND_SWAGGER.md)

## Advanced reference

The module `docs/` directory contains implementation/reference material rather than a second documentation portal.

Useful deep references include:

- [`docs/FRAMEWORKS.md`](docs/FRAMEWORKS.md)
- [`docs/PRESERVATION_RISK_QUESTIONS.md`](docs/PRESERVATION_RISK_QUESTIONS.md)
- [`docs/RISK_MONITORING_AND_REPORTING.md`](docs/RISK_MONITORING_AND_REPORTING.md)
- [`docs/AI_PROVIDER_INTERFACE.md`](docs/AI_PROVIDER_INTERFACE.md)
- [`docs/MODULE_REFERENCE.md`](docs/MODULE_REFERENCE.md)

## Tests

```powershell
pytest -q
```
