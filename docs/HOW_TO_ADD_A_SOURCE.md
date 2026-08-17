# How to add a new preservation evidence source

This is the **single entry point** for onboarding a new source into File Format Preservation Manager.

The goal is not merely to make a source load. A completed onboarding should allow the source to contribute traceable evidence to preservation-risk analysis.

## The seven-step path

```text
1. Decide the source boundary
2. Transcribe to a reviewed structured artifact if the source is unstructured
3. Add/configure the source adapter
4. Register the source and identifier rules
5. Map source observations to neutral criteria
6. Validate, review, and generate criterion claims
7. Test the source through preservation_risk_manager
```

If the source is already a stable CSV/JSON/XML/API feed, Step 2 is skipped.

If the source is narrative PDF/HTML, scanned guidance, prose webpages, or another unstructured publication, **do not put LLM extraction directly inside the production risk calculation**. Produce a versioned transcription artifact first.

## Step 1 — Decide the source boundary

Name and model the conceptual authority/publication, not merely its transport format.

Good:

```text
pronom_registry
loc_fdd_xml
nara_digital_preservation_framework
dpc_bit_list
```

Usually avoid:

```text
pronom_json
dpc_pdf
nara_csv
```

Ask:

- who is asserting the evidence?
- what is the source edition/release?
- how can the original evidence be reacquired or audited?
- does the source own any identifier namespace?
- is the evidence global or institution-specific?
- is it structured or narrative/unstructured?

Detailed adapter/source guide:

[`../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md)

## Step 2 — Transcribe if the source is unstructured

For a narrative source such as the DPC Bit List PDF/web publication:

```text
original PDF/HTML
 -> transcription draft
 -> human review
 -> versioned JSON artifact
 -> normal adapter pipeline
```

The transcription may be:

- manual;
- AI-assisted;
- produced by another extraction service.

The governance rule is the same in all cases: the structured artifact becomes the input to the adapter **only after review**.

Every transcribed record should retain a locator back to the source passage, for example page number, section, heading, URL, and a short source excerpt where licensing permits.

Use:

[`TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](TRANSCRIBING_UNSTRUCTURED_SOURCES.md)

Machine-checkable schema:

```text
qnl_format_registry_builder/config/schemas/unstructured_source_transcription.v1.schema.json
```

Reusable AI transcription prompt:

```text
qnl_format_registry_builder/config/prompts/transcribe_unstructured_source/v1.0.md
```

DPC-specific prompt:

```text
qnl_format_registry_builder/config/prompts/transcribe_unstructured_source/dpc_bit_list.v1.md
```

## Step 3 — Add/configure the adapter

Structured sources enter through a `SourceAdapter` that implements:

```python
acquire() -> list[SourceSnapshot]
extract(snapshots) -> list[RawFormatRecord]
```

Use the built-in `standard_json` adapter when the reviewed transcription package already fits the standard JSON record shape and no source-specific extraction behavior is required.

Use a thin source-specific adapter when you need to:

- promote source-native values into `RawFormatRecord.native_fields`;
- normalize source-specific identifiers;
- enforce edition/source-specific validation;
- preserve richer source locators/provenance;
- support automatic source acquisition.

Detailed implementation guide:

[`../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md)

## Step 4 — Register the source and identifier rules

Configure the source instance:

```json
{
  "id": "dpc_bit_list",
  "type": "standard_json",
  "enabled": true,
  "required": false,
  "uris": ["sources/dpc_bitlist/2026-08.reviewed.json"]
}
```

Only define a strong identifier namespace if the source genuinely owns/stably defines one.

Do not promote copied PUID/LOC identifiers to authority-verified identifiers just because they appear in the new source.

## Step 5 — Map source observations to neutral criteria

A source record becoming visible in the registry is not enough for framework-driven risk analysis.

The evidence path is:

```text
source-native observation
 -> criterion mapping
 -> criterion_claim
 -> RiskFramework question
 -> deterministic answer
```

Use the current vocabulary:

```text
qnl_format_registry_builder/config/criteria/v1.json
```

Normally, a new source needs a **mapping**, not a new criterion.

A new criterion is justified only when a preservation-relevant observation cannot be represented safely by the existing neutral vocabulary.

Start here:

[`../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)

