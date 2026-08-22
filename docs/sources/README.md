# Integrated data sources

This directory documents the sources currently used by the registry and how each one is governed.

## Source matrix

| Source | Project source ID | Primary role | Upstream location | Update model |
| --- | --- | --- | --- | --- |
| PRONOM | `pronom_registry` | Authoritative PUID identity and format/signature data | `https://github.com/nationalarchives/pronom` | Online archive refresh; current config follows `develop` archive. |
| Library of Congress FDD | `loc_fdd_xml` | Authoritative LOC FDD identity + reviewed sustainability evidence | `https://www.loc.gov/preservation/digital/formats/fddXML.zip` | XML ZIP refresh + reviewed mappings/crosswalk. |
| NARA Digital Preservation Framework | `nara_digital_preservation_framework` | Authoritative NARA IDs + source-native risk/action evidence | `https://github.com/usnationalarchives/digital-preservation` | Current production config pinned to `20260320`; deliberate release update. |
| DPC Global Bit List 2025 | `dpc_bit_list_2025` | Preservation-risk/context evidence only | `https://github.com/Digital-Preservation-Coalition/bit-list` | 2025 edition pinned to reviewed commit. |
| Wikidata | `wikidata_file_formats` controlled workflow | Contextual relationships/cross-references only | `https://query.wikidata.org/sparql` | Guarded preflight/apply refresh, not an uncontrolled full crawl. |
| QNL institutional evidence/policy | `qnl_policy_current` and local evidence workflows | Institution-specific policy/readiness/evidence | local reviewed files | Explicit local update/review; never universalized automatically. |

## Authority rules

The registry does not treat every identifier string as equally authoritative.

```text
PRONOM owns PUIDs
LOC owns LOC FDD IDs
NARA owns NARA IDs
Wikidata owns QIDs, not copied PUID/LOC/NARA identifiers
DPC contributes risk/context, not canonical identity
QNL/local evidence is institution-scoped unless explicitly modeled otherwise
```

A PUID copied into another source can be useful linking evidence, but it is not automatically promoted to a verified PUID claim.

## Detailed guides

- [`PRONOM.md`](PRONOM.md)
- [`LOC_FDD.md`](LOC_FDD.md)
- [`NARA.md`](NARA.md)
- [`DPC_BIT_LIST.md`](DPC_BIT_LIST.md)
- [`WIKIDATA.md`](WIKIDATA.md)
- [`QNL_LOCAL.md`](QNL_LOCAL.md)

Each guide answers the same operational questions:

1. What is the source?
2. Where exactly is it acquired from?
3. What does this project use it for?
4. What does it **not** use it for?
5. Which adapter/config is responsible?
6. How is it refreshed?
7. Which mappings/projections require review?
8. How can an operator verify provenance?

## Refreshing normal configured sources

Example:

```powershell
cd qnl_format_registry_builder
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source pronom_registry `
  --workdir work `
  --out output `
  --report monitoring\pronom-refresh.json
```

Repeat `--source` for several sources.

Wikidata is the exception: use its controlled refresh workflow documented in [`WIKIDATA.md`](WIKIDATA.md).

## Adding another source

Follow [`../HOW_TO_ADD_A_SOURCE.md`](../HOW_TO_ADD_A_SOURCE.md). A source is not considered integrated merely because a downloader exists; identity authority, evidence scope, mapping semantics, update behavior and provenance must all be documented and tested.
