# Documentation map

This project has three audiences:

1. **Operators** who run the registry build.
2. **Administrators** who stage source files, set release modes, and choose storage.
3. **Developers** who add new source, storage, or export adapters.

Use this map to avoid reading every document in the repository.

## Start here

| Need | Read |
| --- | --- |
| Understand the project goal and run the pipeline | `README.md` |
| Understand the end-to-end architecture | `docs/ARCHITECTURE.md` |
| Choose online, cached, offline, pinned, latest, or local-file retrieval | `docs/SOURCE_RETRIEVAL_AND_FALLBACKS.md` |
| Add a new source adapter | `docs/ADAPTER_IMPLEMENTATION_GUIDE.md` |
| Configure an existing adapter | `docs/ADAPTER_REFERENCE.md` |
| Understand NARA release modes and local admin files | `docs/NARA_LOCAL_FILES.md` and `docs/NARA_ADAPTER_REQUIREMENTS.md` |
| Choose MongoDB, file, or memory storage | `docs/STORAGE_AND_EXPORT_CONFIG.md` |
| Understand MongoDB collections, fields, indexes, and verification queries | `docs/MONGODB_STORAGE_SCHEMA.md` |
| Understand institutional policy overlays such as QNL | `docs/INSTITUTIONAL_OVERLAYS.md` |
| Understand preservation method profiles | `docs/PRESERVATION_METHOD_PROFILES.md` |
| Understand implementation decisions and constraints | `docs/DECISIONS.md` |

## How the documents fit together

```text
README.md
  -> quick start, operator path, storage/retrieval overview

ARCHITECTURE.md
  -> design model and data flow

SOURCE_RETRIEVAL_AND_FALLBACKS.md
  -> acquisition modes, cache, offline, local files, required/optional sources

ADAPTER_IMPLEMENTATION_GUIDE.md
  -> how to build a new adapter

ADAPTER_REFERENCE.md
  -> existing adapter types and config examples

NARA_ADAPTER_REQUIREMENTS.md / NARA_LOCAL_FILES.md
  -> detailed NARA-specific behavior

STORAGE_AND_EXPORT_CONFIG.md
  -> storage backends and optional exports

MONGODB_STORAGE_SCHEMA.md
  -> MongoDB implementation details, collections, fields, indexes, and example queries
```

## Naming rules

Use source-level names for adapters wherever possible:

```text
nara_digital_preservation_framework
pronom_registry
loc_fdd_xml
institution_policy_xlsx
```

Avoid naming a new adapter after a temporary file representation unless that representation is truly the source boundary. For example, CSV is only NARA's current publication format, so the preferred adapter is `nara_digital_preservation_framework`, not `nara_csv`.

Compatibility aliases can remain for old names, but new configuration should use the source-level name.

## Implementation flow for a new source

1. Read `ADAPTER_IMPLEMENTATION_GUIDE.md`.
2. Copy the small source-adapter skeleton.
3. Add the adapter class under `registry_builder/adapters/` or ship it as an external package loaded with `module:ClassName`.
4. Add an example source block to `config/sources.example.json` if it is generally useful.
5. Add tests under `tests/`.
6. Document the adapter in `ADAPTER_REFERENCE.md`.

## Documentation standard for each adapter

Each adapter section should answer the same questions:

- What source does it represent?
- When should it be used?
- What config fields does it accept?
- How does acquisition work?
- Does it support online, offline, cache, local files, pinned/latest release modes, or fallback files?
- What does it emit into `RawFormatRecord`?
- Which identifiers are verified by this adapter?
- What can fail, and whether it should be `required:true` or `required:false`?
- Which tests prove the adapter works?
