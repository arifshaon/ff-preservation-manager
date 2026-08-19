# Adapter reference

This page documents the implemented adapter types in a consistent format.

For implementation rules and skeleton code, see `docs/ADAPTER_IMPLEMENTATION_GUIDE.md`.

## Common source config fields

All source adapters share these common fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique configured source instance. |
| `type` | yes | Adapter type registered in `registry_builder/adapters/__init__.py`. |
| `enabled` | no | Defaults to true. Disabled sources are listed but not run. |
| `required` | no | Defaults to true. If false, failures are reported but the run continues. |
| `retrieval_mode` | no | Human-readable mode; adapter-specific. |
| `notes` | no | Operational guidance for maintainers. |

All source adapters return `SourceSnapshot` objects from `acquire()` and `RawFormatRecord` objects from `extract()`.

---

## `standard_json`

### Purpose

Reads a simple curated JSON source package. This is useful for tests, small hand-curated sources, and offline demonstrations.

### Config

```json
{
  "id": "example_curated_source",
  "type": "standard_json",
  "enabled": true,
  "required": true,
  "uris": ["examples/sample_source_package.json"]
}
```

### Acquisition and extraction

Reads configured `uris`. A URI may be a local file path or HTTP/HTTPS URL. Emits one `RawFormatRecord` per JSON record.

### Identifier authority

Only mark identifiers as verified if the JSON record explicitly represents an authority source and the adapter logic supports that. In normal curated examples, identifiers are claims, not authority verification.

---

## `institution_policy_xlsx`

### Purpose

Reads an institution-specific file-format policy workbook and imports it as institutional policy overlays.

QNL is one configuration of this generic adapter. The adapter itself is not QNL-specific.

### Config

```json
{
  "id": "qnl_policy_current",
  "type": "institution_policy_xlsx",
  "enabled": true,
  "required": true,
  "institution_id": "qnl",
  "institution_name": "Qatar National Library",
  "institution_format_id_prefix": "QNL",
  "uris": ["input/QNL File Format Policy and Action Plan_27_November_2025.xlsx"],
  "field_map": {
    "institution_format_id": ["QNL Format ID"],
    "name": ["Digital file"],
    "extensions": ["File Extension(s)"],
    "mime_types": ["MIME type(s)", "MIME", "MIME Type", "Mime Type"],
    "category": ["Category/Plan(s)", "Category", "Plan"],
    "risk_level": ["QNL Risk Level", "Risk Level", "Risk"],
    "preservation_action": ["QNL Preservation Action", "Preservation Action", "Action"],
    "proposed_preservation_plan": ["QNL Proposed Preservation Plan", "Proposed Preservation Plan", "Plan"]
  }
}
```

### Acquisition and extraction

Reads configured workbook paths/URIs and snapshots each workbook. Emits one `RawFormatRecord` per substantive workbook row.

Important fields:

```text
name
extensions
mime_types
puids
loc_ids
wikidata_ids
institution_policy
raw
```

The `institution_policy` object carries local risk/action/plan/tool fields.

### Field mapping behavior

The adapter resolves configured workbook column names using `field_map`. Configured fields fail loudly if requested columns are missing. This prevents silent wrong-column matching.

Rows with non-substantive names such as blank, `?`, `n/a`, or `todo` are skipped.

### Identifier authority

Institutional workbook identifiers are local claims. A PUID copied into the workbook is not a verified PRONOM identifier until PRONOM confirms it.

---

## `nara_digital_preservation_framework`

### Purpose

Reads NARA's Digital Preservation Framework as an external preservation-hazard source.

This is the preferred NARA adapter. The older `nara_preservation_csv` name is a compatibility alias.

### When to use

Use this to compare institutional policy with an external hazard estimator and to preserve NARA native numeric ratings.

### Config: pinned release

Use `pinned` for reproducible audit runs.

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "required": true,
  "retrieval_mode": "published_csv",
  "release_mode": "pinned",
  "release_date": "20260320",
  "github_ref": "master"
}
```

### Config: latest release

Use `latest` for scheduled refreshes.

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "enabled": true,
  "required": false,
  "retrieval_mode": "published_csv",
  "release_mode": "latest",
  "fallback_release_date": "20260320"
}
```

### Config: explicit URIs

Use `explicit_uris` for tests and one-off comparisons.

