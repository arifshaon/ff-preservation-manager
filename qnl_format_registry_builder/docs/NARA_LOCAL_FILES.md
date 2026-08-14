# NARA local file retrieval

NARA can be acquired from administrator-supplied files as a first-class source mode. This is useful when an admin has manually downloaded the release CSVs, when GitHub is temporarily unavailable, or when a run must use internally staged source files.

This is different from `--offline`:

```text
--offline
  replay previously cached source snapshots

release_mode: local_files
  treat supplied local files as the current source material and snapshot them
```

The local files are still copied into the content-addressed snapshot cache under `work/snapshots/<source_id>/`, and the run report records whether the local files changed since the previous run.

## Deliberate local-file run

Use `release_mode: local_files` when you want the NARA adapter to read admin-downloaded CSVs directly:

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "required": false,
  "retrieval_mode": "published_csv",
  "release_mode": "local_files",
  "local_files": [
    {
      "path": "input/nara/NARA_PreservationActionPlan_FileFormats_20260320.csv",
      "kind": "preservation_action_plan",
      "release_date": "20260320"
    },
    {
      "path": "input/nara/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv",
      "kind": "risk_matrix_numbered",
      "release_date": "20260320"
    }
  ]
}
```

The `kind` and `release_date` fields are optional when they can be inferred from the NARA filenames, but providing them is better for audit clarity.

The adapter records snapshot metadata such as:

```text
source_location: local_file
admin_supplied: true
release_mode: local_files
release_date: 20260320
kind: preservation_action_plan / risk_matrix_numbered
```

## Latest-mode local fallback

Use `fallback_local_files` when the desired normal mode is `latest`, but an admin has staged files to use if GitHub/API discovery is unavailable:

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "required": false,
  "retrieval_mode": "published_csv",
  "release_mode": "latest",
  "fallback_release_date": "20260320",
  "fallback_local_files": [
    "input/nara/NARA_PreservationActionPlan_FileFormats_20260320.csv",
    "input/nara/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv"
  ]
}
```

Fallback order for `latest` is:

```text
1. online latest discovery
2. cached .nara_release_index.json
3. fallback_local_files / manual_fallback_files / fallback_files
4. pinned fallback_release_date
```

When local fallback is used, the snapshot metadata records:

```text
release_mode: latest_local_fallback
source_location: local_file
admin_supplied: true
release_resolution_error: <original GitHub/API error>
```

This lets the registry build complete while still making the fallback visible to reviewers and auditors.
