# DPC Global Bit List of Endangered Digital Materials

## What it is

The Digital Preservation Coalition (DPC) Global Bit List is a community/expert risk resource describing categories of endangered digital materials.

Official DPC information:

```text
DPC Bit List site:
https://www.dpconline.org/digipres/champion-digital-preservation/bit-list

2025 launch information:
https://www.dpconline.org/news/dpc-launches-new-version-bit-list
```

Machine-readable project source:

```text
https://github.com/Digital-Preservation-Coalition/bit-list
```

## Current reviewed edition

```text
edition: 2025
pinned Git commit: 3ad3fef626ea7c128ef8c323d92227e5cae2efc8
```

The adapter acquires the pinned repository ZIP:

```text
https://github.com/Digital-Preservation-Coalition/bit-list/archive/3ad3fef626ea7c128ef8c323d92227e5cae2efc8.zip
```

It reads English entry files matching:

```text
content/entries/*/index.en.md
```

## Current project configuration

```json
{
  "id": "dpc_bit_list_2025",
  "type": "dpc_bit_list",
  "edition": "2025",
  "github_ref": "3ad3fef626ea7c128ef8c323d92227e5cae2efc8"
}
```

## Role in this project

DPC is **evidence only** for preservation risk/context.

It does not:

- create canonical format identities;
- verify PUIDs/LOC/NARA identifiers;
- override exact format identity;
- supply a numeric scale that can be averaged with NARA.

Each entry retains source-native classification and context such as threats, hazards, mitigations, trends and scope.

## Native terminology

DPC classifications are preserved natively and mapped through governed terminology rules for synthesis.

Current conceptual mapping includes:

```text
Lower Risk             -> minimal
Vulnerable              -> moderate
Endangered              -> high
Critically Endangered   -> critical
Practically Extinct     -> critical
```

The mapping is governed/configurable. Do not replace native labels in stored evidence.

See:

[`../../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md`](../../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md)

## Scope

DPC entries categorized as formats are normally treated as broader `format_group` evidence unless an approved mapping establishes a more specific scope. Other entries remain contextual.

This matters for synthesis. A PDF-group DPC assessment can provide meaningful warning/context without automatically overriding a more specific exact-format assessment from another source.

## Refresh the pinned 2025 source

```powershell
cd qnl_format_registry_builder
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source dpc_bit_list_2025 `
  --workdir work `
  --out output `
  --report monitoring\dpc-refresh.json
```

Because the configured Git ref is pinned, the refresh is reproducible and does not automatically move to a future edition/commit.

## Review/download DPC independently

The repository also provides a review dataset command:

```powershell
python -m registry_builder.dpc_bit_list_download `
  --out dpc-bit-list-2025.json `
  --workdir work
```

This creates review JSON/CSV without creating canonical registry records.

## Adopting a newer DPC edition

Treat a new edition as a reviewed source change:

1. inspect DPC's current publication and repository structure;
2. pin the intended commit/ref;
3. run the adapter/review dataset in isolation;
4. compare classifications, slugs, scopes and schema/front matter;
5. review terminology mapping for any new classification values;
6. review format/group linking rules;
7. update the production configuration deliberately;
8. refresh and inspect governed risk changes.

Do not map a new DPC phrase by keyword guessing.

## Deep references

- [`../../qnl_format_registry_builder/docs/DPC_BIT_LIST_SOURCE.md`](../../qnl_format_registry_builder/docs/DPC_BIT_LIST_SOURCE.md)
- [`../../qnl_format_registry_builder/docs/RISK_ASSESSMENTS.md`](../../qnl_format_registry_builder/docs/RISK_ASSESSMENTS.md)
