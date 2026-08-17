# File Format Preservation Manager

File Format Preservation Manager is a multi-module repository for building, querying, assessing, and managing file-format preservation evidence and risk.

The repository deliberately separates **registry construction** from **risk assessment**:

```text
Authoritative + institutional sources
          |
          v
qnl_format_registry_builder
  acquire -> normalize -> reconcile -> map evidence -> persist
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
```

The registry is therefore not a static spreadsheet, and the risk manager is not an AI-only chatbot. Source provenance, identifier reconciliation, evidence claims, framework questions, scoring, risk bands, and institutional scope remain explicit and auditable.

## Active modules

| Module | Purpose | Start here |
| --- | --- | --- |
| [`qnl_format_registry_builder/`](qnl_format_registry_builder/) | Builds and incrementally updates the local file-format evidence registry from NARA, PRONOM, LOC FDD, QNL/institutional evidence, and additional adapters. | [`qnl_format_registry_builder/README.md`](qnl_format_registry_builder/README.md) |
| [`preservation_risk_manager/`](preservation_risk_manager/) | Reads the registry through the same storage abstraction and performs deterministic preservation-risk assessment, evidence-gap analysis, remediation planning, human Q&A, and machine-readable queries. | [`preservation_risk_manager/README.md`](preservation_risk_manager/README.md) |

## Repository-wide documentation

| Need | Document |
| --- | --- |
| Understand how the two modules fit together | [`docs/REPOSITORY_ARCHITECTURE.md`](docs/REPOSITORY_ARCHITECTURE.md) |
| Understand the shared data model and storage/adapter contract | [`docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](docs/DATA_MODEL_AND_STORAGE_INTERFACE.md) |
| Navigate all documentation | [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md) |
| Install, configure, and run the registry builder | [`qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md`](qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md) |
| Install, configure, and run the risk manager | [`preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md`](preservation_risk_manager/docs/INSTALLATION_SETUP_AND_RUN.md) |
| Human questions and machine/system requests | [`preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md`](preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md) |
| Full preservation-risk question domains | [`preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md`](preservation_risk_manager/docs/PRESERVATION_RISK_QUESTIONS.md) |

## What each module does

### 1. Registry builder

`qnl_format_registry_builder` is the ingestion, normalization, reconciliation, provenance, and persistence layer.

Typical flow:

```text
source config
 -> source adapter
 -> content-addressed source snapshot
 -> RawFormatRecord
 -> identifier normalization
 -> conservative canonical reconciliation
 -> source/native evidence preservation
 -> criterion mapping
 -> criterion_claims
 -> RegistryStore backend
 -> change detection / exports / reports
```

Built-in source types include NARA Digital Preservation Framework, PRONOM registry/DROID data, LOC FDD XML, structured JSON, institutional policy workbooks, and QNL institutional format evidence. External source and storage plugins can be loaded by trusted `module:ClassName` paths.

The builder owns **writes and updates** to the registry. It can use memory, file/JSON document storage, MongoDB, or another backend implementing the shared storage contract.

### 2. Preservation risk manager

`preservation_risk_manager` is the analysis and access layer.

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

The risk manager reuses the registry-builder storage backend through a minimal query contract. It does not duplicate MongoDB logic.

AI is bounded to specific roles such as natural-language request routing, interpretation of unresolved evidence in `fill-gaps`, or independent raw-evidence review in `review-all`. AI does not silently rewrite canonical evidence, deterministic answers, or approved scoring rules.

## Shared storage and adapter model

The common persistence boundary is `RegistryStore`.

At minimum, a storage backend implements:

```python
upsert(collection, key, document)
query(collection, filter)
```

The registry builder uses both operations and provides named convenience methods for runs, source snapshots, source records, canonical formats, identifiers, criterion claims, institutional overlays, assessments, and change events.

The risk manager consumes the read side through `RegistryReader`, whose minimum backend requirement is `query(...)`. This means the same risk code can read a MongoDB registry, file-backed registry, in-memory test store, or compatible future adapter without changing assessment logic.

See [`docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](docs/DATA_MODEL_AND_STORAGE_INTERFACE.md) for the collection model, read/write ownership, MongoDB example, and plugin contract.

## Install both modules in one environment

Python 3.10 or later is required.

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"

cd ..\preservation_risk_manager
python -m pip install -e ".[dev,ai]"

cd ..
```

Using an existing virtual environment is also supported. Installing both packages into the same environment allows the risk manager to reuse registry-builder storage adapters such as MongoDB.

Run all package tests separately:

```powershell
cd qnl_format_registry_builder
pytest -q

cd ..\preservation_risk_manager
pytest -q
```

## Minimal end-to-end example

Build/update the registry:

```powershell
cd qnl_format_registry_builder
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out output
```

Then ask a human question against the same MongoDB-backed registry:

```powershell
cd ..\preservation_risk_manager
python -m preservation_risk_manager ask `
  "What are the software dependency and environment risks of PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

Or bypass natural-language routing and execute a machine request:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["software_dependencies_environment"]
  }
}
```

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

## Framework status

Two example frameworks currently serve different purposes:

- `qnl_sustainability.framework.example.json` — a small three-question example used to exercise deterministic scoring and risk bands.
- `qnl_preservation_risk_questions.framework.draft.json` — the broader 8-domain / 22-question preservation-risk question set. It is marked `draft_unvalidated`; overall Low/Moderate/High banding is intentionally disabled until QNL validates weights and thresholds.

Do not interpret the draft question framework as approved QNL policy.

## Current maturity

Both modules are active and tested. The registry builder is the evidence-production layer; the preservation risk manager is the evidence-consumption and assessment layer. Production deployments should use pinned/reviewed configuration, persistent storage, retained source snapshots, approved criterion mappings, controlled credentials, and reviewed/calibrated risk frameworks.
