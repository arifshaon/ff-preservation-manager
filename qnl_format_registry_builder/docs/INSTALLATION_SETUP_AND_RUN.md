# Registry Builder: installation, setup, and run guide

This is the primary operator runbook for `qnl_format_registry_builder`.

For the first cross-package run from clone to preservation-risk assessment, use **[`../../docs/GETTING_STARTED.md`](../../docs/GETTING_STARTED.md)**. That path deliberately enables criterion mapping so the risk manager receives usable claims.

## 1. What this module does

```text
source acquisition
 -> snapshots
 -> source records
 -> normalization
 -> identifier reconciliation
 -> canonical formats
 -> criterion mapping
 -> criterion claims
 -> RegistryStore / exports
 -> change detection / reports
```

The builder is the normal **write/update owner** for the registry. The sibling `preservation_risk_manager` reads the resulting data through the same storage abstraction or paired exports.

Shared architecture/data model:

- [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)

## 2. Requirements

- Python 3.10 or later.
- Network access for online acquisition unless using cached/offline/local-file modes.
- MongoDB only when the selected backend is `mongodb`.
- Space for snapshots under `work/` and optional exports under `output/`.

## 3. Install

```powershell
cd qnl_format_registry_builder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mongo]"
pytest -q
```

Without MongoDB:

```powershell
python -m pip install -e ".[dev]"
```

If both repository modules share one environment, install the risk manager into the same environment so it can reuse builder storage adapters.

## 4. Configuration model

A builder run is controlled by JSON configuration:

```text
sources
  upstream/institutional adapters

identifier_kinds / reconciliation
  authority-aware canonical matching

criterion_mapping
  source-native observations -> neutral criterion_claims

storage
  memory | file | MongoDB | plugin

exports
  optional JSON/JSONL/CSV/SQLite/Markdown review output

method profiles / institution config
  optional preservation-method/local context
```

### Two important example configurations

#### Registry-construction example

```text
config/sources.example.json
```

This is the general multi-source registry example. **It does not enable `criterion_mapping`.** It can build thousands of canonical format records while producing no normalized criterion claims for the risk framework.

Use it when the goal is learning/testing registry construction itself.

#### Cross-package criterion-mapping quickstart

```text
config/sources.criterion-mapping.quickstart.json
```

This uses memory storage, enables approved criterion mappings and exports the two files required for the file-based risk-manager handoff:

```text
output\registry.json
output\criterion_claims.jsonl
```

Use it when the goal is a no-database end-to-end risk-assessment demonstration.

Operational MongoDB example with integrated mappings:

```text
config/sources.criterion-mapping.mongodb.example.json
```

Other useful examples:

```text
config/sources.nara.mongodb.example.json
config/sources.pronom.mongodb.example.json
config/sources.loc.mongodb.example.json
config/sources.wikidata.mongodb.example.json
config/qnl-institution-format-evidence.mongodb.example.json
config/storage.mongodb.example.json
config/storage.file.example.json
```

Do not place production secrets in committed examples.

## 5. MongoDB setup

Example storage block:

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry",
    "collection_prefix": "",
    "server_selection_timeout_ms": 5000,
    "ping": true
  },
  "exports": {
    "enabled": false
  }
}
```

MongoDB is selected through `RegistryStore`; preservation business logic must not depend directly on `pymongo`.

See:

- [`STORAGE_AND_EXPORT_CONFIG.md`](STORAGE_AND_EXPORT_CONFIG.md)
- [`MONGODB_STORAGE_SCHEMA.md`](MONGODB_STORAGE_SCHEMA.md)
- [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)

## 6. Registry-construction run

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out output
```

This demonstrates acquisition/reconciliation/export, but criterion mapping is disabled by that config.

Typical flow:

```text
load config
open storage
acquire enabled sources
extract + normalize
load prior active source contributions
reconcile canonical formats
assign method profiles
validate
apply criterion mapping when enabled
change detection
persist
write optional exports/reports
```

## 7. Criterion-mapped no-database run

```powershell
python -m registry_builder run `
  --config config\sources.criterion-mapping.quickstart.json `
  --workdir work `
  --out output
