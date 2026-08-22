# Web UI

The Preservation Risk Manager includes a lightweight curator-facing FastAPI interface built on the same registry, governed synthesis, batch-report and AI code used by the CLI.

The browser now presents three curator tasks:

1. **Ask Risk** — ask a preservation-risk question in normal language.
2. **PUID Lookup** — find the PRONOM PUID when the curator knows the format name but not the identifier.
3. **Run Report** — assess a supplied list of PUIDs/format IDs in a background job and download HTML/CSV/JSON/ZIP reports.

The web layer does not contain a second risk engine.

## Install

From `preservation_risk_manager`:

```powershell
python -m pip install -e ".[dev,ai,web]"
```

For MongoDB-backed registry access, install the sibling Registry Builder Mongo extra as well.

## Run

```powershell
python -m preservation_risk_manager web `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --jobs-dir web-jobs `
  --open-browser
```

Default interfaces:

```text
Curator UI   http://127.0.0.1:8080/
Swagger UI   http://127.0.0.1:8080/api/docs
```

## 1. Ask Risk

Examples:

```text
What is the preservation risk of fmt/276?
What is the preservation risk of PDF?
```

### Exact PUID

A complete PRONOM PUID such as:

```text
fmt/276
```

resolves to that exact canonical format before assessment.

### Broad name

A broad term such as:

```text
PDF
```

may match many PUID-backed formats. The existing `human_format_assessment_limit` is applied before risk work starts. Its default is `10` and it can be changed in the AI provider configuration:

```json
{
  "ai": {
    "human_format_assessment_limit": 10
  }
}
```

The web PUID Lookup uses the same configured limit so discovery and human fan-out behave consistently.

### AI modes

- `synthesize` — AI-assisted overall synthesis beside the governed baseline;
- `off` — governed/database evidence only;
- `fill-gaps` — question-level unresolved evidence interpretation;
- `review-all` — question-evidence review/calibration mode.

With no AI provider configured, a direct pattern such as:

```text
What is the preservation risk of fmt/276?
```

can still run with AI mode off and AI identification disabled. More general natural-language routing requires an AI provider.

The governed source-risk result remains the audit baseline. AI never rewrites source-native records or the governed result.

## 2. PUID Lookup

Use **PUID Lookup** when the format is known but its PRONOM identifier is not.

Example searches:

```text
PDF
TIFF
application/pdf
.docx
fmt/276
```

The endpoint is:

```http
GET /api/formats/lookup?q=PDF
```

Lookup searches the current canonical registry by name, PUID, MIME type, extension and other searchable identifiers, then returns only PUID-backed formats.

Each result includes where available:

```text
PUID
label
version
canonical ID
extensions
MIME types
LOC FDD IDs
NARA IDs
```

In the browser each result has two actions:

- **Assess** — fills the Ask Risk form with that exact PUID;
- **Add to report** — adds the PUID to the Run Report list.

This lookup is a read-only registry operation and does not require AI.

## 3. Run Report

The **Run Report** tab accepts pasted identifiers or `.txt`/`.csv` uploads. CSV may use:

```text
puid
pronom_puid
pronom_id
format_id
format
id
```

Batch input is intentionally identifier-based. If the PUID is unknown, use **PUID Lookup** first rather than passing an ambiguous descriptive name to the report job.

### Batch AI modes

`off` is the default:

```text
registry evidence
   -> configured governed synthesis
   -> report
```

`synthesize` adds the capability-driven AI result:

```text
registry evidence + governed baseline + framework/methodology
   -> configured AI client
   -> AI-assisted risk/confidence/rationale/uncertainty
```

The governed and AI results remain separate. If AI fails, governed results remain available.

## Report artifacts

A completed batch produces:

```text
risk-report.html
risk-report.csv
risk-report.json
risk-report.zip
```

The HTML report is the main curator view and supports filtering plus per-format evidence drill-down. CSV is the compact summary; JSON retains the full machine/audit record; ZIP contains all report files.

## Background execution

Human assessments and report generation use the local `JobManager` background pool. Jobs expose:

```text
queued
running
completed
failed
```

Artifacts and job state are stored under:

```text
web-jobs/<job-id>/
```

This is suitable for a single local/internal instance. A horizontally scaled deployment should use a shared queue/state service.

## API endpoints

```text
GET  /api/health
GET  /api/config
GET  /api/formats/lookup?q=<term>
GET  /api/jobs
GET  /api/jobs/{job_id}
POST /api/jobs/human
POST /api/jobs/batch
GET  /api/jobs/{job_id}/download/{artifact}
```

FastAPI documentation:

```text
/api/docs
```

`GET /api/config` reports the active framework, governed synthesis summary, configured human/PUID lookup limit and batch maximum without exposing secrets.

## Relationship to scheduled reports

The web report job and:

```powershell
python -m preservation_risk_manager batch-report ...
```

use the same reusable batch assessment/report core. The dashboard is therefore an interactive front end to the periodic-report workflow, not a separate implementation.

## Security boundary

The default bind address is `127.0.0.1`. The application has no built-in authentication layer.

Do not expose it directly to an untrusted network. A shared institutional deployment should sit behind authenticated access/SSO and normal TLS, secret, logging and job-retention controls.

AI input logging remains separately opt-in. If enabled, prompt log files may contain full evidence context and must be protected accordingly.