Detailed lifecycle:

[`../qnl_format_registry_builder/docs/criterion_mapping_workflow.md`](../qnl_format_registry_builder/docs/criterion_mapping_workflow.md)

## Step 6 — Validate, review, and generate criterion claims

Validate mappings:

```powershell
cd qnl_format_registry_builder
python -m registry_builder mapping validate `
  --criteria config\criteria\v1.json `
  --mappings drafts\my_source.mapping.json
```

AI-generated mappings remain drafts until a human approves them.

After approval, generate claims using an integrated build or criterion-claim backfill.

The output should include `criterion_claims` with source/mapping provenance.

## Step 7 — Test through the risk manager

Do not finish onboarding at “the adapter runs”. Test the evidence at the consumer boundary.

Example machine query:

```json
{
  "action": "assess_format_questions",
  "format": "SWF",
  "filters": {
    "domains": ["adoption_community_support"]
  },
  "scope": "global"
}
```

Or inspect evidence gaps:

```json
{
  "action": "list_evidence_gaps",
  "filters": {
    "family": "Flash"
  },
  "scope": "global"
}
```

The final check is that the intended source claim is actually visible to the intended framework question with correct provenance and scope.

## DPC Bit List worked path

Recommended operational flow:

```text
DPC Bit List PDF/HTML
        |
        v
AI-assisted or manual transcription
        |
        v
human-reviewed JSON artifact
sources/dpc_bitlist/2026-08.reviewed.json
        |
        v
standard_json or DpcBitListAdapter
        |
        v
RawFormatRecord
        |
        v
canonical reconciliation
        |
        v
DPC source-to-criterion mapping
        |
        v
criterion_claims
        |
        v
preservation_risk_manager
```

### Important DPC distinction

The DPC Bit List's overall endangerment/category is a source conclusion. Do not automatically map a composite label such as “Practically Extinct” directly into a primitive sustainability criterion unless the criteria vocabulary/framework explicitly models that source conclusion as its own evidence type.

Useful underlying observations in DPC narrative may instead support criteria such as software support, adoption, dependencies, or ecosystem health after review.

If a DPC observation has no suitable current criterion, record it as unmapped and use that as a vocabulary-extension signal rather than forcing it into the wrong criterion.

## AI has two different roles in source onboarding

Keep them separate.

### AI transcription

```text
unstructured source -> structured source-native draft
```

The model extracts what the publication says and preserves source locators. It does not decide QNL risk.

### AI criterion-mapping draft

```text
reviewed structured fields -> proposed neutral criterion mappings
```

The model receives the current criteria vocabulary and proposes a mapping JSON. It does not approve the mapping.

Both outputs require human review.

## Completion checklist

A new source is fully onboarded when:

- [ ] source boundary and edition are defined;
- [ ] original source is retained/reacquirable;
- [ ] unstructured content has a reviewed versioned transcription when needed;
- [ ] adapter emits stable `RawFormatRecord` objects;
- [ ] source identifiers are classified correctly;
- [ ] source-native evidence is preserved;
- [ ] criterion mappings are reviewed/validated;
- [ ] `criterion_claims` are generated;
- [ ] institution-scoped evidence is correctly scoped;
- [ ] risk-manager query proves the evidence is consumable;
- [ ] tests/documentation are added.

## Related documentation

- Canonical data model: [`DATA_MODEL.md`](DATA_MODEL.md)
- Structured source/adapter details: [`../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md)
- Unstructured source transcription: [`TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](TRANSCRIBING_UNSTRUCTURED_SOURCES.md)
- Criterion mapping: [`../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)
- Risk manager queries: [`../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md`](../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md)
