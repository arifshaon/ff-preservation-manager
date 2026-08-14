# Source retrieval, cache, offline mode, and fallbacks

This project separates four related but different concepts:

```text
online acquisition
  fetch the configured upstream source now and snapshot it

snapshot cache
  content-addressed copies of source material under work/snapshots/<source_id>/

offline mode
  replay previously cached snapshots without touching the network

local/admin files
  treat administrator-supplied files as the current source material and snapshot them
```

The distinction matters for audit and reproducibility. A cached snapshot proves what was used in a previous run. A local/admin file proves an operator supplied a source file for this run. Both avoid the network, but they are different provenance paths.

## Snapshot cache

Every acquired source file is copied into:

```text
work/snapshots/<source_id>/
```

The filename is based on the source content SHA-256. Each source also keeps:

```text
work/snapshots/<source_id>/.snapshot_index.json
```

The index maps the configured URI or local-file key to:

```text
sha256
local_path
content_type
acquired_at
source_type
metadata
```

Online runs still check the upstream source. If the upstream content has not changed, the existing content-addressed file is reused and the run report shows the snapshot as unchanged.

## Offline mode

Use offline mode when the goal is to reproduce a previous run from already-cached source snapshots:

```bash
python -m registry_builder run --config config/sources.example.json --workdir work --out output --offline
```

or:

```json
{
  "offline": true
}
```

Offline mode does not fetch remote URLs and does not read new admin-downloaded files unless those files were previously indexed by the adapter. If a requested URI is missing from the cache index, the run fails clearly.

Use offline mode for audit replay, disaster testing, and reproducibility checks.

## Local/admin files

Use local/admin files when an operator has manually downloaded source files and wants the run to use those files as the source input for this run.

For NARA, this is exposed as:

```json
{
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

The adapter copies those files into the content-addressed snapshot cache and records metadata such as:

```text
source_location: local_file
admin_supplied: true
release_mode: local_files
release_date
kind
```

Use local/admin files when GitHub is blocked, a release has been staged internally, or an operator needs to build from a reviewed file bundle.

## Source requiredness

Each source can declare whether it is required:

```json
{
  "id": "nara_digital_preservation_framework",
  "required": false
}
```

Required sources abort the run if acquisition or extraction fails.

Optional sources are recorded in `run_report.json` as failed, but the pipeline continues with the remaining sources. This prevents an optional external outage from destroying a QNL-only registry run.

A failed optional source summary includes:

```json
{
  "source_id": "nara_digital_preservation_framework",
  "enabled": true,
  "required": false,
  "status": "failed",
  "error_type": "HTTPError",
  "error": "HTTP Error 403: rate limit exceeded"
}
```

## NARA release decision tree

NARA supports these release modes:

```text
explicit_uris
  use the exact configured URIs

pinned
  construct the two dated NARA release CSV URLs from release_date

latest
  discover the newest matching action-plan and numbered-risk CSV pair through GitHub

local_files
  use administrator-supplied local files as the source input
```

For `latest`, fallback order is:

```text
1. online latest discovery
2. cached .nara_release_index.json
3. fallback_local_files / manual_fallback_files / fallback_files
4. pinned fallback_release_date
```

If a fallback is used, the snapshot metadata records the fallback mode and the original resolution error, for example:

```text
release_mode: latest_cached_fallback
release_resolution_error: HTTPError: HTTP Error 403
```

or:

```text
release_mode: latest_local_fallback
source_location: local_file
admin_supplied: true
```

This keeps the run operational while making the fallback visible to auditors.

## GitHub API token

GitHub's unauthenticated API limit is low. For scheduled latest-mode runs, set:

```bash
GITHUB_TOKEN=<token>
```

The HTTP utility will attach it to GitHub API requests. This is mainly for release discovery; source files are still content-addressed after acquisition.
