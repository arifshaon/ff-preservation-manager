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

## The acquisition policy (one convention for every source)

Every shipped adapter follows one decision order, implemented once in the
adapter base class (new adapters get it by implementing `network_acquire()`
instead of `acquire()`):

```text
1. Files exist in input/<source_id>/  ->  use them; do NOT contact the network.
   A dropped file is explicit admin intent.
2. force_check_url: true              ->  fetch fresh anyway; if the fetch fails
   (404, 503, DNS, timeout) fall back to the dropped files and record why in
   snapshot metadata (network_error, network_fallback).
3. No dropped files                   ->  fetch from the network; on failure,
   replay the cached snapshots from the previous run and record why.
```

`acquisition_policy` can pin a mode explicitly:

```text
auto          the order above (default)
local_only    dropped files or fail loudly
network_only  fetch or fail; no silent fallback
cache_only    replay cache only (what --offline maps to)
```

Create the drop folders, each with a per-source README, with:

```bash
python -m registry_builder init-source-inbox --config config/sources.example.json
```

Folders are only created for sources whose adapter actually reads dropped
files, so a file can never be silently ignored in a folder this command made.
The default root is `input/` in the directory you run from — the same
convention as the `work`/`out` defaults. An explicit `input_root` in the
pipeline config resolves relative to the config file, like every other
config-referenced path; `input_dir` on a single source overrides its folder.

### Provenance for dropped files

`acquired_at` says when we fetched data; it says nothing about how old the data
is. Every snapshot therefore also carries `source_published_at`, `edition`, and
`acquisition_mode` (`local` / `network` / `cache`):

- NARA infers release date and file kind from its published filenames.
- Network fetches use the HTTP `Last-Modified` header when the source sends one.
- Anything else can be declared in `input/<source_id>/manifest.json`
  (`{"published_at": ..., "edition": ..., "files": {"<name>": {...}}}`) or a
  per-file `<name>.meta.json` sidecar. Sidecar beats per-file manifest entry
  beats folder-level manifest.

### Testing every source locally, offline

The full walkthrough for a machine with the source files already downloaded:

```bash
# 1. create the drop folders (each gets a README saying what to drop)
python -m registry_builder init-source-inbox --config config/sources.criterion-mapping.quickstart.json

# 2. drop the files
input/pronom_registry/                    develop.zip  (github.com/digital-preservation/pronom archive)
input/nara_digital_preservation_framework/ the two release CSVs, published filenames kept
input/loc_fdd_xml/                        fddXML.zip
input/wikidata_sparql/                    a saved SPARQL JSON result
input/pronom_droid_xml/                   DROID_SignatureFile_V###.xml

# 3. run — every source uses its dropped file; the network is not contacted
python -m registry_builder run --config config/sources.criterion-mapping.quickstart.json
```

The acquire lines confirm it per source:

```text
[registry-builder] source nara_digital_preservation_framework acquired 2 snapshot(s);
  ... via=local; published 2026-03-20 (152 day(s) old)
```

`via=local` with no `network_error` means the dropped file was used by choice,
not as a fallback. To refresh one source from the network later, either empty
its folder or set `force_check_url: true` on that source.

### Data age is reported on every check

Each acquisition logs and reports how old the data is, in two distinct ages:

```text
[registry-builder] source nara acquired 2 snapshot(s); ... via=local;
  published 2026-03-20 (152 day(s) old); last fetched 3 day(s) ago
```

The run report carries the same per source under `data_currency`
(`acquisition_modes`, `editions`, `source_published_at`,
`published_age_days_max`, `acquired_age_days_max`, `publication_date_known`,
`network_errors`). A source whose publication date is unknown says so rather
than pretending freshness.

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
  "source_id": "pronom_registry",
  "enabled": true,
  "required": false,
  "status": "failed",
  "error_type": "HTTPError",
  "error": "HTTP Error 403: rate limit exceeded"
}
```

## Default online sources

`config/sources.example.json` now enables three real evidence sources by default:

```text
NARA   -> pinned external hazard source
PRONOM -> verified PUID and format-identity source
LOC    -> FDD XML sustainability/evidence source
```

PRONOM and LOC are optional by default so a temporary upstream/network failure is visible in the run report but does not destroy the baseline NARA registry run.

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

If a fallback is used, the snapshot metadata records the fallback mode and the original resolution error.

## PRONOM GitHub JSON retrieval

The PRONOM source-level adapter supports:

```text
puids
  targeted PUID list converted to raw GitHub JSON URLs

uris
  explicit raw JSON URLs

github_tree_url
  recursive GitHub tree listing filtered to PRONOM JSON signature paths
```

For full-tree runs, use:

```json
{
  "id": "pronom_registry",
  "type": "pronom_registry",
  "enabled": true,
  "required": false,
  "retrieval_mode": "github_json",
  "github_tree_url": "https://api.github.com/repos/nationalarchives/pronom/git/trees/develop?recursive=1",
  "raw_base_url": "https://raw.githubusercontent.com/nationalarchives/pronom/develop",
  "include_paths": ["signatures/fmt/", "signatures/x-fmt/"]
}
```

Use targeted `puids` for fast tests.

## LOC FDD XML ZIP retrieval

The LOC adapter supports the official FDD XML ZIP as an online source:

```json
{
  "id": "loc_fdd_xml",
  "type": "loc_fdd_xml",
  "enabled": true,
  "required": false,
  "retrieval_mode": "fdd_xml_zip",
  "zip_uri": "https://www.loc.gov/preservation/digital/formats/fddXML.zip"
}
```

The ZIP is stored as one source snapshot. Extraction emits one raw source record per XML file inside the archive. Each extracted record keeps the ZIP URI and internal XML filename in its evidence payload.

The same adapter still supports explicit XML URIs and local XML directories for admin-staged runs.

## GitHub API token

GitHub's unauthenticated API limit is low. For scheduled NARA latest-mode or PRONOM full-tree runs, set:

```bash
GITHUB_TOKEN=<token>
```

The HTTP utility will attach it to GitHub API requests. This is mainly for release discovery and tree listing; source files are still content-addressed after acquisition.
