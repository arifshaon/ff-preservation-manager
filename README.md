# File Format Preservation Manager

File Format Preservation Manager is a multi-module repository for building, querying, assessing, monitoring, and managing file-format preservation evidence and risk.

If this is your first checkout, start with:

**[`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md)**

That guide takes a new user from installation to a criterion-mapped registry and then to a deterministic preservation-risk assessment. It is the canonical cross-package quickstart.

## AI-assisted preservation workflows

AI is a **first-class but bounded capability** in this project. It is used where language understanding or structured extraction is useful, while preservation evidence, deterministic scoring, approval, and policy remain application/human controlled.

Current AI-assisted uses include:

| AI use | What it does | What it must not do |
| --- | --- | --- |
| Human-question routing | Converts a natural-language preservation question into a controlled machine request. | Calculate or invent the risk result. |
| Unstructured-source transcription | Drafts structured JSON from narrative PDF/HTML sources such as the DPC Bit List, preserving source locators. | Invent source facts/identifiers or approve its own transcription. |
| Criterion-mapping draft | Proposes how reviewed source-native fields map to the neutral criteria vocabulary. | Approve mappings or invent criterion IDs/values. |
| `fill-gaps` analysis | Interprets bounded evidence for unresolved framework questions. | Replace already-resolved deterministic answers or invent evidence. |
| `review-all` analysis | Independently reviews raw source evidence for calibration/evaluation. | Automatically change deterministic scoring or policy. |

Local/OpenAI-compatible models and Azure OpenAI are both supported. AI can therefore be hosted locally when required by institutional policy.

Start here for AI-related workflows:

- unstructured/narrative source transcription: [`docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md)
- DPC transcription prompt: [`qnl_format_registry_builder/config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md`](qnl_format_registry_builder/config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md)
- DPC criterion-mapping prompt: [`qnl_format_registry_builder/config/prompts/propose_mapping/dpc_bit_list.v1.md`](qnl_format_registry_builder/config/prompts/propose_mapping/dpc_bit_list.v1.md)
- AI-assisted risk analysis: [`preservation_risk_manager/docs/AI_ASSISTED_ANALYSIS.md`](preservation_risk_manager/docs/AI_ASSISTED_ANALYSIS.md)
- provider/local-model setup: [`preservation_risk_manager/docs/AI_PROVIDER_INTERFACE.md`](preservation_risk_manager/docs/AI_PROVIDER_INTERFACE.md)

The important governance rule is:

```text
AI may draft / route / interpret / review.
AI does not silently create evidence, approve mappings, change deterministic scoring,
or write institutional policy.
```

## Architecture at a glance

```text
Authoritative + institutional sources
          |
          +--> structured source --------------------+
          |                                           |
          +--> narrative PDF/HTML                     |
                 |                                    |
                 +--> manual/AI transcription draft  |
                        |                              |
                        +--> human-reviewed JSON ------+
                                                       |
                                                       v
qnl_format_registry_builder
  acquire -> normalize -> reconcile -> map evidence -> persist/export
          |
          v
Common registry data model / RegistryStore interface
  memory | file | MongoDB | external plugin backend
          |
          v
preservation_risk_manager
  resolve -> assemble evidence -> deterministic assessment
          |
          +--> human question -> detailed archivist-facing answer
          |
          +--> structured request -> canonical JSON for systems/APIs
          |
          +--> periodic monitoring/reporting via external scheduler/service
```

The registry is not a static spreadsheet, and the risk manager is not an AI-only chatbot. Source provenance, identifier reconciliation, criterion claims, framework questions, scoring, risk bands, evidence gaps, and institutional scope remain explicit and auditable.

## Active modules

