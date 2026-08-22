# Incremental source updates

The registry is intended to be populated and refreshed **source by source**. A normal update is not a fresh installation and does not require reacquiring every source.

Running one source should not erase evidence from other sources. A NARA refresh updates NARA evidence; PRONOM, LOC, DPC and other non-refreshed evidence continue from their latest successful stored source run.

## Default behavior

Incremental source updates are enabled by default:

```json
{
  "incremental_source_updates": true
}
```

When a pipeline run completes successfully for one or more sources, the pipeline:

1. extracts and normalizes records from successfully completed sources in the current run;
2. treats only those completed sources as refreshed;
3. reads latest successfully stored source records for sources not refreshed in this run;
4. rebuilds/reconciles the active canonical view from current-run records plus reused current evidence;
5. reruns normal mapping/materialization/validation/change detection;
6. persists the updated current view while retaining historical snapshots/source records.

## Selected-source refresh command

To refresh only selected sources from an existing reviewed configuration:

```powershell
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source nara_digital_preservation_framework `
  --workdir work `
  --out output `
  --report monitoring\nara-refresh.json
```

Repeat `--source` to refresh multiple sources:

```powershell
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source pronom `
  --source loc_fdd_xml_reviewed `
  --workdir work `
  --out output
```

The command does not rewrite the reviewed configuration. It creates a temporary selection beside that configuration so existing relative paths continue to resolve exactly as before, sets `incremental_source_updates=true`, enables only requested sources for that run, invokes the normal pipeline, then deletes the temporary file.

A source configured `enabled:false` can still be explicitly selected for a refresh; explicit operator selection is treated as the instruction to run it for that refresh.

Unknown source IDs are rejected before the pipeline starts.

## Same-source replacement

A successful refresh replaces only that source's active evidence.

If NARA is refreshed again, old NARA evidence is retained historically but is not reused as active NARA input. The new successful NARA run becomes the active NARA contribution. This allows upstream deletions/removals to be detected.

Other sources remain active from their latest successful runs.

## Optional-source failures

A failed optional source is not considered refreshed.

If NARA is `required:false` and acquisition fails, the incremental pipeline keeps its previous successful evidence active while processing other completed sources. The failure is reported separately; it is not treated as "no change".

Required-source failures abort the run.

## Pinned release versus upstream update

Rerunning an adapter does **not** necessarily mean adopting a newer release. The source's retrieval/release configuration remains authoritative.

Examples:

```text
NARA release_mode=pinned
    -> refresh verifies/reacquires the configured pinned release

NARA release_mode=latest
    -> online refresh may discover a newer complete release
```

The same principle applies to other adapters: review their acquisition configuration rather than assuming every online rerun means "latest".

A useful governance pattern is:

```text
production-baseline.json
    pinned/reviewed releases

monitor-latest.json
    selected sources allowed to discover newer upstream releases
```

A discovered new release can then be reviewed before changing the production pinned baseline.

## Online versus offline

Normal update monitoring should run online when the source is intended to discover upstream changes.

`--offline` uses cached snapshots only. Offline mode is useful for replay/recovery/reproducibility but cannot discover an upstream release that has never been acquired.

## What is recomputed

Even though only selected sources are reacquired, the pipeline still rebuilds the current canonical view from the complete active evidence set. This is intentional: identity reconciliation, mappings and derived current views must remain coherent after one source changes.

This is different from "download everything again":

```text
reacquisition       selected source(s) only
active evidence     selected new evidence + other sources' latest successful evidence
reconciliation      complete active evidence set
persistence         updated current canonical/claim view + historical provenance
```

## Risk and criterion evidence after refresh

The pipeline reruns configured criterion mapping from the active evidence set.

Current governed risk claims are rematerialized to current canonicals. If a refreshed source has a separately reviewed source-specific risk backfill/projection step, the run report's `risk_claim_materialization` section indicates when that reviewed backfill should be rerun. Do not invent new risk claims merely because a source was refreshed.

## Refresh report

`python -m registry_builder.refresh` prints a compact JSON report and can save it using `--report`.

Important fields include:

```text
run_id
requested_source_ids
refreshed_source_ids
source_results
raw_records_extracted
prior_source_records_reused
active_source_records
canonical_formats
change_detection
risk_claim_materialization
criterion_mapping
outputs
```

The full normal builder `run_report.json` remains available in the output directory when exports are enabled.

## Full rebuild behavior

The underlying pipeline can still be configured with:

```json
{
  "incremental_source_updates": false
}
```

That behavior rebuilds from only sources actually present/enabled in the run and is useful for isolated tests or deliberate full-baseline reconstruction.

The selected-source `registry_builder.refresh` command intentionally forces incremental updates because a partial-source run with incremental reuse disabled could remove unrelated active evidence.

## Operational recommendation

For normal local MongoDB operation:

1. maintain one reviewed production source configuration;
2. keep incremental updates enabled;
3. refresh only source(s) whose upstream state needs checking;
4. review acquisition status, resolved release metadata and change detection;
5. rerun any separately governed source-risk backfill only when the run report indicates it is necessary;
6. run the Preservation Risk Manager batch watchlist after accepted evidence updates.

Example sequence:

```text
registry_builder.refresh --source nara...
        ↓
review refresh/change report
        ↓
preservation_risk_manager batch-report --input watchlist.csv
        ↓
review curator HTML / retain JSON audit record
```
