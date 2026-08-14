# Incremental source updates

The registry is intended to be populated and refreshed source by source.

Running one source should not erase evidence from other sources. A NARA run should update NARA evidence. A later PRONOM run should update PRONOM evidence and augment the same canonical formats where reconciliation finds a match. QNL institutional policy can then add local policy, readiness, action, and decision evidence to the same canonical records.

## Default behavior

Incremental source updates are enabled by default:

```json
{
  "incremental_source_updates": true
}
```

When a pipeline run completes successfully for one or more sources, the pipeline:

1. extracts and normalizes the records from the source or sources in the current run;
2. treats those completed sources as refreshed;
3. reads the latest stored source records for all other sources from the selected `RegistryStore`;
4. rebuilds the canonical registry from current-run records plus the latest stored records from other sources;
5. writes updated canonical formats, identifiers, assessments, and change events back to the store.

This means source-by-source population works:

```text
Run 1: NARA
  -> registry contains NARA evidence

Run 2: PRONOM
  -> registry is rebuilt from PRONOM evidence + latest stored NARA evidence
  -> matching canonical formats are augmented, not replaced

Run 3: QNL workbook
  -> registry is rebuilt from QNL evidence + latest stored PRONOM and NARA evidence
  -> institutional policy overlays are attached to matching canonical formats
```

## Same-source replacement

A successful run replaces only that source's active evidence.

If NARA is run again, older NARA source records are not reused for reconciliation. The new NARA records become the active NARA evidence. This allows deletions or upstream removals within that source to be detected properly.

Other source evidence remains active unless those sources are also refreshed in the same run.

## Optional source failures

A failed optional source is not considered refreshed.

If NARA is marked `required:false` and GitHub is temporarily unavailable, the run records the source failure but keeps the last successful NARA evidence active while rebuilding the registry from the other completed sources plus stored evidence.

Required source failures still abort the run.

## Full rebuild behavior

To force the older full-run behavior, set:

```json
{
  "incremental_source_updates": false
}
```

With this setting, the canonical registry is rebuilt only from the sources present in the current run. This is useful for isolated tests but should not be the normal production population mode.

## Report fields

Incremental runs include these report fields:

```text
incremental_source_updates
raw_records_extracted
prior_source_records_reused
active_source_records
refreshed_source_ids
```

Meaning:

| Field | Meaning |
| --- | --- |
| `raw_records_extracted` | Records extracted from the source or sources in this run. |
| `prior_source_records_reused` | Latest stored records reused from sources not refreshed this run. |
| `active_source_records` | Total evidence records used for reconciliation. |
| `refreshed_source_ids` | Source IDs successfully refreshed in this run. |

## Operational recommendation

For normal population into a local MongoDB registry, use one stable database and run sources one by one:

```text
format_registry
```

Example order:

```text
1. NARA pinned release
2. PRONOM targeted/full registry
3. LOC FDD XML, if available
4. QNL institutional policy workbook
5. later quarterly refreshes
```

Each run updates one source's evidence and then recomputes the registry from all active evidence in the store.