```json
{
  "release_mode": "explicit_uris",
  "uris": [
    "https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Plan_Spreadsheet/NARA_PreservationActionPlan_FileFormats_20260320.csv",
    "https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Risk_Matrix/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv"
  ]
}
```

### Config: local admin files

Use `local_files` when an administrator downloaded the NARA CSVs manually.

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

### Extraction

Emits NARA records with:

```text
name
category
description
extensions
mime_types
puids from PRONOM URL
loc_ids from LOC URL
nara_ids
wikidata_ids
urls
hazard
raw
```

The hazard object carries both normalized and native values:

```text
external_band
rating / normalized_rating
external_rating_native
external_rating_native_scale
external_rating_native_direction
native_rating_band
nara_total
```

### Identifier authority

NARA Format IDs are verified NARA identifiers. PUIDs found in NARA PRONOM URLs are useful claims but are not verified PRONOM identifiers.

---

## `nara_preservation_csv`

Deprecated compatibility alias for NARA CSV-based configurations. Do not use for new configs. Use `nara_digital_preservation_framework`.

---

## `pronom_registry`

### Purpose

Reads PRONOM registry records from the public GitHub JSON dataset.

### When to use

Use this to verify PUIDs and strengthen canonical matching.

### Config: full GitHub archive

Use archive mode for full PRONOM runs when the upstream archive is available. This snapshots one repository ZIP and extracts PRONOM JSON records from it.

```json
{
  "id": "pronom_registry",
  "type": "pronom_registry",
  "enabled": true,
  "required": false,
  "retrieval_mode": "github_archive",
  "archive_url": "https://github.com/nationalarchives/pronom/archive/refs/heads/develop.zip",
  "include_paths": ["signatures/fmt/", "signatures/x-fmt/"]
}
```

### Config: full GitHub tree with temporary per-record snapshots

Use this when PRONOM is only available as individual JSON files. The tree snapshot is retained, but each JSON file is downloaded to a temporary file, extracted, and deleted after extraction. The normalized source records, including raw PRONOM record payloads, are still persisted through the selected storage backend such as MongoDB.

```json
{
  "id": "pronom_registry",
  "type": "pronom_registry",
  "enabled": true,
  "required": false,
  "retrieval_mode": "github_json",
  "github_tree_url": "https://api.github.com/repos/nationalarchives/pronom/git/trees/develop?recursive=1",
  "raw_base_url": "https://raw.githubusercontent.com/nationalarchives/pronom/develop",
  "include_paths": ["signatures/fmt/", "signatures/x-fmt/"],
  "snapshot_policy": "temporary"
}
```

For tree-based `github_json` runs, `snapshot_policy` defaults to `temporary` to prevent thousands of cached JSON files. Use `snapshot_policy: "cache"` only when deliberately retaining per-record snapshots for audit/debugging.

### Config: targeted PUIDs

Use this for fast tests or small checks. Targeted runs default to retained cache snapshots because they usually involve only a few records.

```json
{
  "id": "pronom_registry",
  "type": "pronom_registry",
  "enabled": true,
  "required": false,
  "retrieval_mode": "github_json",
  "puids": ["fmt/18", "x-fmt/111"]
}
```

Targeted runs can also use temporary snapshots:

```json
{
  "id": "pronom_registry",
  "type": "pronom_registry",
  "enabled": true,
  "required": false,
  "retrieval_mode": "github_json",
  "puids": ["fmt/18", "x-fmt/111"],
  "snapshot_policy": "temporary"
}
```

### Acquisition

Can acquire:

```text
one GitHub archive ZIP for full PRONOM runs
explicit raw JSON URIs
configured PUIDs converted to raw JSON URLs
a recursive GitHub tree with temporary or retained per-record snapshots
```

### Snapshot policy

`github_archive` mode retains one archive snapshot.

`github_json` mode supports:

```text
snapshot_policy: cache
  retain individual source JSON snapshots in work/snapshots/<source_id>/

snapshot_policy: temporary
  write individual source JSON files to work/temporary_snapshots/<source_id>/
  extract records
  delete the temporary JSON files after extraction
```

The snapshot metadata and evidence payload record whether a snapshot was retained.

### Extraction

Emits:

```text
name
category
description
extensions
mime_types
puids
urls
raw PRONOM record
```

For archive acquisition, one source snapshot may produce many PRONOM raw records. Each extracted record records the archive URI and internal JSON filename in its evidence payload.

For temporary JSON acquisition, individual JSON files are not kept in the snapshot cache. The raw PRONOM record payload is still carried in the emitted source record and persisted by the configured storage backend.

