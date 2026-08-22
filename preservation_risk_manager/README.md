# Preservation Risk Manager

`preservation_risk_manager` is the **assessment, query, monitoring, and presentation module** in the File Format Preservation Manager repository.

It reads the evidence registry produced by `qnl_format_registry_builder`, resolves formats, applies explicit preservation-risk frameworks, diagnoses evidence gaps, and exposes the same underlying result to humans, automated systems, and reporting/scheduling services.

If you are new to the repository, start with the cross-package quickstart:

**[`../docs/GETTING_STARTED.md`](../docs/GETTING_STARTED.md)**

## Repository flow

```text
qnl_format_registry_builder
  -> canonical formats + criterion claims
  -> RegistryStore OR export files
  -> RegistryReader
  -> preservation_risk_manager
       -> deterministic assessment
       -> detailed human answer
       -> canonical machine JSON
       -> periodic/reporting integrations
```

## What this module does

```text
format reference
 -> resolve canonical format
 -> gather global/institution-scoped criterion claims
 -> build evidence pack
 -> apply RiskFramework questions
 -> derive controlled answers deterministically
 -> score / suppress band when evidence is insufficient
 -> diagnose gaps / remediation when requested
 -> canonical result
 -> human renderer OR machine JSON
```

AI is optional. The registry evidence remains the primary evidence base. AI can route human questions, interpret unresolved bounded evidence in `fill-gaps`, independently review supplied raw evidence in `review-all` for calibration, and—when explicitly enabled in the Azure provider configuration—verify and supplement the collected preservation evidence through cited public-web research before producing an AI-assisted synthesis. AI web research does not replace the registry with an independent opinion, silently rewrite source-native assessments, change configured source mappings, or persist researched findings back to MongoDB.

## Start here

