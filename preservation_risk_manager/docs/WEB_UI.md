# Web UI

The preservation risk manager includes a lightweight local web interface for two workflows:

1. **Human risk questions** — ask natural-language questions using the same controlled routing, format identification, deterministic assessment, and optional AI interpretation used by the CLI.
2. **Batch risk reports** — paste format IDs or upload TXT/CSV, run assessments as a background job with progress, and download CSV/JSON/ZIP reports.

The web layer does **not** implement a second scoring engine. It calls the existing resolver, request executor, framework, evidence, and AI components.

## Install

From `preservation_risk_manager`:

```powershell
python -m pip install -e ".[dev,ai,web]"
```

For MongoDB-backed registry access, also install the sibling registry builder with its Mongo extra:

```powershell
cd ..\qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"
cd ..\preservation_risk_manager
```

## Run

Example using the current MongoDB registry and AI configuration:

```powershell
python -m preservation_risk_manager web `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --jobs-dir web-jobs `
  --open-browser
```

Default URL:

```text
http://127.0.0.1:8080/
```

Alternative port:

```powershell
python -m preservation_risk_manager web `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --port 8090
```

The console script is also available after installing the `web` extra:

```powershell
preservation-risk-web `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

## Human question workflow

The **Ask a risk question** tab accepts natural-language preservation questions.

Examples:

```text
What is the risk of PDF?
What are the software dependency risks of fmt/18?
What is the preservation risk of Adobe Flash version 8?
```

Controls:

- AI risk mode: `off`, `fill-gaps`, or `review-all`.
- optional bounded AI identification fallback for descriptive format references.
- global or institution scope.

The existing `human_format_assessment_limit` from the AI config applies before a broad human query fans out into many PUID assessments. If PDF matches 36 PUIDs and the configured limit is 10, only 10 are assessed; the remaining matches are reported as not assessed.

Human jobs run in the background and expose progress/status in the browser. Completed jobs can be downloaded as:

```text
human-risk-result.txt
human-risk-result.json
human-risk-result.zip
```

## Batch risk report workflow

The **Batch risk report** tab accepts:

- pasted format IDs;
- uploaded `.txt` files;
- uploaded `.csv` files.

Plain text accepts newline, comma, semicolon, or tab separation.

CSV files may use one of these columns:

```text
puid
pronom_puid
pronom_id
format_id
format
id
```

Headerless CSV uses the first column. Duplicate IDs are removed while preserving first-seen order. Safe identifier normalization is applied, so examples such as `[fmt 18]` and `"x-fmt 123"` are normalized before lookup.

Batch mode expects identifiers, not descriptive format names. AI identification is not used for batch input.

### Batch AI modes

`off` is the default and runs deterministic assessment only.

`fill-gaps` first runs deterministic assessment for every supplied/resolved ID, then uses the existing batched AI evidence interpreter for unresolved framework questions. AI responses remain keyed by PUID and question ID. Provider errors/rate limiting do not erase the deterministic report.

## Progress and background execution

The local server uses an in-process thread pool. Jobs expose:

```text
queued
running
completed
failed
```

and a 0–100 progress value. The browser polls the job API while work continues.

Job metadata and outputs are stored under:

```text
web-jobs/<job-id>/
```

including a `job.json` audit/status record.

The default worker count is 2. Override it with:

```powershell
--workers 4
```

The default maximum batch size is 5,000 distinct IDs. Override it with:

```powershell
--batch-max-formats 1000
```

## Downloads

A completed batch produces:

```text
risk-report.csv
risk-report.json
risk-report.zip
```

The ZIP contains the CSV summary and full JSON report.

The CSV intentionally separates deterministic and AI-assisted fields. It does not silently replace the deterministic result with an AI-derived value. Typical columns include:

```text
input_format_id
resolved_format_id
puid
label
version
deterministic_risk_band
deterministic_analysis_status
deterministic_score
deterministic_evidence_completeness_pct
ai_mode
ai_status
ai_risk_band
ai_analysis_status
ai_score
ai_evidence_completeness_pct
error
```

The JSON report preserves the complete per-format response and audit detail.

## API endpoints

The browser uses a small JSON API:

```text
GET  /api/health
GET  /api/config
GET  /api/jobs
GET  /api/jobs/{job_id}
POST /api/jobs/human
POST /api/jobs/batch
GET  /api/jobs/{job_id}/download/{artifact}
```

Interactive FastAPI API documentation is available at:

```text
/api/docs
```

## Security / deployment boundary

The default bind address is `127.0.0.1`, so the development UI is local to the machine.

The application currently has **no built-in authentication or authorization layer**. Do not expose it directly on a network or the public internet. If QNL deploys it as a shared internal service, place it behind an authenticated reverse proxy/SSO layer and use normal production controls for TLS, secrets, logging, process supervision, and persistent job storage.

The current in-process job queue is intended for a single application instance. If later deployed across multiple workers/servers, move job state/execution to a shared queue/service before horizontal scaling.
