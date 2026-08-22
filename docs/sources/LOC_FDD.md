# Library of Congress Format Description Documents (FDD)

## What it is

The Library of Congress Sustainability of Digital Formats site publishes Format Description Documents (FDDs) and sustainability information for digital formats.

Official source information:

```text
FDD XML information:
https://www.loc.gov/preservation/digital/formats/fdd/fdd_xml_info.shtml

Current XML ZIP used by the project:
https://www.loc.gov/preservation/digital/formats/fddXML.zip

Individual XML pattern:
https://www.loc.gov/preservation/digital/formats/fddXML/fddnnnnnn.xml
```

LOC states that a fresh group ZIP is produced after additions to the site.

## What this project acquires

Current `sources.qnl.json` entry:

```json
{
  "id": "loc_fdd_xml",
  "type": "loc_fdd_xml_reviewed",
  "retrieval_mode": "fdd_xml_zip",
  "zip_uri": "https://www.loc.gov/preservation/digital/formats/fddXML.zip"
}
```

## Authority role

LOC FDD XML is authoritative for the LOC FDD identifier namespace.

Example:

```text
fdd000030
```

PUIDs/QIDs mentioned inside LOC prose or crosswalks are retained as cross-source evidence but do not become authority-verified PUID/QID claims merely because LOC copied them.

## What LOC contributes

The reviewed LOC integration contributes:

- FDD identity/name/version/context;
- source-native sustainability-factor evidence;
- approved normalized criterion claims where mappings have been reviewed;
- provenance and source locators;
- reviewed cross-registry relationship evidence where applicable.

The approved sustainability-factor mapping covers LOC's preservation-relevant factors such as disclosure, adoption, transparency/readability, self-documentation, external dependencies, patents/licensing and technical protection mechanisms.

LOC evidence can inform the Risk Manager's framework questions. It must not be turned into a fabricated LOC overall preservation-risk rating when LOC has not supplied one.

## Reviewed FDD–PUID–QID crosswalk

LOC also publishes a mapping page/crosswalk:

```text
Mapping page:
https://www.loc.gov/preservation/digital/formats/fdd/fdd_puid_qid.shtml

Current reviewed/pinned CSV in this repository:
https://www.loc.gov/preservation/digital/formats/mappings/fdd-puid-qid-20260713.csv
```

The current reviewed mapping date is `20260713`.

These links are not assumed to be exact identity equivalences. FDD, PRONOM and Wikidata may represent different hierarchy/granularity levels. The crosswalk is therefore evidence-first and only approved exact-equivalence rules may influence reconciliation.

## Adapter/configuration

```text
source id:   loc_fdd_xml
source type: loc_fdd_xml_reviewed
config:      qnl_format_registry_builder/config/sources.qnl.json
```

Relevant reviewed mapping configuration is under:

```text
qnl_format_registry_builder/config/criterion_mappings/
```

Deep references:

```text
qnl_format_registry_builder/docs/LOC_FDD_SUSTAINABILITY.md
qnl_format_registry_builder/docs/LOC_FDD_CROSSWALK_SOURCE.md
```

## Refresh the FDD XML source

```powershell
cd qnl_format_registry_builder
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source loc_fdd_xml `
  --workdir work `
  --out output `
  --report monitoring\loc-refresh.json
```

## What to review after refresh

Check:

- ZIP snapshot hash/change status;
- FDD additions/removals/changes;
- canonical/reconciliation effects;
- criterion-claim counts and mapping versions;
- previously unknown native factor values;
- change detection;
- whether a crosswalk review/update is separately required.

A newly changed LOC native value should remain visible even when it does not map to a governed criterion yet. Do not create a weak mapping only to increase coverage.

## Crosswalk review acquisition

The repository has a dedicated review downloader for the LOC FDD–PUID–QID CSV. See:

[`../../qnl_format_registry_builder/docs/LOC_FDD_CROSSWALK_SOURCE.md`](../../qnl_format_registry_builder/docs/LOC_FDD_CROSSWALK_SOURCE.md)

Crosswalk changes should be reviewed separately from the core FDD XML refresh because they can affect cross-registry relationships/identity decisions.

## Related documentation

- [`../HOW_TO_ADD_A_SOURCE.md`](../HOW_TO_ADD_A_SOURCE.md)
- [`../../qnl_format_registry_builder/docs/LOC_FDD_SUSTAINABILITY.md`](../../qnl_format_registry_builder/docs/LOC_FDD_SUSTAINABILITY.md)
- [`../../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md`](../../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md)