| Need | Document |
| --- | --- |
| First end-to-end run across both packages | [`../docs/GETTING_STARTED.md`](../docs/GETTING_STARTED.md) |
| Install/setup/run every mode | [`docs/INSTALLATION_SETUP_AND_RUN.md`](docs/INSTALLATION_SETUP_AND_RUN.md) |
| Navigate all module documentation | [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md) |
| Understand architecture/safety boundaries | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Understand evidence → derivation → scoring → suppression | [`docs/RISK_ANALYSIS_WORKFLOW.md`](docs/RISK_ANALYSIS_WORKFLOW.md) |
| Author/review frameworks and calibration | [`docs/FRAMEWORKS.md`](docs/FRAMEWORKS.md) |
| CLI command reference | [`docs/CLI_REFERENCE.md`](docs/CLI_REFERENCE.md) |
| Human prompts and machine JSON actions | [`docs/HUMAN_AND_SYSTEM_QUERIES.md`](docs/HUMAN_AND_SYSTEM_QUERIES.md) |
| AI `fill-gaps`, `review-all`, Azure and local models | [`docs/AI_ASSISTED_ANALYSIS.md`](docs/AI_ASSISTED_ANALYSIS.md) |
| Registry-first cited AI web research and synthesis | [`docs/AI_RESEARCH_ASSISTED_SYNTHESIS.md`](docs/AI_RESEARCH_ASSISTED_SYNTHESIS.md) |
| Module-by-module code responsibilities | [`docs/MODULE_REFERENCE.md`](docs/MODULE_REFERENCE.md) |
| Set up periodic source refresh/watchlists/Top 10 reports | [`docs/RISK_MONITORING_AND_REPORTING.md`](docs/RISK_MONITORING_AND_REPORTING.md) |
| Review the 8 domains / 22 preservation-risk questions | [`docs/PRESERVATION_RISK_QUESTIONS.md`](docs/PRESERVATION_RISK_QUESTIONS.md) |
| AI provider interface/config details | [`docs/AI_PROVIDER_INTERFACE.md`](docs/AI_PROVIDER_INTERFACE.md) |
| Shared registry/storage contract | [`../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md) |

## Installation

Python 3.10 or later is required.

For normal operation against a registry-builder backend, install both sibling packages in the same environment:

```powershell
cd ..\qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"

cd ..\preservation_risk_manager
python -m pip install -e ".[dev,ai]"
pytest -q
```

For deterministic export-only use, the risk manager can be installed without AI:

```powershell
python -m pip install -e ".[dev]"
```

## Critical data handoff: criterion claims

A format registry alone is not enough for framework-driven risk analysis. The risk manager needs normalized `criterion_claims` as well as canonical formats.

### Persistent store mode

Use the same registry-builder backend:

```powershell
--storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

The reader queries `canonical_formats` and `criterion_claims` through the shared storage interface.

### Export mode

Use:

```powershell
--registry-json ..\qnl_format_registry_builder\output\registry.json
```

Registry-builder exports criterion claims separately. The risk manager now automatically discovers a sibling:

```text
criterion_claims.jsonl
criterion_claims.json
```

and loads it into the same read contract.

If the builder run did not enable criterion mapping, the claim export may be absent/empty and assessment can correctly return `Not Assessed` or low completeness.

For a no-database end-to-end demonstration, use:

```text
qnl_format_registry_builder/config/sources.criterion-mapping.quickstart.json
```

not the generic `sources.example.json`.

## Deterministic example

```powershell
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --registry-json ..\qnl_format_registry_builder\output\registry.json `
  --format PDF `
  --evidence-summary
```

Inspect:

```text
criterion_claims_used
analysis.analysis_status
analysis.evidence_completeness
analysis.analysed_band
analysis.band_suppressed_reason
```

A `null` band is not automatically an error and must not be interpreted as Low risk. See [`docs/RISK_ANALYSIS_WORKFLOW.md`](docs/RISK_ANALYSIS_WORKFLOW.md).

## Human interface

A person asks an ordinary preservation question:

```powershell
python -m preservation_risk_manager ask `
  "What are the software dependency and environment risks of PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

Normal output is detailed human-readable text with source assessments, synthesis reasoning, question-level evidence where requested, unresolved evidence, and calibration cautions.

The AI model routes the question to a controlled action; the registry/framework engine remains the evidence authority. With `--ai-mode synthesize`, the normal config-driven synthesis is used by default. If `ai.web_research.enabled=true` in the Azure AI config, the same action additionally verifies and supplements the collected evidence through cited public-web research before returning the AI-assisted synthesized result. See [`docs/AI_RESEARCH_ASSISTED_SYNTHESIS.md`](docs/AI_RESEARCH_ASSISTED_SYNTHESIS.md).

Use `--json` only when you want the canonical result and router audit metadata.

## Machine/system interface

Software should send a structured action directly rather than depend on prompt interpretation.

Example:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["software_dependencies_environment"]
  },
  "scope": "global"
}
```

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

This path makes no AI call unless an AI mode is explicitly supplied. It returns canonical JSON for APIs, dashboards, scheduled processes, tests, and other integrations.

## Controlled request actions

Current actions:

```text
assess_format
assess_format_questions
search_formats
assess_format_family
list_at_risk_formats
list_assessment_questions
list_evidence_gaps
plan_evidence_remediation
```

See [`docs/HUMAN_AND_SYSTEM_QUERIES.md`](docs/HUMAN_AND_SYSTEM_QUERIES.md).

## Frameworks

### Small scoring example

```text
examples/qnl_sustainability.framework.example.json
```

Three-question example used to exercise deterministic scoring/banding. It is not the full QNL obsolescence framework.

### Broad draft question set

```text
examples/qnl_preservation_risk_questions.framework.draft.json
```

Contains 8 domains / 22 stable question IDs and is currently:

```text
calibration_status = draft_unvalidated
banding_enabled = false
```

Question-level evidence assessment is usable, but overall Low/Moderate/High banding is intentionally withheld until QNL validates the framework.

See [`docs/FRAMEWORKS.md`](docs/FRAMEWORKS.md) and [`docs/PRESERVATION_RISK_QUESTIONS.md`](docs/PRESERVATION_RISK_QUESTIONS.md).

## Other execution modes

| Mode | Purpose |
| --- | --- |
| `analyze-format` | Full deterministic single-format JSON analysis. |
| `analyze-format-ai --ai-mode fill-gaps` | Deterministic analysis plus bounded interpretation of unresolved questions. |
| `analyze-format-ai --ai-mode review-all` | Independent raw-evidence AI review for calibration; never automatic override. |
| `analyze-fixture` | Score test/fixture evidence without live registry access. |
| `propose-policy-change` | Build an evidence-grounded proposal package for human approval; does not write policy. |

See [`docs/CLI_REFERENCE.md`](docs/CLI_REFERENCE.md) and [`docs/AI_ASSISTED_ANALYSIS.md`](docs/AI_ASSISTED_ANALYSIS.md).

## AI examples

Azure:

```text
examples/ai.azure.example.json
```

The Azure example includes an explicit `web_research` block. It is disabled by default. Set `enabled` to `true` only when cited public-web verification is intended and permitted for the deployment/subscription.

Local/OpenAI-compatible:

```text
examples/ai.local.example.json
```

Copy an example to `config\ai.local.json` and edit it locally. Do not commit real API keys.

## Periodic risk monitoring and reporting

A typical recurring workflow is:

```text
1. refresh approved upstream/institution sources
2. verify source/run health
3. run query-json for selected formats/families/whole registry
4. save canonical JSON with date/time/framework version
5. compare with previous report snapshot
6. render/distribute a report
```

Supported patterns include watchlists, all-High-risk queues, Moderate+High queues, Top 10, family reports, evidence-gap reports, and institution-scoped reports.

Full guide: [`docs/RISK_MONITORING_AND_REPORTING.md`](docs/RISK_MONITORING_AND_REPORTING.md).

## Evidence gaps and remediation

Human questions include:

```text
Why can't PDF 1.7 be assessed?
Which PDF formats need more evidence and what is missing?
What should we fix first so the PDF family can be assessed?
```

The deterministic gap/remediation layer distinguishes missing evidence, matched-but-unmapped claims, unrelated claims, mapping work, source-evidence work, and framework-alignment review.

This prevents `Unknown` from being silently treated as `Low`.

## Global vs institution scope

Global analysis excludes institution-scoped claims.

Institution analysis includes:

```text
global/external evidence
+ evidence where institution_id matches
```

Example:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["local_institutional_feasibility"]
  },
  "scope": "institution",
  "institution_id": "qnl"
}
```

Local capability/storage/readiness observations should not be generalized as universal properties of PDF.

## Tests

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev,ai]"
pytest -q
```

Cross-package handoff changes should include a regression proving that exported criterion claims are visible to risk analysis.