### Identifier authority

PUIDs emitted by this adapter are verified PRONOM identifiers.

### Failure handling

Usually `required:false` in multi-source registry runs so a temporary GitHub issue does not destroy a NARA/LOC baseline run. Consider `required:true` for identity-quality runs where verified PUIDs are mandatory.

### Tests

Covered by `tests/test_pronom_registry.py`.

---

## `pronom_droid_xml`

### Purpose

Parses PRONOM/DROID signature XML files.

### When to use

Use this when you already have a DROID signature XML file or need compatibility with a DROID XML workflow.

For source-level PRONOM data, prefer `pronom_registry`.

### Config

```json
{
  "id": "pronom_droid_signature_file",
  "type": "pronom_droid_xml",
  "enabled": true,
  "required": false,
  "uris": ["input/DROID_SignatureFile.xml"]
}
```

### Extraction

Emits one record per `FileFormat` element, including:

```text
name
extensions
mime_types
puids
urls
raw XML attributes
```

### Identifier authority

PUIDs from PRONOM/DROID XML are verified PRONOM identifiers.

---

## `loc_fdd_xml`

### Purpose

Parses Library of Congress Format Description Document XML records.

### When to use

Use this to add LOC FDD identifiers and sustainability evidence.

### Config: official FDD XML ZIP

The default sample config enables this source as optional enrichment:

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

### Config: local XML directory

Use this when an administrator has staged individual FDD XML files locally:

```json
{
  "id": "loc_fdd_xml",
  "type": "loc_fdd_xml",
  "enabled": true,
  "required": false,
  "uris": [],
  "directory": "input/loc_fdd_xml"
}
```

### Config: explicit XML URI

```json
{
  "id": "loc_fdd_xml",
  "type": "loc_fdd_xml",
  "enabled": true,
  "required": false,
  "uris": ["https://www.loc.gov/preservation/digital/formats/fddXML/fdd000030.xml"]
}
```

### Acquisition

Can acquire:

```text
the official FDD XML ZIP
explicit XML or ZIP URIs
all .xml files in a configured local directory
```

### Extraction

Emits:

```text
name
category
extensions
puids
loc_ids
wikidata_ids
urls
raw snapshot/source-file reference
```

For ZIP acquisition, one source snapshot may produce many LOC raw records. Each extracted record records the ZIP URI and internal XML filename in its evidence payload.

The parser is intentionally conservative and extracts a limited subset. Detailed sustainability-claim extraction should be added in the later preservation-risk analysis layer.

### Identifier authority

LOC FDD IDs from LOC FDD XML are verified LOC identifiers.

PUIDs found inside LOC XML are useful claims but should be treated according to normalization authority rules.

### Failure handling

Usually `required:false` because it is enrichment evidence.

### Tests

Covered by `tests/test_loc_fdd_xml.py`.

---

## `wikidata_sparql`

### Purpose

Harvests cross-registry identity links from the Wikidata Query Service: the QID
for a format, plus the PUIDs, LoC FDD IDs, MIME types and extensions Wikidata
asserts for it, plus community-maintained context (developer, publication date,
"replaced by").

### When to use

Use this to join records that other sources describe under different
identifiers, and to surface supersession relationships no single authority
publishes.

Wikidata sits in the **graph-linking tier**, not the evaluative tier. It
contributes links between identifiers that authorities already own. It
deliberately contributes **no** sustainability or risk claims, so no criterion
mapping is configured for it — a crowd-maintained graph must not supply
preservation evidence on the same footing as a national archive.

### Config

```json
{
  "id": "wikidata_sparql",
  "type": "wikidata_sparql",
  "enabled": true,
  "required": false,
  "retrieval_mode": "sparql",
  "endpoint": "https://query.wikidata.org/sparql"
}
```

A full example is `config/sources.wikidata.mongodb.example.json`.

`endpoint` and `query` are both optional. Supplying `query` replaces the built-in
one entirely; the result set must still expose the same binding names
(`item`, `itemLabel`, `puids`, `fdds`, `exts`, `mimes`, `developers`,
`replacedBy`, `published`).

### Local input files

