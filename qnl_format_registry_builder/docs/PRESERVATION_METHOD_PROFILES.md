# Preservation Method Profiles

The registry builder must not maintain one bespoke preservation method for every file format. That does not scale across QNL policy formats, NARA-covered formats, PRONOM formats and future formats discovered in QNL holdings.

Instead, the system assigns reusable preservation method profiles.

## Principle

A format receives:

```text
Generic preservation baseline
+ format-family profile
+ optional domain modifier
+ optional format-specific override
```

The resulting method is generated from templates and stored as part of the current registry view. It is not an approved QNL policy decision by itself.

## Why this matters

A format such as Chemical Markup Language (CML) should not have a full custom method written only for CML. It should inherit from reusable profiles:

```text
generic_preservation
structured_text
xml_based_structured_text
scientific_data
chemistry_scientific_data
```

The chemistry profile adds domain-specific metadata extraction and derivative guidance. Only the narrow chemistry-specific warnings are overrides.

## Example: CML

CML is assigned to XML-based structured text because it is a structured XML format. It is also assigned to chemistry/scientific data because its preservation value depends on maintaining chemical semantics.

The generated method therefore includes:

- preserve the original file;
- check fixity and provenance;
- validate text readability and XML well-formedness;
- validate against schema or documented conventions where possible;
- extract namespace, schema references and embedded metadata;
- extract chemistry-specific data such as molecule identifiers, formulae, atom/bond structures, coordinates and reaction information where available;
- use chemistry-aware derivative tools for access or reuse copies where required;
- avoid treating PDF conversion as sufficient preservation for structured chemical semantics.

This is scalable because the same XML profile can also support METS, MODS, TEI, KML, JATS, XHTML and other XML-based formats, while domain modifiers handle specialist cases.

## Configuration

Method profiles are configured in:

```text
config/method_profiles.example.json
```

The main pipeline config enables the profile assignment step:

```json
{
  "method_profiles": {
    "enabled": true,
    "path": "method_profiles.example.json"
  }
}
```

## Runtime behavior

The pipeline order is:

```text
source acquisition
→ extraction
→ normalization
→ reconciliation
→ method profile assignment
→ validation
→ exports / reports
```

Profile assignment happens after reconciliation so it works against canonical format records rather than raw source rows.

## What profiles are not

Profiles are not hazard scores. They do not reduce or increase intrinsic format hazard.

Profiles are also not QNL-approved action plans. They are generated method templates that support action-plan drafting, review and readiness assessment.

## Current vocabulary

The starter configuration includes profiles for:

- `generic_preservation`
- `structured_text`
- `xml_based_structured_text`
- `scientific_data`
- `chemistry_scientific_data`
- `raster_image`
- `office_document`
- `archive_or_container`
- `geospatial_data`
- `audiovisual`

This vocabulary should grow slowly. Add a new profile only when several formats can reuse it or when a domain modifier is clearly needed.

## Design rule

Do not create a new method profile just because a new format appears.

First ask:

1. Does an existing family profile cover it?
2. Does an existing domain modifier cover it?
3. Is a small override enough?
4. Only if none of those work, create a new reusable profile.
