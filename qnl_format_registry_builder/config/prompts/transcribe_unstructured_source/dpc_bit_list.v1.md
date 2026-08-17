# Prompt: transcribe a DPC Bit List edition

Use this prompt with the generic transcription schema:

```text
config/schemas/unstructured_source_transcription.v1.schema.json
```

and the exact DPC Bit List edition/publication being transcribed.

You are drafting a **source-native transcription** of a DPC Bit List edition for later ingestion into the QNL File Format Registry Builder.

This is not a criterion-mapping task and not a QNL risk-scoring task.

## Inputs

I will provide:
1. the exact DPC Bit List PDF/HTML/export for one edition;
2. `unstructured_source_transcription.v1.schema.json`;
3. the known edition/date/source URL if available.

## Required behavior

- Extract only entries actually present in the supplied DPC source.
- Preserve DPC-native terminology and categories.
- Keep any DPC endangerment/status category as a source-native field; do not translate it into QNL `Low`, `Moderate`, or `High` risk.
- Preserve trend/change language only when the DPC source explicitly states it.
- Preserve the rationale as a concise source-native summary; do not add outside explanations.
- Preserve recommended actions/advice as source-native fields if present, but do not turn them into sustainability criteria.
- Extract file extensions, MIME types, PUIDs, other identifiers, or software names only when explicitly present in the supplied source.
- Do not infer missing identifiers from your knowledge of the format.
- Every DPC entry must have a page, section, heading, anchor, or URL locator back to the source.
- If the entry covers a format family rather than one precise technical format, preserve that scope rather than pretending it is a single exact PUID/version.
- If one DPC entry lists multiple technical variants and the source does not distinguish their risk evidence separately, preserve them as one source entry and flag the ambiguity for review.
- If any extraction is uncertain, add a short item to `needs_review` and do not guess.

## Preferred `native_fields`

Use these keys where they match the supplied edition:

```text
endangerment_category
trend
rationale
why_endangered
software_support_statement
adoption_statement
dependency_statement
recommended_action
significant_properties_note
other_source_observations
```

Do not populate a preferred key merely because it exists in this prompt. Omit/null fields that are not stated by the source.

If the edition uses different terminology, preserve the edition's terminology and add a stable descriptive key rather than forcing a false equivalence.

## Output metadata

Use:

```text
schema_version = unstructured_source_transcription/v1
source_id = dpc_bit_list
transcription_method = ai_assisted
transcribed_by = llm
review_status = draft
reviewed_by = null
reviewed_at = null
prompt_version = dpc_bit_list_transcription/v1
```

Set `source_edition`, `transcribed_from`, `source_media_type`, `transcribed_at`, and `model_id` from the supplied context when known.

## Stable source record IDs

Use a deterministic pattern such as:

```text
dpc-<edition>-<normalized-entry-name>
```

This is a local transcription record ID, not a new DPC authority identifier.

## Example shape

The following is structural only; the values are not DPC facts:

```json
{
  "schema_version": "unstructured_source_transcription/v1",
  "source_id": "dpc_bit_list",
  "source_edition": "<edition>",
  "transcribed_from": "<source URL/file>",
  "source_media_type": "application/pdf",
  "transcription_method": "ai_assisted",
  "transcribed_by": "llm",
  "model_id": "<model if known>",
  "prompt_version": "dpc_bit_list_transcription/v1",
  "transcribed_at": "<ISO date-time if known>",
  "review_status": "draft",
  "reviewed_by": null,
  "reviewed_at": null,
  "records": [
    {
      "source_record_id": "dpc-<edition>-example-format",
      "name": "Example Format",
      "extensions": [],
      "mime_types": [],
      "identifiers": {},
      "native_fields": {
        "endangerment_category": "<verbatim/native category if present>",
        "rationale": "<concise source-supported summary>"
      },
      "source_page": 14,
      "source_section": "<section if present>",
      "source_url": "<source URL>",
      "needs_review": []
    }
  ]
}
```

## Final checks before returning

Internally verify:
1. record count and names are grounded in the supplied DPC edition;
2. no extension/MIME/PUID/identifier was supplied from model knowledge;
3. DPC endangerment categories remain source-native;
4. no QNL criterion IDs or risk bands were invented;
5. every record has a usable source locator;
6. uncertain cases are flagged;
7. review status remains `draft`;
8. output is one JSON object only, with no markdown fence or prose outside JSON.

After this transcription is human-reviewed, use the separate DPC criterion-mapping prompt:

```text
config/prompts/propose_mapping/dpc_bit_list.v1.md
```

That second AI task maps reviewed source-native observations to the current neutral criteria vocabulary. It must not be combined with this transcription task.