```

Verify the handoff artifacts:

```powershell
Test-Path output\registry.json
Test-Path output\criterion_claims.jsonl
(Get-Content output\criterion_claims.jsonl | Measure-Object -Line).Lines
```

The first two should be `True`; the claim count should be greater than zero.

The sibling risk manager now automatically loads `criterion_claims.jsonl` when `--registry-json` points to the sibling `registry.json`.

Full walkthrough: [`../../docs/GETTING_STARTED.md`](../../docs/GETTING_STARTED.md).

## 8. What to inspect after a run

When exports are enabled, common files include:

```text
output\run_report.json
output\coverage_report.md
output\registry.json
output\registry.csv
output\criterion_claims.jsonl   # when criterion mapping generated claims
```

Check at minimum:

- run status;
- source acquisition status;
- canonical format count;
- active source-record count;
- criterion-claim count when mappings are expected;
- validation errors/warnings;
- change summary;
- collision/review flags.

If the intended next step is risk assessment and `criterion_claims.jsonl` is absent/empty, stop and verify mapping configuration rather than interpreting the risk manager's resulting unknowns as format safety.

## 9. Offline replay

After snapshots have been cached:

```powershell
python -m registry_builder run `
  --config config\sources.example.json `
  --workdir work `
  --out output `
  --offline
```

Offline mode reuses cached snapshots only. It cannot discover an upstream release never previously acquired.

Read [`SOURCE_RETRIEVAL_AND_FALLBACKS.md`](SOURCE_RETRIEVAL_AND_FALLBACKS.md).

## 10. Run one source at a time

### NARA

```powershell
python -m registry_builder run `
  --config config\sources.nara.mongodb.example.json `
  --workdir work `
  --out output\nara
```

### PRONOM

```powershell
python -m registry_builder run `
  --config config\sources.pronom.mongodb.example.json `
  --workdir work `
  --out output\pronom
```

### Library of Congress FDD

```powershell
python -m registry_builder run `
  --config config\sources.loc.mongodb.example.json `
  --workdir work `
  --out output\loc
```

### QNL institution evidence

```powershell
python -m registry_builder run `
  --config config\qnl-institution-format-evidence.mongodb.example.json `
  --workdir work `
  --out output\qnl-evidence
```

The current canonical view is recomputed from active source contributions; earlier source records remain for provenance/history.

Read [`INCREMENTAL_SOURCE_UPDATES.md`](INCREMENTAL_SOURCE_UPDATES.md).

## 11. Periodic source refresh

A monitoring configuration may rerun approved sources periodically:

```powershell
python -m registry_builder run `
  --config config\sources.criterion-mapping.mongodb.example.json `
  --workdir work `
  --out output
```

However, rerunning online does not necessarily mean “use newest release.” Release behavior is adapter/config-specific.

For example, a pinned NARA config stays pinned. For NARA follow-latest monitoring use:

```json
"release_mode": "latest"
```

Many deployments should keep separate:

```text
pinned/reviewed production baseline
follow-latest monitoring configuration
```

See:

- [`NARA_ADAPTER_REQUIREMENTS.md`](NARA_ADAPTER_REQUIREMENTS.md)
- [`../../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md`](../../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md)

## 12. Local/downloaded source files

Use adapter-supported local-file modes when automatic acquisition is unavailable or a release must be staged manually.

Do not create one-off parsers outside the adapter framework; retain snapshot/provenance behavior.

Read:

- [`ADDING_AND_RUNNING_DATA_SOURCES.md`](ADDING_AND_RUNNING_DATA_SOURCES.md)
- [`NARA_LOCAL_FILES.md`](NARA_LOCAL_FILES.md)
- [`SOURCE_RETRIEVAL_AND_FALLBACKS.md`](SOURCE_RETRIEVAL_AND_FALLBACKS.md)

## 13. Validate exported registry

```powershell
python -m registry_builder validate `
  --registry output\registry.json
```

## 13b. Registry health check

`validate` checks a registry's structure. `health-check` checks the invariants
that make ingesting one source at a time trustworthy — run it after each source:

```bash
python -m registry_builder health-check \
  --registry out/registry.json \
  --storage-config config/sources.loc.local.json
```

```text
registry health: ok

  [pass] claims_point_at_live_canonicals
         0 of 8857 claim(s) reference a canonical_id that is not in the registry
  [pass] every_source_is_represented
         all 3 contributing source(s) have claims
  [pass] unendorsed_claims_are_not_identifiers
         0 unendorsed claim(s) leaked into the identifier map (102 retained as evidence)
  [pass] reconciliation_is_order_independent
         0 record(s) landed on a different canonical when re-run in a shuffled order

  canonical formats: 3095
  canonicals drawing on more than one source: 664
      nara_digital_preservation_framework + pronom_registry: 554
