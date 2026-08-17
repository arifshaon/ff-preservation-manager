# Preservation Risk Manager

`preservation_risk_manager` is the **assessment, query, monitoring, and presentation module** in the File Format Preservation Manager repository.

It reads the evidence registry produced by `qnl_format_registry_builder`, resolves formats, applies explicit preservation-risk frameworks, diagnoses evidence gaps, and exposes the same underlying result to humans, automated systems, and external reporting/scheduling services.

Repository flow:

```text
qnl_format_registry_builder
  -> RegistryStore / criterion evidence
  -> RegistryReader
  -> preservation_risk_manager
       -> detailed human answer
       -> canonical machine JSON
       -> periodic/reporting integrations
```

Start with repository-wide architecture/data model if you are working across both modules:

- [`../docs/REPOSITORY_ARCHITECTURE.md`](../docs/REPOSITORY_ARCHITECTURE.md)
- [`../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)

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

AI is optional and bounded. It can route human questions, interpret unresolved evidence in `fill-gaps`, or independently review raw evidence in `review-all`. It does not silently rewrite deterministic answers, scores, risk bands, evidence, or institutional policy.

## Start here

| Need | Document |
| --- | --- |
| Install/setup/run every mode | [`docs/INSTALLATION_SETUP_AND_RUN.md`](docs/INSTALLATION_SETUP_AND_RUN.md) |
| Navigate all module documentation | [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md) |
| Understand architecture/safety boundaries | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Set up periodic source refresh, watchlists, Top 10/high-risk reports | [`docs/RISK_MONITORING_AND_REPORTING.md`](docs/RISK_MONITORING_AND_REPORTING.md) |
| Human prompts and machine JSON actions | [`docs/HUMAN_AND_SYSTEM_QUERIES.md`](docs/HUMAN_AND_SYSTEM_QUERIES.md) |
| 8 domains / 22 preservation-risk questions | [`docs/PRESERVATION_RISK_QUESTIONS.md`](docs/PRESERVATION_RISK_QUESTIONS.md) |
| AI provider configuration | [`docs/AI_PROVIDER_INTERFACE.md`](docs/AI_PROVIDER_INTERFACE.md) |
| Add/map a new evidence source | [`../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md) |

## Installation

Python 3.10 or later is required.

For normal operation against a registry-builder MongoDB backend, install both sibling packages in the same environment:

```powershell
cd ..\qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"

cd ..\preservation_risk_manager
python -m pip install -e ".[dev,ai]"
pytest -q
```

For deterministic JSON-export-only use, the risk manager can be installed without AI:

```powershell
python -m pip install -e ".[dev]"
```

Full setup: [`docs/INSTALLATION_SETUP_AND_RUN.md`](docs/INSTALLATION_SETUP_AND_RUN.md).

## Human interface

A person asks an ordinary preservation question:

```powershell
python -m preservation_risk_manager ask `
  "What are the software dependency and environment risks of PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

Normal output is detailed human-readable text with evidence coverage, question-level conclusions, supporting evidence, unresolved evidence, and calibration cautions.

The AI model routes the question to a controlled action; the registry/framework engine determines the actual assessment.

Use `--json` only when you want the canonical result and router audit metadata:

```powershell
python -m preservation_risk_manager ask `
  "Which PDF formats need more evidence?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --json
