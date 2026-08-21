# DPC Global Bit List source

## Role

The DPC Global Bit List is a **preservation-risk evidence source**, not a file-format identity authority.

The source can describe exact formats, format families/groups, content types, systems, services, or broader preservation contexts. Therefore a Bit List entry must not automatically become a canonical file-format record.

## Primary acquisition source

The primary machine-readable source is the public DPC Bit List GitHub repository:

```text
https://github.com/Digital-Preservation-Coalition/bit-list
```

The repository's `content/entries/*/index.en.md` files contain YAML front matter plus review prose. The DPC repository README states that `content/` is the source data/content used to build the site and the generated report.

The adapter snapshots one repository archive rather than scraping the rendered website or parsing the PDF. This gives one content-addressed source snapshot and makes offline replay possible.

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
  "github_ref": "main"
}
```

The adapter is intentionally **acquisition-only** in the normal registry pipeline:

```python
extract(...) -> []
```

This prevents broad entries such as `Legacy Video Files`, `3D Digital Engineering Drawings`, or `PDF` as a whole from accidentally creating or collapsing canonical file-format identity.

## Review extraction command

Use the companion command to acquire the archive and create structured JSON and CSV review datasets:

```powershell
python -m registry_builder.dpc_bit_list_download `
  --out dpc-bit-list-2025.json `
  --workdir work
```

This writes:

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

A normalized `risk_assessment` object is also prepared for later mapping. It preserves the DPC classification as `native_label` and records the DPC scale as:

```text
dpc_global_bit_list_classification
```

The shared semantic level is a separate, transparent projection:

```text
Lower Risk            -> minimal
Vulnerable            -> moderate
Endangered             -> high
Critically Endangered -> critical
Practically Extinct   -> critical
```

Native DPC values remain preserved regardless of the semantic projection.

## Scope

Before reconciliation, DPC entry scope is deliberately coarse:

```text
category includes Formats -> format_group
otherwise                 -> contextual
```

This is not the final mapping scope. The later reviewed mapping layer may assign:

```text
exact_format
format_version
format_family
format_group
content_type
contextual
```

The mapping layer must also record its basis and review status.

## Relationship to NARA and LOC

DPC does not replace either source:

- NARA can provide an explicit format-risk assessment on its own native scale.
- DPC provides a separate community/expert Bit List classification with imminence, preservation effort, hazards, mitigations, and trends.
- LOC provides sustainability-factor evidence and should not be assigned an overall risk classification unless a separate approved derivation is explicitly defined.

All source-native assessments should remain independently queryable. A synthesized semantic risk is an optional decision-support view and must always retain its contributing sources and declared scopes.

## Next step

After the review dataset is validated, create an explicit DPC-entry-to-canonical-format/family mapping layer. Do not enable direct DPC canonical projection.
