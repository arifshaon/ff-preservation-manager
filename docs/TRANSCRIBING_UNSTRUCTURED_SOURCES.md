# Transcribing unstructured and narrative preservation sources

Use this guide when a useful preservation source is published primarily as prose rather than as a stable machine-readable feed.

Examples include:

```text
PDF guidance/publications
narrative web pages
scanned or OCR'd tables/reports
catalogues with prose entries
standards summaries
risk/watch lists published as human-readable documents
```

The DPC Bit List is the main worked example for this pattern.

## Core principle

**Transcription produces a first-class evidence artifact.**

Do not make a production risk calculation depend on an opaque one-time LLM conversation or manual copy/paste session.

Instead:

```text
unstructured publication
        |
        v
manual or AI-assisted transcription
        |
        v
versioned JSON draft
        |
        v
human review
        |
        v
reviewed JSON source artifact
        |
        v
normal registry-builder adapter pipeline
```

The reviewed JSON is diffable, reviewable, repeatable, and can be reprocessed without invoking an AI model again.

## What transcription is — and is not

Transcription should capture **what the source says**.

It may normalize representation, for example:

```text
".SWF" -> ["swf"]
"Practically Extinct" -> native_fields.endangerment_category
```

but it should not silently convert a narrative source into QNL's final preservation policy or deterministic risk band.

Keep these stages separate:

```text
transcription       = source-native structured evidence
criterion mapping   = source-native evidence -> neutral criterion
risk framework      = neutral criterion -> controlled assessment answer
policy/action       = institutional decision
```

## Manual and AI-assisted paths are equivalent at the review gate

Both are supported:

### Manual

```text
human reads source
 -> drafts JSON
 -> second-person/reviewer checks source locators and values
 -> approve artifact
```

### AI-assisted

```text
AI reads supplied source
 -> drafts JSON
 -> human checks every record against source
 -> correct/approve artifact
```

An AI-assisted draft must not be marked reviewed simply because the JSON validates syntactically.

## Required review rule

A transcription should not be used as approved production evidence until it has:

```text
review_status = reviewed
reviewed_by   = named human/team
reviewed_at   = date/time
```

A draft may use:

```text
review_status = draft
reviewed_by   = null
reviewed_at   = null
```

The exact review process is institutional policy, but the artifact must preserve the decision explicitly.

## Provenance rule for every record

Unlike an API record, a narrative observation cannot always be re-queried by ID. Every transcribed record therefore needs a locator back to the source passage.

Use one or more of:

```text
source_page
source_section
source_heading
source_anchor
source_url
source_excerpt
```

For PDF publications, page number is strongly recommended.

For HTML, keep the URL and a section/heading/anchor where possible.

A short `source_excerpt` can help review, but only retain text consistent with copyright/licensing requirements.

## Recommended artifact shape

The committed schema is:

```text
qnl_format_registry_builder/config/schemas/unstructured_source_transcription.v1.schema.json
```

Example:

```json
{
  "schema_version": "unstructured_source_transcription/v1",
  "source_id": "dpc_bit_list",
  "source_edition": "2026",
  "transcribed_from": "https://example.org/source",
  "source_media_type": "application/pdf",
  "transcription_method": "ai_assisted",
  "transcribed_by": "llm",
  "model_id": "example-model",
  "prompt_version": "dpc_bit_list_transcription/v1",
  "transcribed_at": "2026-08-20T10:00:00Z",
  "review_status": "reviewed",
  "reviewed_by": "QNL Digital Curation, Preservation, and Access",
  "reviewed_at": "2026-08-21T10:00:00Z",
  "records": [
    {
      "source_record_id": "dpc-2026-example-format",
      "name": "Example Format",
      "extensions": ["ext"],
      "identifiers": {},
      "native_fields": {
        "endangerment_category": "Example native category",
        "trend": "worsening",
        "rationale": "Source-native summary of the stated rationale."
      },
      "source_page": 14,
      "source_section": "Example section",
      "source_url": "https://example.org/source",
      "source_excerpt": "Short review locator excerpt where permitted."
    }
  ]
}
```

The values above are illustrative; do not treat them as DPC facts.

## Why source-native fields matter

A transcription should preserve the publication's own vocabulary before attempting neutral criterion mapping.

Good:

```json
"native_fields": {
  "endangerment_category": "Practically Extinct",
  "trend": "worsening"
}
```

Avoid prematurely writing:

```json
"sustainability.adoption": "low"
```

unless that is actually the source's native field/value.

The mapping layer exists specifically to make that translation visible and reviewable.

## Using `standard_json`

The built-in `standard_json` adapter accepts a package with a top-level `records` array.

For a reviewed transcription file:

```json
{
  "id": "dpc_bit_list",
  "type": "standard_json",
  "enabled": true,
  "required": false,
  "uris": ["sources/dpc_bitlist/2026-08.reviewed.json"]
}
```

`standard_json` reads identity fields such as name/extensions/identifiers and retains the full record in `RawFormatRecord.raw`.

Therefore source-native transcription values inside the record remain available under the stored raw payload. A mapping may use paths such as:

