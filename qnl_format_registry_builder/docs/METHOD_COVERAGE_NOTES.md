# Method Coverage Notes

Method-profile coverage depends on both source mapping and assignment-rule design.

A useful lesson from the QNL workbook run: fixing the format-name field and mapping category/description/MIME correctly did **not** dramatically raise coverage by itself. The reason was not the adapter. The assignment rules were mostly extension-led: almost all rules matched `identifiers.extension`, and only a small number consulted names or categories.

That means the system needs two complementary matching layers:

1. **Extension rules** for common, high-confidence cases.
2. **Category fallback rules** for long-term scalability.

Extension lists are useful but will always lag a growing registry. Categories and descriptions provide a safer fallback when a format is ordinary but not yet enumerated in a profile rule.

## Institutional field-map requirements

The QNL workbook source should declare at least:

```json
{
  "field_map": {
    "institution_format_id": ["QNL Format ID"],
    "name": ["Digital file"],
    "extensions": ["File Extension(s)"],
    "mime_types": ["MIME type(s)", "MIME", "MIME Type"],
    "category": ["Category/Plan(s)", "Category/Plan", "Category", "Format Category", "Plan"],
    "description": ["Description and Justification", "Description/Justification", "Description", "Justification"],
    "preferred_tools": ["QNL Preferred Processing and Conversion Tool(s)", "Preferred Processing and Conversion Tool(s)"],
    "proposed_preservation_plan": ["QNL Proposed Preservation Plan", "Proposed Preservation Plan"]
  }
}
```

Multiple candidate headers are allowed for a single field. Extraction fails loudly only when none of the candidates is found. Missing configured fields are reported together so the user can correct the configuration in one pass.

## Assignment-rule improvements

The method profile config should include both explicit extensions and category fallbacks.

Examples of missing ordinary extensions that should be covered:

```text
csv, json, md, log, dtd, xsd, docm, dotx, dotm, mol, cif, fasta
```

Recommended mappings:

```text
csv/json/tsv/yaml        → structured_data
dtd/xsd/rdf              → xml_based_structured_text
md/log/txt               → structured_text
docm/dotx/dotm           → office_document
mol/cif/sdf/pdb          → chemistry_scientific_data
fasta/fastq              → scientific_data
```

Recommended fallback categories:

```text
Structured Data                  → structured_data
Textual and Word Processing      → structured_text and/or office_document
Scientific Data                  → scientific_data
Geospatial / GIS                 → geospatial_data
Raster Image / Still Image       → raster_image
Audio / Video / Audiovisual      → audiovisual
Archive / Container / Compressed → archive_or_container
```

## Interpretation

Low method coverage should be interpreted as a classification/mapping/rule gap, not necessarily a preservation-policy gap.

Before adding highly specific method profiles, check:

- whether source fields needed by existing matching rules are actually imported;
- whether common extensions are missing from existing profiles;
- whether category-based fallback rules are available;
- whether the unmatched formats truly need new profiles or only better assignment rules.

## Next diagnostics

After running against the real workbook, inspect:

- total canonical records;
- records with assigned method profiles;
- records with category populated;
- records with description populated;
- records with MIME type populated;
- top unmatched categories/extensions;
- formats that matched only by category fallback.

This will show whether to add more method profiles or improve source mapping further.
