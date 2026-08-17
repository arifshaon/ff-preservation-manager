# Risk monitoring and periodic reporting

This guide describes how to operate the repository as a **continuous preservation-risk monitoring service**, not only as an interactive command-line tool.

The monitoring model has three separate jobs:

```text
1. Refresh evidence
   qnl_format_registry_builder
        -> reacquire/update configured sources
        -> normalize/reconcile/map
        -> persist current registry evidence

2. Reassess risk
   preservation_risk_manager
        -> query selected formats/families/all formats
        -> deterministic assessment
        -> canonical JSON

3. Produce/distribute reports
   operator script / scheduler / external service
        -> retain JSON snapshots
        -> compare with previous reports
        -> create email/dashboard/PDF/ticket/report as required
```

The repository does **not** require the same process to perform all three jobs. An external reporting or orchestration service can call the registry builder and/or the risk-manager machine interface and use the returned JSON to generate its own reports.

## 1. Periodically refresh all evidence sources

For an integrated MongoDB-backed refresh with criterion mapping enabled:

```powershell
cd qnl_format_registry_builder
python -m registry_builder run `
  --config config\sources.criterion-mapping.mongodb.example.json `
  --workdir work `
  --out output
```

The example integrated configuration currently includes QNL seed evidence, NARA, PRONOM and LOC FDD. For production, copy the configuration and enable the sources that form the institution's approved evidence baseline.

A scheduled refresh should normally run **online** so upstream changes can be discovered. `--offline` is for replay/recovery using cached snapshots; it is not a substitute for a current-source monitoring run.

### What a refresh preserves

The builder keeps source snapshots and source records for provenance/history while recomputing the active canonical view from current source contributions. Change detection records differences between registry states.

A monitoring service should retain or archive at least:

- the builder run report;
- source acquisition status for each source;
- source snapshot hashes/metadata;
- mapping version(s);
- canonical/criterion-claim counts;
- any reported assessment/change events;
- the date/time and configuration version used for the run.

Do not treat a failed optional source as equivalent to "no change". Report source failures separately from preservation-risk results.

## 2. Choose a monitoring cadence

Cadence is an operational policy, not hard-coded application behavior.

Example patterns:

| Monitoring object | Example cadence | Reason |
| --- | --- | --- |
| Authoritative external sources | monthly or quarterly | detect new formats, changed guidance, signatures and evidence |
| Institution-authored evidence | after review/change, plus periodic verification | local capability and policy can change independently of external sources |
| High-risk/watchlist formats | monthly | maintain a current intervention queue |
| Broad whole-registry ranking | monthly/quarterly | identify newly elevated risks and evidence gaps |
| Critical collection-specific formats | after each source refresh or more frequently | higher operational consequence |

Use a cadence appropriate to the volatility and importance of the evidence source. The important point is that **source refresh and risk reporting are repeatable commands** and can therefore be scheduled externally.

## 3. Report selected file formats

For a fixed watchlist, run one structured request per format and retain each canonical JSON response.

Example request for PDF:

```json
{
  "action": "assess_format",
  "format": "fmt-pdf",
  "scope": "global"
}
```

Execute:

```powershell
cd preservation_risk_manager
python -m preservation_risk_manager query-json `
  --request requests\pdf.json `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

An external service can loop over a watchlist such as:

```text
fmt-pdf
fmt-tiff
fmt-jpeg
fmt-wav
fmt-mp4
...
```

and write each response to a dated report folder.

### Institution-scoped watchlist

Use:

```json
{
  "action": "assess_format",
  "format": "fmt-pdf",
  "scope": "institution",
  "institution_id": "qnl"
}
```

Institution scope includes global evidence plus matching institution-scoped claims. It must not promote QNL-specific observations into global facts.

## 4. Report all High-risk formats

Once a framework has approved/calibrated risk banding, a machine request can return High-risk formats:

```json
{
  "action": "list_at_risk_formats",
  "filters": {
    "risk_bands": ["High"]
  },
  "scope": "global",
  "limit": 5000
}
```

Results are ranked by:

```text
High -> Moderate -> Low
then descending score
then format label
```

For `risk_bands: ["High"]`, the result therefore provides a deterministic ranked High-risk queue.

## 5. Produce a Top 10 highest-risk report

**Do not use `limit: 10` when the intention is "find the ten highest-risk formats in the whole registry."**

The current request layer applies `limit` to the candidate format set before all candidates are scored. A whole-registry Top 10 workflow should therefore:

1. request a candidate limit large enough to cover the registry (current maximum: `5000`);
2. request the required risk bands;
3. use the already ranked `results` array;
4. take the first 10 results in the external reporting layer.

Example request:

```json
{
  "action": "list_at_risk_formats",
  "filters": {
    "risk_bands": ["High", "Moderate"]
  },
  "scope": "global",
  "limit": 5000
}
```

External reporting logic:

```text
response.results[0:10]
```

If the operational registry grows beyond the request-layer maximum, perform the whole-registry assessment in a service that pages/partitions the registry and ranks the combined deterministic results. Do not silently report the first ten candidates as the highest ten risks.

## 6. Produce a family-specific risk report

Example: PDF-family formats that are Moderate or High risk:

