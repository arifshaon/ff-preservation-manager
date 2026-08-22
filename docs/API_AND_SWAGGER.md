# Web UI, REST API and Swagger

The Preservation Risk Manager includes a FastAPI web application with three curator workflows:

- **Ask Risk** — human/natural-language preservation-risk questions;
- **PUID Lookup** — discover the PRONOM PUID for a known format name/identifier;
- **Run Report** — background risk reports for supplied PUIDs/format IDs.

The same application also provides downloadable report artifacts, REST endpoints and generated Swagger/OpenAPI documentation.

## Install

From `preservation_risk_manager`:

```powershell
python -m pip install -e ".[dev,web]"
```

With AI support:

```powershell
python -m pip install -e ".[dev,ai,web]"
```

## Start the server

```powershell
python -m preservation_risk_manager.web_cli `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --host 127.0.0.1 `
  --port 8080
```

With AI:

```powershell
python -m preservation_risk_manager.web_cli `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --host 127.0.0.1 `
  --port 8080
```

## Open the interfaces

```text
Curator UI   http://127.0.0.1:8080/
Swagger UI   http://127.0.0.1:8080/api/docs
Health       http://127.0.0.1:8080/api/health
```

Swagger is generated from the live FastAPI application and is the easiest place to inspect current request/response models.

## Current API surface

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check. |
| `GET` | `/api/config` | Safe runtime configuration summary. |
| `GET` | `/api/formats/lookup?q=<term>` | Search the current registry for PUID-backed formats. |
| `GET` | `/api/jobs` | List recent background jobs. |
| `GET` | `/api/jobs/{job_id}` | Inspect one job and its status/results. |
| `POST` | `/api/jobs/human` | Submit a human/natural-language risk assessment job. |
| `POST` | `/api/jobs/batch` | Submit a PUID/watchlist report job. |
| `GET` | `/api/jobs/{job_id}/download/{artifact}` | Download a completed report artifact. |

Use Swagger for exact current schemas rather than copying old payloads from documentation.

## PUID Lookup API

Example:

```http
GET /api/formats/lookup?q=PDF
```

Possible response shape:

```json
{
  "query": "PDF",
  "match_count": 69,
  "returned_count": 10,
  "limit": 10,
  "limit_applied": true,
  "matches": [
    {
      "puid": "fmt/276",
      "puids": ["fmt/276"],
      "canonical_id": "puid-fmt-276",
      "label": "Acrobat PDF 1.7",
      "version": "1.7",
      "extensions": ["pdf"],
      "mime_types": ["application/pdf"],
      "loc_ids": [],
      "nara_ids": []
    }
  ]
}
```

The exact counts depend on the current registry. The lookup limit uses the same configured `human_format_assessment_limit` used for broad human-format assessment; without an AI config it defaults to 10.

Lookup is read-only and does not require an AI provider.

## Human assessment jobs

Example request:

```json
{
  "question": "What is the preservation risk of fmt/276?",
  "ai_mode": "synthesize",
  "enable_ai_identification": true,
  "scope": "global",
  "institution_id": null
}
```

An exact PUID resolves directly. A broad term such as `PDF` can fan out to the configured first N PUID-backed matches.

If the server has no AI configuration, a direct simple risk question can still run with:

```json
{
  "question": "What is the preservation risk of fmt/276?",
  "ai_mode": "off",
  "enable_ai_identification": false,
  "scope": "global"
}
```

General free-form natural-language routing requires an AI provider.

## Batch/report jobs

Batch jobs accept explicit PUIDs/canonical identifiers. If the required PUID is unknown, discover it with `/api/formats/lookup` first.

Batch output can include:

```text
risk-report.html
risk-report.csv
risk-report.json
risk-report.zip
```

The governed result remains separate from optional AI-assisted synthesis.

## Background jobs

```text
browser/API request
       |
       v
background JobManager
       |
       +--> human assessment core
       |
       +--> batch monitoring/report core
       |
       v
job state + downloadable artifacts
```

Job states are:

```text
queued
running
completed
failed
```

## Data source

The web app accepts exactly one of:

```text
--storage-config <registry builder storage/source config>
```

or:

```text
--registry-json <registry export>
```

For the normal persistent QNL-style setup:

```powershell
--storage-config ..\qnl_format_registry_builder\config\sources.qnl.json
```

## AI modes

When an AI config is supplied, the human/report endpoints expose the current governed plus AI-assisted modes implemented by the Risk Manager. Provider output remains advisory and separate from governed source-level risk.

If no AI config is supplied, PUID lookup and governed report generation remain available, and direct simple human risk questions can run with AI disabled.

## Job directory

Default:

```text
web-jobs/
```

Override:

```powershell
--jobs-dir D:\risk-jobs
```

This directory stores job metadata and generated artifacts. Manage retention and permissions according to deployment policy.

## Limits and workers

Useful controls include:

```text
human_format_assessment_limit     AI provider config; default 10
--workers 2
--batch-max-formats 5000
--max-ai-evidence-items 20
--default-institution <id>
```

The human assessment limit is also the default number of PUID lookup results shown by the curator application.

## Swagger workflow

1. Start the server.
2. Open `http://127.0.0.1:8080/api/docs`.
3. Try `GET /api/formats/lookup` with `q=PDF` when the PUID is unknown.
4. Submit either `/api/jobs/human` or `/api/jobs/batch`.
5. Retain the returned job ID.
6. Poll `GET /api/jobs/{job_id}`.
7. Download completed artifacts through the advertised download endpoint.

## Security

The built-in web app has no authentication layer and binds to `127.0.0.1` by default.

If exposed beyond localhost, place it behind approved authenticated access. Do not expose an AI-enabled internal assessment service directly to an untrusted network.

## Programmatic integration principle

Applications should use API/JSON responses rather than scrape the curator HTML/text.

The web/API layer remains thin:

```text
API -> existing lookup/request/batch core -> RegistryReader -> governed/AI analysis
```

Do not duplicate format resolution, risk synthesis or source-governance logic in a frontend.

## Related documentation

- [`USE_CASES.md`](USE_CASES.md)
- [`OPERATIONS.md`](OPERATIONS.md)
- [`AI_PROVIDERS.md`](AI_PROVIDERS.md)
- [`../preservation_risk_manager/docs/WEB_UI.md`](../preservation_risk_manager/docs/WEB_UI.md)
