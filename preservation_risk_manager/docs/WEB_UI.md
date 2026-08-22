# Web UI

The Preservation Risk Manager includes a lightweight curator-facing web interface built on the same assessment code as the CLI.

It supports two workflows:

1. **Human risk questions** — natural-language query, normal format resolution, governed source-risk synthesis and optional AI assistance.
2. **Batch risk reports** — paste/upload controlled format identifiers, run the assessment as a background job, preview governed/AI results and download HTML/CSV/JSON/ZIP artifacts.

The web layer does **not** contain a second preservation-risk engine. It calls the same request executor, governed synthesis policy, evidence layer and AI synthesis used by command-line workflows.

## Install

From `preservation_risk_manager`:

```powershell
python -m pip install -e ".[dev,ai,web]"
```

For MongoDB-backed registry access, install the sibling builder's Mongo extra as well.

## Run

```powershell
python -m preservation_risk_manager web `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --jobs-dir web-jobs `
  --open-browser
```

Default local URL:

```text
http://127.0.0.1:8080/
```

## Human question workflow

The **Ask a risk question** tab uses the same human-query path as the CLI.

AI modes exposed by the API/UI are:

- `synthesize` — AI-assisted overall synthesis alongside the governed baseline;
- `off` — governed/database evidence only;
- `fill-gaps` — additionally interpret unresolved framework questions;
- `review-all` — question-evidence review mode.

The existing `human_format_assessment_limit` applies before broad human queries fan out into many PUID assessments.

AI never changes the source-native records or the governed config baseline. Both remain visible/auditable.

## Batch risk-report workflow

The **Batch risk report** tab accepts pasted IDs or `.txt`/`.csv` uploads. CSV may use:

```text
puid
pronom_puid
pronom_id
format_id
format
id
```

Batch input is intended to be a controlled watchlist of PUIDs/canonical identifiers, not ambiguous descriptive names. AI identification is not used for the uploaded list.

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

The governed result and AI result are reported separately. If AI fails, the governed result remains.

`fill-gaps` remains for the older question-level evidence-gap workflow and is not the default overall-risk AI mode.

## Curator report

A completed batch produces:

```text
risk-report.html
risk-report.csv
risk-report.json
risk-report.zip
```

### HTML

The HTML report is self-contained and intended for curator review. It includes:

- search/filter by format, PUID, source or risk;
- governed overall risk;
- governed selected scope;
- governed headline and broader-context sources;
- AI-assisted overall risk and confidence;
- relation of AI level to the governed baseline;
- AI considerations and uncertainty;
- external URLs returned/consulted by the AI provider;
- expandable full machine record for audit.

### CSV

The CSV provides a compact management/analysis view. Key columns include:

```text
input_format_id
puid
label
governed_risk_level
governed_risk_label
governed_selected_scope
governed_headline_sources
governed_context_sources
ai_status
ai_risk_level
ai_risk_label
ai_confidence
ai_relation_to_governed
ai_web_search_used
ai_external_source_count
ai_quality_warning_count
framework_analysis_status
framework_evidence_completeness_pct
error
```

Framework score/completeness fields are supporting diagnostics. They do not replace the configured governed source-risk synthesis.

### JSON

`risk-report.json` preserves the full per-format source assessments, governed synthesis, AI audit information and framework diagnostics.

### ZIP

The ZIP contains HTML, CSV and JSON.

## Background execution

The current local server uses the existing in-process `JobManager` thread pool. Jobs expose:

```text
queued
running
completed
failed
```

and progress from 0–100. Artifacts/status are stored under:

```text
web-jobs/<job-id>/
```

This is appropriate for a single local/internal application instance. For a horizontally scaled deployment, move execution/state to a shared queue before adding multiple application servers.

## API endpoints

```text
GET  /api/health
GET  /api/config
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

`GET /api/config` also exposes the active governed synthesis-policy summary (no secrets) so an administrator can see the semantic levels and configured operators used by the application.

## Relationship to scheduled reports

The web batch job and:

```powershell
python -m preservation_risk_manager batch-report ...
```

use the same reusable batch assessment/report code. The dashboard is therefore an interactive front end to the same periodic-report workflow rather than a separate implementation.

## Security/deployment boundary

The default bind address is `127.0.0.1`. The application does not currently implement an authentication/authorization layer.

Do not expose it directly to a network/public internet. A shared QNL deployment should sit behind authenticated institutional access/SSO and normal controls for TLS, secrets, logging, job storage and process supervision.

AI input logging is separately opt-in through the AI configuration. If enabled, those log files may contain complete assessment/evidence prompts and must be protected as potentially sensitive data.
