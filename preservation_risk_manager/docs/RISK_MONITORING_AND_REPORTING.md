# Risk monitoring and periodic reporting

This guide describes the supported recurring preservation-risk workflow. It uses the same registry, governed synthesis policy and optional AI synthesis as interactive queries; scheduled jobs must not implement a second risk engine.

## Operating model

```text
1. Refresh selected evidence sources
   qnl_format_registry_builder
        ↓
   snapshots / source evidence / mappings / change detection
        ↓
   current MongoDB registry view

2. Assess a watchlist
   preservation_risk_manager batch-report
        ↓
   governed overall risk for every resolved format
        ↓ optional
   AI-assisted overall synthesis

3. Review/download
   HTML curator report
   CSV summary
   canonical JSON audit record
   ZIP bundle
```

Source refresh and risk reporting can run on different cadences. A report can also be run without refreshing sources first when the purpose is to reassess the current stored evidence.

## 1. Refresh only the source that needs updating

The registry builder already supports incremental source updates. The normal production operation is **not** a fresh installation or full rebuild.

Use the selected-source refresh command:

```powershell
cd qnl_format_registry_builder

python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source nara_digital_preservation_framework `
  --workdir work `
  --out output `
  --report monitoring\nara-refresh.json
```

Refresh more than one configured source by repeating `--source`:

```powershell
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source pronom `
  --source loc_fdd_xml_reviewed `
  --workdir work `
  --out output
```

The command creates a temporary selection of the existing reviewed configuration, forces `incremental_source_updates=true`, and invokes the normal pipeline. The production configuration itself is not rewritten.

A successful selected-source refresh:

1. reacquires/extracts/normalizes the selected source(s);
2. treats only successfully completed selected sources as refreshed;
3. reuses the latest successfully stored source records from all other sources;
4. reconciles the complete active evidence set;
5. reruns normal validation, criterion mapping, risk-claim materialization and change detection;
6. persists the updated current registry view and run provenance.

If a selected optional source fails, its previous successful evidence is retained by the incremental pipeline. Required-source failures still fail the run.

### Pinned versus follow-latest

Refreshing does not automatically mean "use the newest possible release." Each adapter's reviewed source configuration controls release/retrieval behavior.

For example, a pinned NARA configuration remains pinned when refreshed. A separately reviewed monitoring configuration can use NARA `release_mode=latest` to discover the newest complete release. Review newly discovered evidence/mapping effects before changing a pinned production baseline when that is the governance model.

`--offline` replays cached snapshots and cannot discover upstream material that has never been acquired.

## 2. Batch report from the current database: AI off

For a fixed watchlist:

```powershell
cd preservation_risk_manager

python -m preservation_risk_manager batch-report `
  --id fmt/18 `
  --id fmt/19 `
  --id fmt/276 `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\2026-08-22 `
  --ai-mode off
```

Or use a TXT/CSV watchlist:

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\2026-08-22 `
  --ai-mode off
```

CSV may contain `puid`, `pronom_puid`, `pronom_id`, `format_id`, `format` or `id`.

With `--ai-mode off`, the headline report is produced from governed source-risk evidence already present in the registry. Silent/missing sources contribute nothing. Question-framework completeness remains visible as supporting diagnostic information and is not substituted for the governed overall risk.

## 3. Batch report with AI-assisted synthesis

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\2026-08-22-ai `
  --ai-mode synthesize `
  --ai-config config\ai.local.json
```

For every successfully resolved format the report retains two different results:

```text
Governed config synthesis
AI-assisted synthesis
```

The AI receives the collected database evidence, configured methodology, governed baseline and framework. Provider capabilities such as web search are exposed when allowed; the model decides whether to use them. AI output does not rewrite source evidence or MongoDB.

If an AI call fails or is rate-limited, the governed database result remains available for that format.

`fill-gaps` remains available as a legacy/question-level mode for unresolved framework questions, but `synthesize` is the primary AI mode for periodic overall-risk reporting.

## 4. Curator report artifacts

