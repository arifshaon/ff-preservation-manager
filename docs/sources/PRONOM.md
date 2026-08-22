# PRONOM

## What it is

PRONOM is The National Archives (UK) technical registry of file formats. This project uses PRONOM as the authority for **PRONOM Unique Identifiers (PUIDs)** and as a major source of format-identification metadata.

Official pages:

```text
PRONOM website/about:
https://pronom.nationalarchives.gov.uk/about

Official data repository:
https://github.com/nationalarchives/pronom

DROID:
https://www.nationalarchives.gov.uk/information-management/manage-information/preserving-digital-records/droid/
```

PRONOM also supports individual XML retrieval by appending `.xml` to a format page, for example:

```text
https://pronom.nationalarchives.gov.uk/fmt/1.xml
```

## What this project acquires

Current `sources.qnl.json` configuration:

```json
{
  "id": "pronom_registry",
  "type": "pronom_registry",
  "retrieval_mode": "github_archive",
  "archive_url": "https://github.com/nationalarchives/pronom/archive/refs/heads/develop.zip",
  "include_paths": ["signatures/fmt/", "signatures/x-fmt/"]
}
```

So the normal project acquisition is the GitHub archive, not a screen scrape of the PRONOM website.

## Authority role

PRONOM may verify:

```text
PUID: fmt/... or x-fmt/...
```

A PUID found in NARA, LOC, Wikidata, a local spreadsheet or another source is not automatically authority-verified merely because the string looks correct.

## What PRONOM contributes

Depending on the upstream record and adapter extraction, PRONOM contributes information such as:

- format name/version;
- PUID;
- extensions/signatures/identification metadata;
- related technical metadata retained from the source;
- source provenance/snapshot hash.

PRONOM is primarily identity/format-identification evidence in the governed risk architecture. The Risk Manager must not invent a PRONOM overall preservation-risk rating when PRONOM did not supply one.

## Adapter/configuration

```text
source id:   pronom_registry
source type: pronom_registry
config:      qnl_format_registry_builder/config/sources.qnl.json
```

Deep implementation/reference material remains in:

```text
qnl_format_registry_builder/docs/ADAPTER_REFERENCE.md
qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md
```

## Refresh

```powershell
cd qnl_format_registry_builder
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source pronom_registry `
  --workdir work `
  --out output `
  --report monitoring\pronom-refresh.json
```

The selected-source refresh reacquires PRONOM while reusing current evidence from sources not refreshed in the same run.

## What to review after refresh

Check:

- snapshot URI and SHA-256;
- source status and record count;
- identifier/canonical reconciliation changes;
- new/removed PUIDs;
- collision/review warnings;
- change-detection summary.

A PRONOM change can legitimately affect canonical identity reconciliation, so review identity/collision effects rather than only source-record totals.

## Offline replay

After a snapshot has been cached:

```powershell
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source pronom_registry `
  --workdir work `
  --out output `
  --offline
```

Offline mode cannot discover newer upstream PRONOM data.

## Related documentation

- [`../HOW_TO_ADD_A_SOURCE.md`](../HOW_TO_ADD_A_SOURCE.md)
- [`../../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md`](../../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md)
- [`../../qnl_format_registry_builder/docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md`](../../qnl_format_registry_builder/docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md)