| Module | Purpose | Start here |
| --- | --- | --- |
| [`qnl_format_registry_builder/`](qnl_format_registry_builder/) | Builds and incrementally updates the local file-format evidence registry from NARA, PRONOM, LOC FDD, QNL/institutional evidence, transcribed narrative sources, and additional adapters. | [`qnl_format_registry_builder/README.md`](qnl_format_registry_builder/README.md) |
| [`preservation_risk_manager/`](preservation_risk_manager/) | Reads the same evidence store/exports and performs deterministic risk assessment, gap diagnosis, remediation planning, human Q&A, machine queries, AI-assisted review, and monitoring/reporting integration. | [`preservation_risk_manager/README.md`](preservation_risk_manager/README.md) |

## Where to start

| Need | Document |
| --- | --- |
| First clone: build evidence and produce a real risk assessment | [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) |
| Understand the canonical backend-neutral data model | [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) |
| Understand storage/adapters/query-update contract | [`docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](docs/DATA_MODEL_AND_STORAGE_INTERFACE.md) |
| Understand how the modules fit together | [`docs/REPOSITORY_ARCHITECTURE.md`](docs/REPOSITORY_ARCHITECTURE.md) |
| Add any new source — one obvious starting page | [`docs/HOW_TO_ADD_A_SOURCE.md`](docs/HOW_TO_ADD_A_SOURCE.md) |
| Add a narrative/PDF/unstructured source | [`docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](docs/TRANSCRIBING_UNSTRUCTURED_SOURCES.md) |
| Navigate all documentation | [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md) |
| Install/configure/run the registry builder | [`qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md`](qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md) |
| Add/map a new source or institution-level evidence | [`qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md) |
| Draft a DPC Bit List transcription with AI | [`qnl_format_registry_builder/config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md`](qnl_format_registry_builder/config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md) |
| Draft a DPC Bit List criterion mapping with AI | [`qnl_format_registry_builder/config/prompts/propose_mapping/dpc_bit_list.v1.md`](qnl_format_registry_builder/config/prompts/propose_mapping/dpc_bit_list.v1.md) |
| Install/configure/run the risk manager | [`preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md`](preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md) |
| Understand the risk-analysis pipeline and band suppression | [`preservation_risk_manager/docs/RISK_ANALYSIS_WORKFLOW.md`](preservation_risk_manager/docs/RISK_ANALYSIS_WORKFLOW.md) |
| Author/review risk frameworks | [`preservation_risk_manager/docs/FRAMEWORKS.md`](preservation_risk_manager/docs/FRAMEWORKS.md) |
| Human questions and machine/system requests | [`preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md`](preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md) |
| CLI command reference | [`preservation_risk_manager/docs/CLI_REFERENCE.md`](preservation_risk_manager/docs/CLI_REFERENCE.md) |
| AI-assisted analysis and local/Azure model modes | [`preservation_risk_manager/docs/AI_ASSISTED_ANALYSIS.md`](preservation_risk_manager/docs/AI_ASSISTED_ANALYSIS.md) |
| Risk-manager module-by-module reference | [`preservation_risk_manager/docs/MODULE_REFERENCE.md`](preservation_risk_manager/docs/MODULE_REFERENCE.md) |
| Periodic source refresh, watchlists, Top 10/high-risk reports | [`preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md`](preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md) |
| Full 8-domain / 22-question preservation-risk set | [`preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md`](preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md) |

## What the registry builder produces

Typical structured-source flow:

```text
source config
 -> source adapter
 -> content-addressed snapshot
 -> RawFormatRecord
 -> identifier normalization
 -> conservative canonical reconciliation
 -> source-native evidence retention
 -> approved criterion mapping
 -> criterion_claims
 -> RegistryStore and/or exports
 -> change detection / reports
```

For narrative/unstructured sources there is an explicit pre-ingestion artifact:

```text
PDF/HTML
 -> manual or AI-assisted transcription draft
 -> human-reviewed versioned JSON
 -> normal source adapter pipeline
```

The builder owns normal registry **writes and updates**.

A key distinction for new users:

- `config/sources.example.json` is primarily a registry-construction example and does **not** enable criterion mapping.
- `config/sources.criterion-mapping.quickstart.json` explicitly enables criterion mapping and is the correct no-database quickstart when the goal is to hand evidence to the risk manager.

## What the preservation risk manager consumes

Typical flow:

```text
human prompt or structured request
 -> controlled action
 -> format resolution
 -> RegistryReader
 -> canonical format + criterion claims
 -> evidence pack
 -> framework question derivation
 -> deterministic scoring / gap diagnosis / remediation
 -> human renderer OR canonical JSON
```

With persistent storage, the risk manager reads the same `RegistryStore` backend through `RegistryReader`.

With exports, it reads `registry.json` and automatically discovers a sibling:

```text
criterion_claims.jsonl
criterion_claims.json
```

when present. This is the supported file-export handoff between the two packages.

## Install both modules

Python 3.10 or later is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"

cd ..\preservation_risk_manager
python -m pip install -e ".[dev,ai]"

cd ..
```

Using an existing virtual environment is also supported.

## Minimal end-to-end example

For the fully explained version, use [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md).

Build an export-backed registry **with criterion mapping enabled**:

```powershell
cd qnl_format_registry_builder
python -m registry_builder run `
  --config config\sources.criterion-mapping.quickstart.json `
  --workdir work `
  --out output
```

Verify claims exist:

```powershell
Test-Path output\registry.json
Test-Path output\criterion_claims.jsonl
(Get-Content output\criterion_claims.jsonl | Measure-Object -Line).Lines
```

Then analyse PDF:

```powershell
cd ..\preservation_risk_manager
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --registry-json ..\qnl_format_registry_builder\output\registry.json `
  --format PDF `
  --evidence-summary
```

The risk manager loads the sibling criterion-claim export automatically.

## Persistent/service integration

For operational deployments, prefer persistent storage such as MongoDB or the file store:

```text
registry_builder -> RegistryStore
                     |
                     v
              RegistryReader
                     |
                     v
          preservation_risk_manager
```

Machine request example:

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

## Human interface

A preservation professional asks a normal question:

```powershell
python -m preservation_risk_manager ask `
  "What are the software dependency and environment risks of PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

The AI routes intent/parameters. The deterministic registry/framework engine produces the assessment. Normal output is detailed human-readable text; `ask --json` exposes the canonical payload and router audit metadata.

## AI provider examples

Azure:

```text
preservation_risk_manager/examples/ai.azure.example.json
```

Local/OpenAI-compatible:

```text
preservation_risk_manager/examples/ai.local.example.json
```

See [`preservation_risk_manager/docs/AI_ASSISTED_ANALYSIS.md`](preservation_risk_manager/docs/AI_ASSISTED_ANALYSIS.md).

## Periodic risk monitoring and reports

The same machine interface can be orchestrated by Windows Task Scheduler, cron, Azure automation, Airflow, CI/CD, a dashboard backend, or another reporting service.

Typical periodic flow:

```text
refresh configured sources
 -> verify source/run status
 -> run selected-format / family / whole-registry risk requests
 -> save canonical JSON snapshots
 -> compare with previous snapshots
 -> render Top 10 / High-risk / watchlist / evidence-gap reports
 -> distribute as PDF, email, dashboard, ticket or API result
```

See [`preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md`](preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md).

## Framework status

Two framework examples serve different purposes:

- `qnl_sustainability.framework.example.json` — small three-question example used to exercise deterministic scoring/banding.
- `qnl_preservation_risk_questions.framework.draft.json` — broader 8-domain / 22-question working set with `calibration_status = draft_unvalidated` and `banding_enabled = false`.

Do not interpret the draft question framework as approved QNL policy or use its suppressed bands as an operational Top 10 ranking.

## Tests

```powershell
cd qnl_format_registry_builder
pytest -q

cd ..\preservation_risk_manager
pytest -q
```

Changes to cross-package handoff behavior should include an end-to-end-style regression that proves exported criterion claims are actually visible to risk analysis.
