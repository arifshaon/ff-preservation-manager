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

### Config: full GitHub tree

The default sample config enables this source as optional enrichment:

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

### Config: targeted PUIDs

Use this for fast tests or small checks:

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

### Acquisition

Can acquire:

```text
explicit raw JSON URIs
configured PUIDs converted to raw JSON URLs
a recursive GitHub tree filtered to PRONOM JSON signature paths
```

For scheduled full-tree runs, set `GITHUB_TOKEN` to reduce GitHub API rate-limit risk.

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

## `qnl_policy_xlsx`

Deprecated compatibility alias for old QNL-specific configuration. Do not use in new configs. Use `institution_policy_xlsx` with `institution_id: "qnl"`.