```

## Machine/system interface

Software should send a structured action directly rather than depend on prompt interpretation.

Example `request.json`:

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

Run:

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

This path makes no AI call and returns canonical JSON for APIs, dashboards, scheduled processes, tests, and other integrations.

## Periodic risk monitoring and reporting

The tool is designed to be called by an external scheduler/reporting layer as well as interactively.

A typical recurring workflow is:

```text
1. rerun registry-builder against all approved sources
2. verify source/run health
3. run query-json for selected formats/families/whole registry
4. save the canonical JSON response with a date/time
5. compare with the previous saved response
6. produce/distribute a report
```

Supported report patterns include:

```text
selected-format watchlist
all High-risk formats
Moderate + High queue
Top 10 highest-risk formats
family-specific risk report
evidence-gap / unbanded report
institution-scoped QNL report
```

The reporting layer can be Windows Task Scheduler, cron, Azure Automation, Airflow, CI/CD, a dashboard backend, or another institutional/external service. It should consume canonical JSON and may render PDF, email, dashboard, ticket, or another API response.

Important: for a true whole-registry "Top 10", the current request `limit` must cover the candidate registry before the external report takes the first 10 ranked results. See the monitoring guide for the exact request and caveat.

Full guide:

[`docs/RISK_MONITORING_AND_REPORTING.md`](docs/RISK_MONITORING_AND_REPORTING.md)

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

See [`docs/HUMAN_AND_SYSTEM_QUERIES.md`](docs/HUMAN_AND_SYSTEM_QUERIES.md) for request/response semantics and examples.

## Frameworks

### Small scoring example

```text
examples/qnl_sustainability.framework.example.json
```

A 3-question example used to exercise deterministic scoring/banding. It is not the full QNL obsolescence framework.

### Broad draft preservation question set

```text
examples/qnl_preservation_risk_questions.framework.draft.json
```

Contains 8 domains / 22 stable question IDs covering:

1. Specification Disclosure & Governance
2. Software Dependencies & Environment
3. Adoption & Community Support
4. Technical Structure & Transparency
5. Intellectual Property & Rights Management
6. Metadata & Self-Documentation
7. Essential Characteristics (Content Fidelity)
8. Local Institutional Feasibility

It is marked:

```text
calibration_status = draft_unvalidated
banding_enabled = false
```

Question-level evidence assessment is usable, but overall Low/Moderate/High banding must remain disabled until QNL validates weights and thresholds.

This means the broad draft is suitable for periodic question/evidence-gap monitoring, but it should not yet be presented as an approved Top 10 High-risk ranking.

See [`docs/PRESERVATION_RISK_QUESTIONS.md`](docs/PRESERVATION_RISK_QUESTIONS.md).

## Other execution modes

| Mode | Purpose |
| --- | --- |
| `analyze-format` | Full deterministic single-format JSON analysis. |
| `analyze-format-ai --ai-mode fill-gaps` | Deterministic analysis plus bounded interpretation of unresolved questions. |
| `analyze-format-ai --ai-mode review-all` | Independent raw-evidence AI review for calibration; never automatic override. |
| `analyze-fixture` | Score test/fixture evidence without live registry access. |
| `propose-policy-change` | Build an evidence-grounded proposal package for human approval; does not write policy. |

Commands: [`docs/INSTALLATION_SETUP_AND_RUN.md`](docs/INSTALLATION_SETUP_AND_RUN.md).

## Evidence gaps and remediation

The system treats unresolved evidence as a first-class result.

Human questions:

```text
Why can't PDF 1.7 be assessed?
Which PDF formats need more evidence and what is missing?
What should we fix first so the PDF family can be assessed?
```

The deterministic gap/remediation layer distinguishes:

```text
no matching evidence
claims that exist but do not map
claims unrelated to the active framework
mapping-rule work
new source-evidence work
framework-alignment review
```

This prevents `Unknown` from being silently treated as `Low`.

## Registry/storage access

The risk manager does not implement separate MongoDB business logic.

`RegistryReader` consumes a minimal store protocol:

```python
query(collection, filter)
```

When given a registry-builder storage config, it creates the configured registry-builder backend. Therefore MongoDB, file storage, or a future compatible backend can serve the same assessment code.

Shared contract: [`../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md).

## Global vs QNL scope

Global analysis excludes institution-scoped claims.

QNL/institution analysis includes:

```text
global/external evidence
+ institution_id=qnl evidence
```

Example machine request:

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

## Adding new source evidence

The registry builder owns source onboarding and criterion mappings. A new source normally follows:

```text
ingest -> audit -> map -> validate -> human approve -> backfill/integrated run -> verify here
```

For external sources, institution-scoped evidence, adding a genuinely new criterion, and the dedicated AI prompt for DPC Bit List mapping, see:

[`../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)

## AI provider support

The provider-neutral interface currently supports:

- Azure OpenAI;
- OpenAI-compatible endpoints.

Capabilities include normal generation, structured output, and tool-calling validation where supported.

Provider configuration must be local/secret-managed; never commit real API keys.

See [`docs/AI_PROVIDER_INTERFACE.md`](docs/AI_PROVIDER_INTERFACE.md).

## Tests

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev,ai]"
pytest -q
```

Changes to the canonical request layer should test both human routing and direct structured requests so the two interfaces cannot drift.