```text
raw.native_fields.endangerment_category
raw.native_fields.trend
```

when using `standard_json` directly.

For long-term source-specific operation, a thin `DpcBitListAdapter` may instead promote these values into `RawFormatRecord.native_fields`, support automatic acquisition, and enforce DPC-specific validation. In that case mappings can use:

```text
native_fields.endangerment_category
native_fields.trend
```

Do not guess which path exists: run the criterion-evidence audit and map the actual stored field path.

## When to use a thin source-specific adapter

Prefer a dedicated adapter if you need any of the following:

- automatic fetching of the publication/edition;
- source-version discovery;
- stable source record IDs derived from source structure;
- source-specific identifier normalization;
- promotion of native fields out of `raw`;
- structured preservation of page/section references;
- source-specific validation rules;
- automatic comparison between editions.

A dedicated adapter should still consume the reviewed structured artifact if AI/manual transcription is required. Do not hide transcription inside `extract()` without retaining the intermediate result.

## File naming/versioning

Use an edition/date-oriented path such as:

```text
sources/dpc_bitlist/
  2026-08.draft.json
  2026-08.reviewed.json
```

or another controlled location outside generated `output/` directories.

The reviewed artifact should be immutable for that edition. Corrections should create a new revision with review metadata rather than silently rewriting history.

## AI transcription workflow

Reusable generic prompt:

```text
qnl_format_registry_builder/config/prompts/transcribe_unstructured_source/v1.0.md
```

DPC-specific prompt:

```text
qnl_format_registry_builder/config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md
```

Give the AI agent:

```text
1. the exact source PDF/HTML/export;
2. the transcription JSON schema;
3. the transcription prompt;
4. any source-specific field guidance;
5. optionally a previously reviewed transcription example.
```

The model should return JSON only.

## What the AI must not do during transcription

It must not:

- invent records absent from the source;
- invent PUIDs/MIME types/extensions;
- infer a risk criterion where the source only gives prose;
- rewrite DPC/native categories into QNL categories;
- fabricate page/section locators;
- mark itself as the human reviewer;
- collapse uncertainty into a definitive field value;
- use outside web knowledge unless the transcription task explicitly permits it.

If information is absent, return null/empty values or a review note according to the schema/prompt.

## DPC Bit List worked workflow

```text
A. Save/acquire the selected DPC edition
B. Record source URL/edition/date
C. Provide PDF/HTML + schema + DPC transcription prompt to AI (or transcribe manually)
D. Save draft JSON
E. Validate shape and inspect every source locator
F. Human-review all records against the publication
G. Save reviewed JSON
H. Ingest with standard_json or DpcBitListAdapter
I. Audit actual fields in registry storage
J. Draft source-to-criterion mapping
K. Human-review/approve the mapping
L. Generate criterion_claims
M. Verify evidence via preservation_risk_manager
```

Two AI operations can be used, but they are different artifacts:

```text
AI transcription draft
  source prose -> source-native JSON

AI mapping draft
  reviewed source-native JSON -> proposed criterion-mapping JSON
```

Neither is self-approving.

## Mapping DPC endangerment categories

Treat composite DPC endangerment/status labels cautiously.

A source label such as an endangerment category may be valuable evidence, but it is already a source-level conclusion. The current mapping validator intentionally prevents several kinds of composite risk/hazard conclusions from being smuggled into primitive neutral criteria.

Options are:

1. retain the DPC endangerment label as source-native evidence/hazard context;
2. map underlying narrative observations to existing neutral criteria where semantics support it;
3. add a new explicit criterion for an external source hazard classification only if the vocabulary/framework governance process decides that is appropriate;
4. leave it unmapped and record a vocabulary-extension proposal.

Do not map it to `sustainability.adoption`, for example, merely because highly endangered formats are often less adopted.

## Institution-level narrative sources

The same transcription approach can be used for internal QNL narrative material.

If the source observation is local, preserve:

```text
institution_id = qnl
source_independence = institution_scoped
```

A local statement about QNL tooling, staff expertise, migration tests, or storage constraints must not become a global claim.

## Validation checklist

Before ingestion:

- [ ] source edition/location captured;
- [ ] each record has stable `source_record_id`;
- [ ] each record has page/section/URL provenance;
- [ ] extensions/identifiers are source-supported, not inferred from model knowledge;
- [ ] source-native vocabulary is preserved;
- [ ] draft/review status is explicit;
- [ ] named human review completed for production use;
- [ ] JSON matches the transcription schema;
- [ ] no risk-framework answers were invented during transcription.

After ingestion:

- [ ] source records are visible;
- [ ] expected raw/native fields are visible in audit output;
- [ ] identifier claims have correct verification status;
- [ ] mapping JSON uses actual field paths;
- [ ] criterion claims retain source provenance;
- [ ] risk manager can consume the intended evidence.

## Related documentation

- Source onboarding router: [`HOW_TO_ADD_A_SOURCE.md`](HOW_TO_ADD_A_SOURCE.md)
- Data model: [`DATA_MODEL.md`](DATA_MODEL.md)
- Adapter/source implementation: [`../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md)
- Criterion mapping: [`../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)
