# Operations: end to end

This is the normal operator runbook after installation.

The system has two operational loops:

```text
DATA LOOP
upstream source -> Registry Builder -> current local registry

RISK LOOP
current local registry -> Risk Manager -> curator/system report
```

Do not merge those responsibilities. The Registry Builder owns normal registry writes; the Risk Manager reads evidence and produces assessment outputs.

## A. Check the environment

Activate the repository virtual environment:

```powershell
cd C:\path\to\ff-preservation-manager
.\.venv\Scripts\Activate.ps1
```

Check MongoDB if using the persistent registry:

```powershell
mongosh "mongodb://localhost:27017" --eval "db.adminCommand({ ping: 1 })"
```

Run tests after code/config changes:

```powershell
cd qnl_format_registry_builder
pytest -q
cd ..\preservation_risk_manager
pytest -q
```

## B. Know the source configuration

The main reviewed source configuration is:

```text
qnl_format_registry_builder/config/sources.qnl.json
```

Current normal external source IDs are:

```text
nara_digital_preservation_framework
pronom_registry
loc_fdd_xml
dpc_bit_list_2025
```

The configuration also contains the disabled QNL institutional-policy source. Wikidata uses its separately governed acquisition/refresh workflow.

See [`sources/README.md`](sources/README.md).

## C. Initial registry creation versus normal update

These are different operations.

### Initial/clean-room construction

Use the Registry Builder's controlled source-by-source integration process when creating a new persistent registry from scratch. The detailed current implementation reference remains:

[`../qnl_format_registry_builder/docs/PERSISTENT_INTEGRATION.md`](../qnl_format_registry_builder/docs/PERSISTENT_INTEGRATION.md)

A clean-room build may require reviewed post-processing/backfill steps because some source evidence has historically been projected through source-specific governed transformations.

### Normal operation

Do **not** reinstall/reacquire every source on every update. Normal operation is incremental:

```text
refresh selected source(s)
+ reuse latest successful evidence from untouched sources
-> reconcile complete active evidence set
-> persist updated current view
-> retain history/provenance
```

## D. Refresh one source

Example: NARA.

```powershell
cd qnl_format_registry_builder

python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source nara_digital_preservation_framework `
  --workdir work `
  --out output `
  --report monitoring\nara-refresh.json
```

The compact report records the run ID, reviewed base-config path/hash, selected/refreshed source IDs, source results, record reuse and change detection.

## E. Refresh several sources

```powershell
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source pronom_registry `
  --source loc_fdd_xml `
  --workdir work `
  --out output `
  --report monitoring\format-authorities-refresh.json
```

Unknown source IDs are rejected before execution.

## F. Understand pinned versus latest

An online refresh follows the configured acquisition policy; it does not automatically mean "take the latest release."

Example: the current NARA production configuration is pinned to release `20260320`. Refreshing it verifies/reacquires that reviewed release unless the configuration is deliberately changed to a newer reviewed release or to an approved monitoring mode.

Recommended governance pattern:

```text
production config -> reviewed/pinned baseline
monitoring config -> may discover latest upstream state
review change      -> approve
production config -> move pin deliberately
```

## G. Offline replay

Use cached snapshots only:

```powershell
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source pronom_registry `
  --workdir work `
  --out output `
  --offline
```

Offline replay supports reproducibility/recovery but cannot discover new upstream material.

## H. Wikidata update

Wikidata is intentionally not treated as an ordinary broad source refresh. The production population is governed because an earlier transitive taxonomy crawl produced large ontology spillover.

Use the controlled Wikidata production workflow documented in:

[`../qnl_format_registry_builder/docs/WIKIDATA_PRODUCTION_INTEGRATION.md`](../qnl_format_registry_builder/docs/WIKIDATA_PRODUCTION_INTEGRATION.md)

The role of Wikidata in this project is contextual/relationship evidence. It does not supply preservation-risk ratings and does not override authority-owned identifiers.

## I. Review the registry update

After a refresh, inspect at least:

```text
run status
source status/release/snapshot hash
raw records extracted
prior source records reused
active source records
canonical format count
change detection
criterion mapping/materialization status
risk claim materialization status
validation warnings/errors
```

Do not interpret a failed optional source as "source now contains no records." Incremental logic retains its last successful contribution when appropriate and reports the failure separately.

## J. Validate/review MongoDB

MongoDB-specific collection/index details are in:

[`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md)

The logical rule used throughout the system is:

```text
current != false  -> current/active record
current == false  -> historical/superseded record
```

Do not manually edit current evidence merely to improve Risk Manager coverage.

## K. Add a new dataset/source

Use [`HOW_TO_ADD_A_SOURCE.md`](HOW_TO_ADD_A_SOURCE.md).

The required flow is:

```text
understand authority/scope
-> configure acquisition
-> write/reuse adapter
-> retain native/raw values
-> decide identifier authority
-> test extraction/reconciliation
-> add reviewed risk/criterion mappings if justified
-> run in isolation
-> review outputs
-> integrate incrementally
-> document upstream URL/update method
```

A new source should not be added directly to MongoDB by one-off scripts unless the same provenance/governance contract is preserved.

## L. Run one preservation-risk query without AI

```powershell
cd ..\preservation_risk_manager

python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-mode off
```

This resolves the format and reports the configured governed source-risk synthesis from evidence already in the registry.

## M. Run one query with AI-assisted synthesis

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --ai-mode synthesize
```

The output retains two separately auditable results:

```text
governed config synthesis
AI-assisted synthesis
```

The AI does not automatically update MongoDB.

## N. Batch/watchlist operation

Use the committed example:

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\current `
  --ai-mode off
```

With AI:

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\current-ai `
  --ai-mode synthesize `
  --ai-config config\ai.local.json
```

Artifacts:

```text
risk-report.html
risk-report.csv
risk-report.json
risk-report.zip
```

## O. What a curator should look for

Do not review only the headline level. Check:

- governed risk level and selected scope;
- exact-format versus broader family/group evidence;
- contributing source-native assessments;
- unmapped source risk terms;
- AI risk relative to governed baseline;
- AI confidence/uncertainty;
- external URLs consulted by AI when available;
- framework/evidence completeness;
- unresolved formats/errors.

Missing evidence is a completeness/uncertainty signal, not automatically a higher or lower risk rating.

## P. Web UI/API operation

Start the web server:

```powershell
python -m preservation_risk_manager.web_cli `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --host 127.0.0.1 `
  --port 8080
```

Use:

```text
http://127.0.0.1:8080/          curator UI
http://127.0.0.1:8080/api/docs Swagger
```

Web batch jobs use the same batch/reporting core as the CLI.

## Q. Scheduled operation

A typical scheduled sequence is:

```text
1. refresh selected upstream source(s)
2. fail/alert on required-source failure
3. retain refresh/change report
4. run controlled watchlist
5. produce dated HTML/CSV/JSON/ZIP risk report
6. compare/review changes
7. retain artifacts for audit
```

Windows Task Scheduler, cron/systemd, Azure Automation, CI/CD or another orchestrator can call the commands directly.

Do not build a separate scheduler-specific risk engine.

## R. AI prompt logging for audit/debugging

Set in local AI configuration:

```json
"input_log_file": "logs/ai-inputs.jsonl"
```

The file contains the actual post-budget request sent to the provider. It can contain sensitive institutional evidence; protect it and do not commit it.

## S. Backups and reproducibility

Retain:

- MongoDB backups according to deployment policy;
- source snapshots/hashes;
- registry run reports;
- reviewed configuration and mapping versions;
- dated risk-report JSON/HTML bundles;
- AI prompt logs only when explicitly needed and safely handled.

The current registry view can be rebuilt from active source contributions; historical source/run records provide audit provenance.

## T. Troubleshooting order

When a result looks wrong, check in this order:

```text
1. Did the requested identifier resolve to the intended canonical format?
2. Which current source assessments/claims exist in MongoDB?
3. Did native source terminology map under the active synthesis policy?
4. Which scope was selected for governed synthesis?
5. Is broader-scope evidence only contextual as configured?
6. Did the AI receive the expected context? (enable input logging if needed)
7. Did AI web search run, and which URLs were consulted?
8. Is the issue actually missing evidence rather than a risk conclusion?
```

Do not start by modifying registry data.

## Related guides

- [`USE_CASES.md`](USE_CASES.md)
- [`AI_PROVIDERS.md`](AI_PROVIDERS.md)
- [`API_AND_SWAGGER.md`](API_AND_SWAGGER.md)
- [`sources/README.md`](sources/README.md)
- [`../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md`](../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md)
- [`../qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md`](../qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md)