```

Each check corresponds to a way the pipeline has actually gone wrong, so a
failure names a real regression rather than a style violation:

| Check | Catches |
| --- | --- |
| `claims_point_at_live_canonicals` | claims left dangling after a later source reshaped canonicals |
| `every_source_is_represented` | a source's claims dropped from the export |
| `unendorsed_claims_are_not_identifiers` | a PUID an authority declined to assert presented as one of the format's ids |
| `reconciliation_is_order_independent` | the canonical set depending on which source ran first |

`--storage-config` is what enables the order-independence check: it re-reconciles
the stored source records in shuffled orders and compares. Without it that check
reports **SKIP**, never `pass`, and the overall status becomes `incomplete` — an
unrun check must not read as a clean bill of health. The command exits non-zero
only on `FAIL`.

The merge counts underneath are not pass/fail. They are the number to watch as
sources are added: adding an authority should only ever increase them.

The `needs review` block counts what reconciliation could not settle —
`heuristic_identifier_bridges` and `ambiguous_identifier_citations`. These are
expected, not errors; the point is that they are counted rather than silent.
`collision-report` lists them individually.

## 14. Identifier collision report

```powershell
python -m registry_builder collision-report `
  --registry output\registry.json `
  --sample-limit 50
```

Read [`IDENTIFIER_RECONCILIATION.md`](IDENTIFIER_RECONCILIATION.md).

## 15. Audit source/criterion coverage

```powershell
python -m registry_builder criterion-evidence-audit `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --out output\criterion_evidence_audit.json
```

Optional source filter:

```powershell
--source loc_fdd_xml
```

The audit helps distinguish:

```text
source field absent
source field present but not mapped
mapping exists but coverage limited
```

## 16. Validate criterion mappings

```powershell
python -m registry_builder mapping validate `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings
```

Do not approve a weak mapping simply to increase completeness.

Read:

- [`criterion_mapping_workflow.md`](criterion_mapping_workflow.md)
- [`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)

## 17. Backfill criterion claims

Dry run:

```powershell
python -m registry_builder criterion-claims backfill `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings `
  --dry-run
```

After review, omit `--dry-run` to write claims.

Combined config:

```powershell
python -m registry_builder criterion-claims backfill `
  --config config\criterion-claims-backfill.mongodb.example.json
```

Use `--include-drafts` only for projection/debugging. Use `--replace-source-claims` when a reviewed mapping update is intended to supersede older current claims from the affected source(s).

## 18. Add a new source or criterion mapping

Preferred flow:

```text
source
 -> SourceAdapter
 -> RawFormatRecord/native fields
 -> criterion evidence audit
 -> draft mapping
 -> mapping validation
 -> human approval
 -> backfill/integrated build
 -> risk-manager verification
```

Start with [`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md).

For adapter implementation:

1. [`ADDING_AND_RUNNING_DATA_SOURCES.md`](ADDING_AND_RUNNING_DATA_SOURCES.md)
2. [`ADAPTER_IMPLEMENTATION_GUIDE.md`](ADAPTER_IMPLEMENTATION_GUIDE.md)
3. [`ADAPTER_REFERENCE.md`](ADAPTER_REFERENCE.md)
4. [`IDENTIFIER_RECONCILIATION.md`](IDENTIFIER_RECONCILIATION.md)

## 19. Add a storage backend

A plugin subclasses `RegistryStore` and implements at least:

```python
upsert(collection, key, document)
query(collection, filter)
```

Example:

```json
{
  "storage": {
    "type": "mypkg.storage.sql:SqlRegistryStore"
  }
}
```

Read:

- [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
- [`ADAPTER_IMPLEMENTATION_GUIDE.md`](ADAPTER_IMPLEMENTATION_GUIDE.md)

## 20. Relationship to the risk manager

### Persistent-store handoff

```text
registry_builder -> RegistryStore -> RegistryReader -> risk manager
```

Example:

```powershell
cd ..\preservation_risk_manager
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"PDF","scope":"global"}' `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

### Export handoff

```text
output\registry.json
output\criterion_claims.jsonl
        |
        v
JsonRegistryStore
        |
        v
risk manager
```

Example:

```powershell
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --registry-json ..\qnl_format_registry_builder\output\registry.json `
  --format PDF `
  --evidence-summary
```

The risk manager auto-discovers the sibling claim export.

## 21. Tests

```powershell
cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"
pytest -q
```

For source/mapping changes, also run the smallest relevant real/configured pipeline and inspect the run/coverage report.

## Deeper references

- [`DOCUMENTATION_MAP.md`](DOCUMENTATION_MAP.md)
- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`ADDING_AND_RUNNING_DATA_SOURCES.md`](ADDING_AND_RUNNING_DATA_SOURCES.md)
- [`ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)
- [`STORAGE_AND_EXPORT_CONFIG.md`](STORAGE_AND_EXPORT_CONFIG.md)
- [`MONGODB_STORAGE_SCHEMA.md`](MONGODB_STORAGE_SCHEMA.md)
- [`IDENTIFIER_RECONCILIATION.md`](IDENTIFIER_RECONCILIATION.md)
- [`INCREMENTAL_SOURCE_UPDATES.md`](INCREMENTAL_SOURCE_UPDATES.md)
- [`criterion_mapping_workflow.md`](criterion_mapping_workflow.md)
- [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
