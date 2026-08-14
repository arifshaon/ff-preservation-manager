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

All source adapters should return `SourceSnapshot` objects from `acquire()` and `RawFormatRecord` objects from `extract()`.

---

## `standard_json`

### Purpose

Reads a simple curated JSON source package. This is useful for tests, small hand-curated sources, and demonstration runs.

### When to use

Use this when a source is already represented in the internal-style JSON structure or when you need a lightweight fixture.

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

### Acquisition

Reads configured `uris`. A URI may be a local file path or an HTTP/HTTPS URL, depending on the base read helper.

### Extraction

Emits one `RawFormatRecord` per JSON record.

### Identifier authority

Only mark identifiers as verified if the JSON record explicitly represents an authority source and the adapter logic supports that. In normal curated examples, identifiers should be treated as claims, not authority verification.

### Failure handling

Use `required:true` for demo runs where the sample must exist. Use `required:false` only if the source is optional enrichment.

### Tests

Covered by exporter, pipeline, and storage smoke tests that use the sample source.

---

## `institution_policy_xlsx`

### Purpose

Reads an institution-specific file-format policy workbook and imports it as institutional policy overlays.

QNL is one configuration of this generic adapter. The adapter itself is not QNL-specific.

### When to use

Use this when an institution maintains its own preservation risk/action spreadsheet and the registry should compare it with external sources.

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

### Acquisition

Reads configured workbook paths/URIs and snapshots each workbook.

### Extraction

Emits one `RawFormatRecord` per substantive workbook row.

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

The adapter resolves configured workbook column names using the `field_map`.

Configured fields fail loudly if the requested columns are missing. This prevents silent wrong-column matching.

Rows with non-substantive names such as blank, `?`, `n/a`, or `todo` are skipped.

### Identifier authority

Institutional workbook identifiers are local claims. A PUID copied into the workbook is not a verified PRONOM identifier until PRONOM confirms it.

### Failure handling

For a QNL production registry run, this should normally be `required:true`.

### Tests

Covered by `tests/test_qnl_policy_xlsx.py`.

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
  "required": false,
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

### Latest fallback order

When `release_mode` is `latest`, the adapter tries:

```text
1. online latest discovery through GitHub contents API
2. cached .nara_release_index.json
3. fallback_local_files / manual_fallback_files / fallback_files
4. pinned fallback_release_date
```

### Acquisition

The adapter snapshots the NARA action-plan CSV and the numbered risk-matrix CSV.

Snapshot metadata records:

```text
release_mode
release_date
kind
github_ref
github_path
github_blob_sha, when available
source_location, online or local_file
admin_supplied, when local files are used
release_resolution_error, when fallback is used
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

NARA Format IDs are verified NARA identifiers.

PUIDs found in NARA PRONOM URLs are useful claims but are not verified PRONOM identifiers.

### Failure handling

Usually set `required:false`. NARA enriches the registry, but a temporary GitHub or NARA issue should not prevent a QNL-only registry build unless the run explicitly requires external hazard reconciliation.

### Tests

Covered by `tests/test_nara_preservation_csv.py` and reconciliation tests.

---

## `nara_preservation_csv`

### Purpose

Deprecated compatibility alias for NARA CSV-based configurations.

### When to use

Do not use for new configs. Use `nara_digital_preservation_framework`.

### Behavior

Delegates to the NARA Digital Preservation Framework logic but keeps the old adapter type name for backward compatibility.

---

## `pronom_registry`

### Purpose

Reads PRONOM registry records from the public GitHub JSON dataset.

### When to use

Use this to verify PUIDs and strengthen canonical matching.

### Config: targeted PUIDs

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

### Config: full GitHub tree

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

### Acquisition

Can acquire:

```text
explicit raw JSON URIs
configured PUIDs converted to raw JSON URLs
a recursive GitHub tree filtered to PRONOM JSON signature paths
```

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

### Identifier authority

PUIDs emitted by this adapter are verified PRONOM identifiers.

### Failure handling

Often `required:false` in early registry runs. Consider `required:true` for identity-quality runs where verified PUIDs are mandatory.

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

### Acquisition

Snapshots configured XML files or URIs.

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

### Failure handling

Usually `required:false` unless this is the main PRONOM source for the run.

---

## `loc_fdd_xml`

### Purpose

Parses Library of Congress FDD XML records.

### When to use

Use this to add LOC FDD identifiers and sustainability evidence.

### Config

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

### Acquisition

Reads configured XML URIs and/or all `.xml` files in a configured directory.

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
raw snapshot reference
```

The parser is intentionally conservative and extracts a limited subset.

### Identifier authority

LOC FDD IDs from LOC FDD XML are verified LOC identifiers.

PUIDs found inside LOC XML are useful claims but should be treated according to normalization authority rules.

### Failure handling

Usually `required:false` because it is enrichment evidence.

---

## `qnl_policy_xlsx`

### Purpose

Deprecated compatibility alias for old QNL-specific configuration.

### When to use

Do not use in new configs. Use `institution_policy_xlsx` with `institution_id: "qnl"`.

### Behavior

Delegates to the generic institution policy workbook logic while preserving the old adapter type name.
