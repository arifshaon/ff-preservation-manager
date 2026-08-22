# NARA Digital Preservation Framework

## What it is

The U.S. National Archives and Records Administration (NARA) publishes a Digital Preservation Framework containing a Risk Matrix and preservation action plans.

Official repository:

```text
https://github.com/usnationalarchives/digital-preservation
```

The repository documents the framework, release history and machine-readable spreadsheets/CSVs.

## Current reviewed release

The production configuration is currently pinned to:

```text
release date: 20260320
release:      NARA Digital Preservation Framework 3.6.0
```

The adapter's current primary raw CSV locations are:

```text
Preservation Action Plan:
https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Plan_Spreadsheet/NARA_PreservationActionPlan_FileFormats_20260320.csv

Numbered Risk Matrix:
https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Risk_Matrix/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv
```

NARA's release changelog is available at:

```text
https://github.com/usnationalarchives/digital-preservation/blob/master/CHANGELOG.md
```

## Current project configuration

```json
{
  "id": "nara_digital_preservation_framework",
  "type": "nara_digital_preservation_framework",
  "retrieval_mode": "published_csv",
  "release_mode": "pinned",
  "release_date": "20260320",
  "fallback_release_date": "20260320",
  "github_ref": "master"
}
```

## Authority role

NARA is authoritative for its own NARA format IDs, for example:

```text
NF00xxx
```

A PUID/LOC/Wikidata link copied into a NARA row is useful cross-reference evidence but does not replace the authority that owns that namespace.

## Risk model used by the project

The adapter preserves NARA's native numeric risk rating and its direction:

```text
native scale:     nara_file_format_risk_matrix
native direction: higher_is_safer
```

Current governed semantic mapping from the native numeric rating:

```text
rating >= 23   -> Low
rating <= -23  -> High
otherwise      -> Moderate
```

The native numeric value is retained. It is not averaged with DPC or another source's scale.

NARA overall risk assessments are exact-format evidence when their reconciled target is an exact format/version.

## What NARA contributes

- authoritative NARA identity;
- source-native Risk Matrix fields;
- native numeric risk rating and NARA risk label;
- preservation action-plan fields;
- technical/source URLs and supporting native fields;
- reviewed source-level risk claims;
- reviewed criterion evidence where mappings have been approved.

## Refresh the current pinned release

```powershell
cd qnl_format_registry_builder
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source nara_digital_preservation_framework `
  --workdir work `
  --out output `
  --report monitoring\nara-refresh.json
```

Because the production configuration is pinned, this does **not** silently adopt a future NARA release.

## Adopting a new NARA release

Recommended process:

```text
1. Check NARA repository/changelog for a complete new release.
2. Acquire/review it in monitoring/review mode.
3. Compare source counts, IDs, risk changes and schema changes.
4. Review any new native values/mapping implications.
5. Update the production `release_date` deliberately.
6. Run source refresh.
7. Review change detection and risk-claim materialization.
8. Run the Risk Manager watchlist/report.
```

Do not simply switch production to `latest` without review if a pinned/reproducible baseline is required.

## Follow-latest monitoring

The NARA adapter supports a `release_mode` that can be used by a separate monitoring configuration to discover a newer complete release. Keep discovery and production adoption as separate governance decisions.

## What to review after a NARA change

Check:

- new/removed NARA IDs;
- changed format names/links;
- changed native numeric risk values;
- changed NARA risk levels;
- schema/column changes;
- preservation-action changes;
- canonical reconciliation effects;
- governed risk-claim materialization;
- criterion-mapping effects;
- change-detection output.

Several canonicals can legitimately have multiple NARA assessments/records. Preserve real same-scope conflicts rather than collapsing them by averaging.

## Deep references

- [`../../qnl_format_registry_builder/docs/NARA_ADAPTER_REQUIREMENTS.md`](../../qnl_format_registry_builder/docs/NARA_ADAPTER_REQUIREMENTS.md)
- [`../../qnl_format_registry_builder/docs/RISK_ASSESSMENTS.md`](../../qnl_format_registry_builder/docs/RISK_ASSESSMENTS.md)
- [`../../qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md`](../../qnl_format_registry_builder/docs/INCREMENTAL_SOURCE_UPDATES.md)
