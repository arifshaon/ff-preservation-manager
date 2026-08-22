# Web UI, REST API and Swagger

The Preservation Risk Manager includes a FastAPI web application. It provides:

- a curator-facing browser UI;
- background human-query jobs;
- background batch-report jobs;
- downloadable report artifacts;
- REST endpoints for integrations;
- automatically generated Swagger/OpenAPI documentation.

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

Swagger is generated from the running FastAPI application and is the easiest place to inspect the live request/response models.

## Current API surface

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check. |
| `GET` | `/api/config` | Safe runtime configuration summary. |
| `GET` | `/api/jobs` | List recent background jobs. |
| `GET` | `/api/jobs/{job_id}` | Inspect one job and its status/results. |
| `POST` | `/api/jobs/human` | Submit a human/natural-language assessment job. |
| `POST` | `/api/jobs/batch` | Submit a batch/watchlist assessment job. |
| `GET` | `/api/jobs/{job_id}/download/{artifact}` | Download a completed report artifact. |

Use Swagger for the exact current request schema rather than copying stale API payloads from documentation.

## Background jobs

The web layer does not implement a separate risk engine. It calls the same application logic used by the CLI.

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

Batch output can include:

```text
risk-report.html
risk-report.csv
risk-report.json
risk-report.zip
```

## Data source

The web app accepts either:

```text
--storage-config <registry builder storage/source config>
```

or:

```text
--registry-json <registry export>
```

Only one is used for a run.

For the normal persistent QNL-style setup:

```powershell
--storage-config ..\qnl_format_registry_builder\config\sources.qnl.json
```

## AI modes

When an AI config is supplied, supported human/batch modes include the current governed/AI synthesis paths exposed by the application. The web job retains the governed baseline separately from AI-assisted output.

If no AI config is supplied, deterministic/governed assessment remains available.

## Job directory

Default:

```text
web-jobs/
```

Override:

```powershell
--jobs-dir D:\risk-jobs
```

This directory stores job metadata and generated download artifacts. Manage retention/permissions according to your deployment policy.

## Limits and workers

Useful runtime options:

```text
--workers 2
--batch-max-formats 5000
--max-ai-evidence-items 20
--default-institution <id>
```

These are local-process controls, not a distributed queue. For horizontal/multi-server scaling, move job execution to a shared queue/service rather than running multiple independent in-memory job managers.

## Security

The built-in web app has no user authentication layer.

By default it binds to:

```text
127.0.0.1
```

If you expose it beyond localhost, place it behind an authenticated reverse proxy or another approved access-control layer. Do not expose an AI-enabled internal assessment service directly to an untrusted network.

The CLI prints a warning when binding to a non-loopback host.

## Swagger workflow for an integrator

1. Start the web server.
2. Open `http://127.0.0.1:8080/api/docs`.
3. Expand `/api/jobs/human` or `/api/jobs/batch`.
4. Click **Try it out**.
5. Enter the request body shown by the current OpenAPI schema.
6. Execute and retain the returned job ID.
7. Poll `GET /api/jobs/{job_id}`.
8. Download any completed artifact through the advertised download path.

## Programmatic integration principle

Applications should use canonical JSON/API responses. Do not scrape the human-rendered HTML/text output.

The web/API layer should remain thin:

```text
API -> existing request/batch core -> RegistryReader -> governed/AI analysis
```

Do not duplicate resolution, risk synthesis or source-governance logic in a frontend.

## Related documentation

- [`USE_CASES.md`](USE_CASES.md)
- [`OPERATIONS.md`](OPERATIONS.md)
- [`AI_PROVIDERS.md`](AI_PROVIDERS.md)
- [`../preservation_risk_manager/docs/WEB_UI.md`](../preservation_risk_manager/docs/WEB_UI.md) — lower-level implementation/reference details