The adapter follows the shared acquisition policy: a saved SPARQL JSON result
dropped in `input/wikidata_sparql/` is used instead of contacting the endpoint
(set `force_check_url: true` to fetch fresh, with automatic fallback to the
dropped file on 404/503). Wikidata publishes no edition, so record when the
query was run in `manifest.json` as `{"published_at": "YYYY-MM-DD"}` for the
data-age report. See
[`SOURCE_RETRIEVAL_AND_FALLBACKS.md`](SOURCE_RETRIEVAL_AND_FALLBACKS.md).

### Run it after PRONOM, not on its own

Every harvested record anchors on an asserted PUID, so a standalone run has
nothing to attach to: the PUIDs are unverified claims, reconciliation falls
through to name keys, and colliding names abort the run. Run this source
alongside or after `pronom_registry`.

### Acquisition

Issues one GET to the SPARQL endpoint requesting `format=json`. The query is
encoded into the request URI, which is also the snapshot cache key, so editing
the query produces a new snapshot instead of silently overwriting the previous
one.

### Extraction

The query anchors on **P2748 (PRONOM file format ID)**. Wikidata holds tens of
thousands of items that are instances or subclasses of "file format", the
overwhelming majority of which carry no identifier a preservation authority
recognises. Anchoring on P2748 keeps the harvest to the ~2.3k items that can
actually join the registry and makes every emitted record resolvable by
construction.

Two disambiguation behaviours are worth knowing about, because both exist to
stop records becoming orphan canonicals:

**One record per asserted PUID.** A Wikidata item often describes a format
concept more broadly than PRONOM versions it — "Blend file" asserts both
`fmt/902` and `fmt/903`. A single record for such an item cannot be bridged onto
either PRONOM canonical without guessing, so reconciliation correctly declines
and the item becomes a canonical of its own. Splitting states what Wikidata
actually means: this QID applies to each of those formats. The sibling PUIDs are
retained in `native_fields.wikidata.asserted_puids`.

**Names are qualified when they are not unique.** Wikidata labels are not unique
— seven separate items are each called "PowerProject". Reconciliation groups
unverified records by name, so same-label records land in one group carrying
conflicting PUID claims and the bridge refuses them. Where a label is shared, or
an item was split across several PUIDs, the record name becomes
`Label (fmt/NNN)`. The unqualified label is preserved in
`native_fields.wikidata.label`.

Rows with no QID or no PUID are dropped: without a QID there is nothing to cite,
and without a PUID the row cannot be reconciled against anything.

Emits:

```text
name
extensions
mime_types
puids
loc_ids
wikidata_ids
urls
native_fields.wikidata (developers, replaced_by, publication_date,
                        asserted_puids, label)
```

### Identifier authority

The adapter emits every identifier with `verified=False`. Wikidata is not the
authority for any namespace it references, including — for registry purposes —
its own QIDs, which are weak by strength anyway. Its assertions are candidate
links for reconciliation to weigh, never strong reconciliation keys.

That flag is a floor, not a guarantee: `normalize_record` computes
`verified = adapter_flag or is_verified_identifier(kind, source_type, rules)`, so
`identifier_kinds` can still promote them. Note that the shipped default rules
list `"wikidata"` in `puid.verified_from`. Nothing is registered under that bare
type name today, which is why this adapter is called `wikidata_sparql` rather
than `wikidata` despite the usual preference for conceptual source names — an
adapter registered as `wikidata` would turn crowd-asserted PUIDs into verified
strong keys in every existing config.

### Property identifiers

The properties are pinned as named constants because getting them wrong fails
silently — a wrong property returns a well-formed result set that is simply
almost empty.

| Constant | Property | Not to be confused with |
| --- | --- | --- |
| `P_PRONOM_FILE_FORMAT` | `P2748` PRONOM file format ID | `P2749` PRONOM **software** ID |
| `P_LOC_FDD` | `P3266` LoC Format Description ID | `P3267` Flickr user ID |
| `P_FILE_EXTENSION` | `P1195` | |
| `P_MEDIA_TYPE` | `P1163` | |
| `P_DEVELOPER` | `P178` | |
| `P_PUBLICATION_DATE` | `P577` | |
| `P_REPLACED_BY` | `P1366` | |

The two confusable pairs are asserted directly in the tests.

### Failure handling

Use `required:false`. This is enrichment: the registry is complete without it.

### Tests

Covered by `tests/test_wikidata_sparql_adapter.py`.

---

## `qnl_policy_xlsx`

Deprecated compatibility alias for old QNL-specific configuration. Do not use in new configs. Use `institution_policy_xlsx` with `institution_id: "qnl"`.
