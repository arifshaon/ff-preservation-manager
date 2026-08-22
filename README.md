# File Format Preservation Manager

A preservation-data and risk-analysis toolkit for building a local file-format registry from authoritative sources, keeping that evidence up to date, and assessing selected formats through configurable governance rules with optional AI-assisted analysis.

The repository has two main modules:

| Module | Purpose |
| --- | --- |
| [`qnl_format_registry_builder/`](qnl_format_registry_builder/) | Acquires preservation sources, retains snapshots/provenance, reconciles format identities, maps source evidence, and maintains the local registry. |
| [`preservation_risk_manager/`](preservation_risk_manager/) | Resolves formats, synthesizes governed source-level risk, assesses framework evidence, optionally asks an AI model for a separate synthesis, and produces interactive/batch reports. |

MongoDB is the normal persistent registry store. JSON/JSONL/CSV/SQLite/Markdown exports are also available for review and portable workflows.

## How the system fits together

```text
PRONOM   LOC FDD   NARA   DPC   Wikidata   QNL/local sources
   \        |        |      |       |             /
    +-------+--------+------+-------+------------+
                         |
                         v
              qnl_format_registry_builder
       acquire -> snapshot -> extract -> normalize
       -> reconcile identity -> map evidence -> persist
                         |
                         v
                  local registry
             MongoDB / reviewed exports
                         |
                         v
              preservation_risk_manager
       resolve format -> governed synthesis -> diagnostics
                  |                     |
                  |                     +--> optional AI synthesis
                  |
                  +--> one-format query / batch report / web API
```

The registry evidence, governed risk result, and AI-assisted result remain separately auditable. Missing evidence is not silently treated as Low risk, and AI output does not automatically rewrite source records or MongoDB.

## Documentation table of contents

Start with the documentation portal: **[`docs/README.md`](docs/README.md)**.

| I want to... | Go to |
| --- | --- |
| Understand the overall architecture and logic | [`docs/REPOSITORY_ARCHITECTURE.md`](docs/REPOSITORY_ARCHITECTURE.md) |
| Understand the data model and collections | [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) |
| Install the registry builder, Risk Manager, web UI/API and Swagger | [`docs/INSTALLATION.md`](docs/INSTALLATION.md) |
| Operate the system end to end, including refreshing sources | [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
| Add a new dataset/source | [`docs/HOW_TO_ADD_A_SOURCE.md`](docs/HOW_TO_ADD_A_SOURCE.md) |
| See every currently integrated data source and its upstream URL | [`docs/sources/README.md`](docs/sources/README.md) |
| Test one format or create a batch report | [`docs/USE_CASES.md`](docs/USE_CASES.md) |
| Configure Azure OpenAI, OpenAI, Gemini, Claude or another compatible model | [`docs/AI_PROVIDERS.md`](docs/AI_PROVIDERS.md) |
| Run the web interface or use Swagger/OpenAPI | [`docs/API_AND_SWAGGER.md`](docs/API_AND_SWAGGER.md) |
| Understand configurable risk terminology and synthesis governance | [`preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md`](preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md) |
| Inspect MongoDB-specific storage details | [`qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md) |

## Quick installation

Python 3.10+ is required. MongoDB is required only for the persistent MongoDB workflow.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"

cd ..\preservation_risk_manager
python -m pip install -e ".[dev,ai,web]"
```

Full installation choices, including a data/export-only setup, are in [`docs/INSTALLATION.md`](docs/INSTALLATION.md).

## Quick use: assess one format

From `preservation_risk_manager`:

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-mode off
```

`fmt/276` is a PRONOM Unique Identifier (PUID) for PDF 1.7. See [`docs/USE_CASES.md`](docs/USE_CASES.md) for identifier explanations and AI-enabled examples.

## Quick use: batch report

A runnable example watchlist is committed at [`preservation_risk_manager/monitoring/watchlist.csv`](preservation_risk_manager/monitoring/watchlist.csv).

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\sample `
  --ai-mode off
```

The report directory contains HTML, CSV, JSON and ZIP artifacts.

## Quick use: web UI and Swagger

```powershell
python -m preservation_risk_manager.web_cli `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --host 127.0.0.1 `
  --port 8080
```

Open:

- Curator UI: `http://127.0.0.1:8080/`
- Swagger UI: `http://127.0.0.1:8080/api/docs`

## Operating principle

Normal operation is incremental:

```text
upstream source changes
  -> refresh only selected source(s)
  -> reuse current evidence from other sources
  -> rebuild/reconcile the active current view
  -> review change report
  -> run one-format or watchlist risk assessment
  -> review/download curator report
```

A source refresh is not automatically a clean reinstall, and a pinned source does not silently move to a newer release. See [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## Validation checkpoint

The validated `preservation-risk-v0.1.0` checkpoint covers configurable governed synthesis, optional AI-assisted synthesis, batch monitoring/reporting, web/API operation and incremental source refresh.

Run both test suites after changes:

```powershell
cd qnl_format_registry_builder
pytest -q

cd ..\preservation_risk_manager
pytest -q
```

## License

See [`LICENSE`](LICENSE).