Each `batch-report` run writes:

```text
risk-report.html
risk-report.csv
risk-report.json
risk-report.zip
```

The HTML report is intended for curator review. It provides:

- search/filter over the selected formats;
- governed overall risk and selected scope;
- headline and broader-context source assessments;
- AI-assisted risk, confidence and relation to the governed baseline;
- AI rationale/uncertainty and material considerations;
- external URLs returned/consulted when AI used web search;
- full machine record per format for audit/drill-down.

The CSV is the compact management/analysis view. The JSON is the canonical detailed run artifact. The ZIP contains HTML, CSV and JSON.

There is deliberately no hidden third "combined AI + database" score. The curator sees governed and AI-assisted results separately.

## 5. What should draw curator attention

The report should be reviewed for more than just a High/Critical label. Useful attention signals include:

- governed `critical`, `high` or `moderate` risk;
- AI result higher than governed risk;
- source disagreement at the selected scope;
- broader-scope warnings such as a vulnerable format family;
- material AI uncertainty;
- AI quality warnings;
- unresolved or unmapped source assessments;
- evidence/framework incompleteness;
- a format that failed to resolve.

Missing evidence is not automatically a higher risk rating. It is a separate completeness/uncertainty signal.

## 6. Institution-scoped watchlists

Add:

```powershell
--institution qnl
```

Institution-scoped evidence remains distinct from global evidence. Public web-search capability is suppressed for an AI synthesis call when institution/private assessment evidence is present.

## 7. Scheduling

The batch command is intentionally scheduler-friendly. It can be called by:

- Windows Task Scheduler;
- cron/systemd;
- CI/CD scheduling;
- Azure Automation/Functions;
- Airflow or another workflow orchestrator.

Example PowerShell pattern:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportDir = "monitoring-reports\$stamp"

# Refresh selected external evidence.
Push-Location ..\qnl_format_registry_builder
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source nara_digital_preservation_framework `
  --source pronom `
  --workdir work `
  --out output `
  --report "..\preservation_risk_manager\$reportDir\registry-refresh.json"
if ($LASTEXITCODE -ne 0) { throw "Registry refresh failed" }
Pop-Location

# Assess the controlled watchlist.
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output $reportDir `
  --ai-mode off
if ($LASTEXITCODE -ne 0) { throw "Risk report failed" }
```

A separate scheduled run may use `--ai-mode synthesize` when AI-assisted review is required.

## 8. Recommended report/run metadata to retain

Retain at least:

```text
registry refresh run_id
selected/refreshed source IDs
source changed/unchanged/failed status
source snapshot/release metadata
prior source records reused
change-detection summary
risk synthesis policy ID/version
framework ID/version/calibration status
scope/institution
watchlist/input identifiers
AI mode/provider configuration reference
generated_at
full risk-report.json
```

AI input logging, when explicitly enabled in `ai.local.json`, can also retain the exact prompt sent to the AI. Those logs may contain sensitive assessment evidence and must be protected accordingly.

## 9. Evidence-gap/framework warning

The broad working framework `examples/qnl_preservation_risk_questions.framework.draft.json` remains `draft_unvalidated` with operational banding disabled. This does **not** prevent source-level governed synthesis (NARA/DPC/etc.) or AI-assisted synthesis from being reported.

It does mean draft question-framework scores/bands must not be presented as an approved QNL risk-ranking model. The batch report therefore treats framework completeness/answers as supporting diagnostics alongside the governed overall source-risk synthesis.

## 10. Historical comparison

The batch command writes dated report artifacts but does not yet automatically persist a time-series of report-to-report changes in MongoDB.

For periodic monitoring, retain dated report folders and compare fields such as:

```text
governed_risk_level
governed_selected_scope
governed_headline_sources
governed_context_sources
ai_risk_level
ai_confidence
ai_relation_to_governed
framework_evidence_completeness_pct
```

The registry builder's own change-detection records explain upstream evidence/registry changes and should be retained with the batch risk report.
