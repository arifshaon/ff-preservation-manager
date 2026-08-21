# DPC Global Bit List source

## Role

The DPC Global Bit List is a **preservation-risk evidence source**, not a file-format identity authority.

The source can describe exact formats, format families/groups, content types, systems, services, or broader preservation contexts. Therefore a Bit List entry must not automatically become a canonical file-format record.

## Primary acquisition source

The primary machine-readable source is the public DPC Bit List GitHub repository:

```text
https://github.com/Digital-Preservation-Coalition/bit-list
```

The repository's `content/entries/*/index.en.md` files contain YAML front matter plus review prose. The adapter snapshots one repository archive rather than scraping the rendered website or parsing the PDF.

For the 2025 edition, acquisition is pinned to:

```text
3ad3fef626ea7c128ef8c323d92227e5cae2efc8
```

This is the final observed 2025 repository commit and prevents a future change to `main` from silently changing a rerun labelled `edition: 2025`.

## Adapter

```text
registry_builder.adapters.dpc_bit_list.DpcBitListAdapter
source type: dpc_bit_list
```

Default configuration:

```json
{
  "id": "dpc_bit_list_2025",
  "type": "dpc_bit_list",
  "enabled": true,
  "required": false,
  "edition": "2025",
  "github_ref": "3ad3fef626ea7c128ef8c323d92227e5cae2efc8"
}
```

The adapter emits source records with:

```text
record_role = evidence_only
```

`evidence_only` records are persisted for audit, criterion mapping and risk mapping, but the reconciler excludes them from canonical identity formation. This prevents broad entries such as `Legacy Video Files`, `Native Cloud Formats`, `Email`, or `PDF` as a whole from becoming canonical formats.

## Review extraction command

Use the companion command to acquire the archive and create structured JSON and CSV review datasets:

```powershell
python -m registry_builder.dpc_bit_list_download `
  --out dpc-bit-list-2025.json `
  --workdir work
```

The command uses the pinned 2025 commit unless `--github-ref` is explicitly supplied.

It writes:

```text
dpc-bit-list-2025.json
dpc-bit-list-2025.csv
```

and prints a JSON summary containing the immutable snapshot path/hash, entry count, classification counts, and coarse source scope counts.

## Extracted fields

For each English Bit List entry, the review dataset retains source-native fields including:

```text
source_record_id
slug
title
description
examples
categories
threats
classification
imminence
effort
trends
hazards
mitigations
year_added
published
last_updated
aliases
comments
case_studies
review_body
source_url
source_file
snapshot_sha256
edition
raw_front_matter
```

A normalized `risk_assessment` object preserves the DPC classification as `native_label` and records the DPC scale as:

```text
dpc_global_bit_list_classification
```

The shared semantic level is a separate, transparent projection:

```text
Lower Risk            -> minimal
Vulnerable            -> moderate
Endangered            -> high
Critically Endangered -> critical
Practically Extinct   -> critical
```

Native DPC values remain preserved regardless of the semantic projection.

## Scope

Before reviewed mapping, DPC entry scope is deliberately coarse:

```text
category includes Formats -> format_group
otherwise                 -> contextual
```

A reviewed mapping may assign:

```text
exact_format
format_version
format_family
format_group
content_type
contextual
```

The mapping also records its rule ID, mapping version and scope basis.

## Reviewed mapping v1

The reviewed mapping file is:

```text
config/external_risk_mappings/dpc_bit_list_2025.v1.approved.json
```

Version 1 approves only the DPC `PDF` entry for automatic attachment. The DPC assessment remains a `format_group` assessment because DPC explicitly treats PDF versions and variants together.

These entries remain contextual-only in v1:

```text
Native Cloud Formats
Legacy Video Files
Email
```

They are intentionally not projected to individual canonical formats because their DPC scope spans platforms, carriers, services, containers/codecs, messages, mailboxes and other broader conditions.

## Read-only persistent-registry preview

Before any DPC assessment is persisted onto canonical records, preview the approved mapping against the current registry in MongoDB:

```powershell
python -m registry_builder.dpc_risk_mapping_mongo `
  --config config/sources.qnl.dpc-only.json `
  --out out/dpc-risk-mapping-preview.json
```

This command:

- loads the current canonical registry view from the configured storage backend;
- selects only the latest completed `dpc_bit_list_2025` source run;
- applies the reviewed mapping in memory;
- reports the exact target canonical IDs, names and identifiers;
- reports the mapped source-native assessment and the projected synthesized-risk view;
- performs **no storage writes** and **no identity projection**.

The preview report records:

```text
mode = read_only_store_preview
storage_write = false
identity_projection = false
```

This is the required review gate before production persistence of DPC risk assessments.

## File-export mapping preview

The older file-based preview remains useful for detached review datasets:

```powershell
python -m registry_builder.dpc_risk_mapping `
  --registry out/registry.json `
  --dpc-json dpc-bit-list-2025.json
```

The command prints the exact canonical IDs and preferred names matched by each approved rule. It does not modify the registry unless `--out` is supplied.

To write an enriched review copy:

```powershell
python -m registry_builder.dpc_risk_mapping `
  --registry out/registry.json `
  --dpc-json dpc-bit-list-2025.json `
  --out out/registry-with-dpc-risk.json
```

## Relationship to NARA and LOC

DPC does not replace either source:

- NARA can provide an explicit format-risk assessment on its own native scale.
- DPC provides a separate community/expert Bit List classification with imminence, preservation effort, hazards, mitigations, and trends.
- LOC provides sustainability-factor evidence and should not be assigned an overall risk classification unless a separate approved derivation is explicitly defined.

All source-native assessments remain independently queryable. A synthesized semantic risk is an optional decision-support view and always retains its contributing sources and declared scopes.

## PowerShell UTF-8 display

The JSON review dataset is UTF-8. Windows PowerShell can display typographic punctuation as mojibake when `Get-Content` uses a legacy default encoding. Use:

```powershell
Get-Content dpc-bit-list-2025.json -Raw -Encoding UTF8
```

This is a display issue, not source-data corruption.