```json
{
  "action": "list_at_risk_formats",
  "filters": {
    "family": "PDF",
    "risk_bands": ["Moderate", "High"]
  },
  "scope": "global",
  "limit": 500
}
```

The family search is deliberately conservative. Explicit family metadata is preferred; otherwise names/aliases are used. Extension or MIME overlap alone does not prove family membership.

## 7. Produce an evidence-gap monitoring report

Risk monitoring must also surface formats that **cannot yet be reliably assessed**.

A report that only lists High/Moderate results can create false reassurance if many formats are unbanded because evidence is missing.

Whole family example:

```json
{
  "action": "list_evidence_gaps",
  "filters": {
    "family": "PDF"
  },
  "scope": "global",
  "limit": 500
}
```

For actionable remediation planning:

```json
{
  "action": "plan_evidence_remediation",
  "filters": {
    "family": "PDF"
  },
  "scope": "global",
  "limit": 500
}
```

A periodic management report should normally show both:

```text
A. assessed/ranked risk
B. unbanded / insufficient-evidence population
```

## 8. Framework/calibration warning

The broad working framework:

```text
examples/qnl_preservation_risk_questions.framework.draft.json
```

currently has:

```text
calibration_status = draft_unvalidated
banding_enabled = false
```

It is suitable for question-level evidence assessment, evidence-gap monitoring and framework development, but **not yet for an operational Top 10 High-risk ranking based on Low/Moderate/High bands**.

The small:

```text
examples/qnl_sustainability.framework.example.json
```

has working bands for testing the assessment architecture, but it is only a three-question example and must not be presented as the final QNL preservation-risk model.

A production risk-ranking report should identify the framework ID/version and use an approved/calibrated framework.

## 9. Recommended report metadata

Every generated report or saved JSON snapshot should record enough context to reproduce it:

```text
report generated_at
registry refresh/run reference
source refresh status
framework_id
framework_version
calibration_status
banding_enabled
scope
institution_id when applicable
request/action/filters
candidate_count
result_count
evidence hashes from returned assessments
```

When a report is transformed into PDF, email, dashboard cards or tickets, retain the canonical JSON as the machine audit record.

## 10. External scheduler/reporting-service pattern

The application is intentionally suitable for orchestration by another service.

Examples include:

- Windows Task Scheduler;
- cron/systemd timers;
- CI/CD schedulers;
- Azure Automation / Functions;
- Airflow or another workflow orchestrator;
- a repository dashboard/backend service;
- an institutional reporting service.

Recommended sequence:

```text
SCHEDULE TRIGGER
   |
   +--> run registry refresh
   |      |
   |      +--> verify source/run status
   |
   +--> run one or more query-json requests
   |      |
   |      +--> save canonical JSON
   |
   +--> compare current vs prior saved report
   |
   +--> render/distribute report
          PDF | dashboard | email | ticket | API response
```

The external service should call `query-json` or, in a future HTTP wrapper, the same canonical request executor. It should **not** reproduce preservation scoring logic itself.

## 11. Example PowerShell monitoring wrapper

This example shows the orchestration shape. It is intentionally simple and can be replaced by an external scheduler/service.

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportDir = "monitoring-reports\$stamp"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

# 1. Refresh registry/evidence.
Push-Location ..\qnl_format_registry_builder
python -m registry_builder run `
  --config config\sources.criterion-mapping.mongodb.example.json `
  --workdir work `
  --out output | Out-File -Encoding utf8 "..\preservation_risk_manager\$reportDir\registry-run.json"
if ($LASTEXITCODE -ne 0) { throw "Registry refresh failed" }
Pop-Location

# 2. Run a whole-registry at-risk request prepared in requests\at-risk.json.
python -m preservation_risk_manager query-json `
  --request requests\at-risk.json `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  | Out-File -Encoding utf8 "$reportDir\at-risk.json"
if ($LASTEXITCODE -ne 0) { throw "Risk query failed" }

# 3. An external/reporting step can now consume the saved JSON.
```

In production, separate diagnostic/progress output from canonical JSON as appropriate for the calling service, and use a reviewed production configuration/framework rather than example files.

## 12. Comparing reports over time

The current canonical query layer returns current assessment results; it does not yet provide a complete built-in historical risk-report store.

For periodic reporting today, the orchestration/reporting service should persist dated canonical JSON responses and compare fields such as:

```text
risk_band
score
analysis_status
evidence_completeness
missing_count
main_risk_factors
evidence_hash
```

A changed `evidence_hash` is a useful signal that the evidence package has changed, but the reporting service should still compare the actual assessment fields to explain what changed.

The registry builder's own source/change history remains useful for tracing *why* upstream evidence changed.

## 13. Minimum operational monitoring set

A practical recurring preservation monitoring package is:

```text
1. Source health report
   - which sources refreshed / failed / were unchanged

2. Top-risk report
   - High first, then Moderate
   - Top 10 or another management-sized list

3. Watchlist report
   - selected critical formats regardless of current band

4. Evidence-gap report
   - unbanded / insufficient-evidence formats

5. Change report
   - current report compared with previous saved snapshot
```

This keeps "known high risk" separate from "we do not yet have enough evidence to know."