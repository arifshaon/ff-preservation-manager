# Method Coverage Notes

Method coverage is not expected to jump solely from fixing the QNL format-name mapping. The method-profile matcher uses several fields:

- `preferred_name`
- `category`
- `description`
- `identifiers.extension`
- `identifiers.mime`

The QNL workbook import must therefore map not only the format name and extensions, but also category, MIME type, and description fields.

## QNL field-map requirements

The QNL workbook source should declare at least:

```json
{
  "field_map": {
    "name": ["Digital file"],
    "source_id": ["QNL Format ID"],
    "extensions": ["File Extension(s)"],
    "mime_types": ["MIME", "MIME Type"],
    "category": ["Category/Plan", "Category", "Format Category", "Plan"],
    "description": ["Description and Justification", "Description/Justification", "Description", "Justification"]
  }
}
```

Multiple candidate headers are allowed for a single field. Extraction fails loudly only when none of the candidates is found.

## Interpretation

Low method coverage should be interpreted as a classification/mapping gap, not necessarily a preservation-policy gap. Before adding new method profiles, first check whether source fields needed by existing matching rules are actually being imported.

## Next diagnostics

After running against the real workbook, inspect:

- total canonical records;
- records with assigned method profiles;
- records with category populated;
- records with description populated;
- records with MIME type populated;
- top unmatched categories/extensions.

This will show whether to add more method profiles or improve source mapping further.
