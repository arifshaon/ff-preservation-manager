# Prompt: draft DPC Bit List criterion mapping

Use this prompt with an AI agent after uploading the DPC Bit List source, the current neutral criteria vocabulary, and (preferably) an audit/source-field profile from the adapter.

You are drafting a criterion-mapping configuration for the QNL File Format Registry Builder.

I will upload:
1. the DPC Bit List source file/export;
2. `config/criteria/v1.json`;
3. a source-field audit/profile showing the exact fields emitted by the adapter, if available;
4. one or more accepted mapping examples;
5. the project's negative mapping rules.

Your task is to map ONLY preservation-relevant DPC source observations to the existing neutral criteria vocabulary.

## Architecture rules

- Criterion claims are observations.
- Hazard/risk bands are conclusions.
- Actions are decisions.
- Readiness is capability.
- Do not map an overall DPC risk/status/ranking directly to a neutral criterion if it is a composite conclusion.
- Do not map recommended preservation actions or preferred tools to sustainability/technical criteria.
- Do not invent criterion IDs or criterion values.
- Do not force every DPC field into a criterion.
- If a field does not fit an existing criterion, place it in `no_criterion`.
- If semantics are unclear, place it in `needs_review`.
- If exact adapter `from_field` paths are not proven by the supplied audit/profile, do not guess that they are production-ready; flag them for adapter-field confirmation.
- AI mappings are drafts only. Do not set `decided_by` and do not mark rules accepted/approved.

## Source independence

- Use `independent` if DPC expresses the observation itself.
- Use `source_derived` if DPC explicitly republishes another authority's observation.
- Never use `institution_scoped` for DPC unless the supplied source is actually an institution-specific local dataset.

## Directness

- `explicit` = source states the same observation directly.
- `derived` = interpretation/transformation is required but remains a non-composite observation.
- `inferred` = indirect/weak evidence.

## Output requirements

- Return ONLY one JSON object.
- No markdown fences.
- No explanation outside JSON.
- `criteria_version` must match the uploaded criteria vocabulary.
- `claim_review_status` must be `unreviewed`.
- `review_status` must be `pending`.
- `mapping_mode` must be `ai_draft`.
- `decided_by` and `decided_at` must be null.
- Every mapped target value must exist in the uploaded criterion enum/null value.
- Include `excluded_from_criteria`, `maps`, `no_criterion`, and `needs_review` arrays.
- `source_id` must be a real identifier.
- Include `source_type` only if the exact adapter source type is supplied. If it is not known, omit `source_type`; do not return a placeholder string.

Use this shape when the exact adapter source type is known:

```json
{
  "source_id": "dpc_bit_list",
  "source_type": "dpc_bit_list",
  "mapping_version": "YYYY-MM-DD-draft",
  "criteria_version": "v1",
  "native_vocabulary": "dpc_bit_list",
  "mapping_mode": "ai_draft",
  "drafted_by": "llm",
  "model_id": "<model if known>",
  "prompt_version": "dpc_bit_list/v1",
  "review_status": "pending",
  "claim_review_status": "unreviewed",
  "decided_by": null,
  "decided_at": null,
  "excluded_from_criteria": [
    {
      "field": "<field>",
      "reason": "<why excluded>"
    }
  ],
  "maps": [
    {
      "id": "dpc.<criterion>.<field>.v1",
      "criterion": "<criterion id from uploaded criteria/v1.json>",
      "from_field": "<exact adapter field path>",
      "directness": "explicit | derived | inferred",
      "covers": "full | partial",
      "covers_note": "<required explanation when partial>",
      "source_independence": "independent | source_derived",
      "mapping_status": "draft | needs_review",
      "values": {
        "<DPC native value>": "<allowed target criterion value>"
      },
      "text_rules": [
        {
          "value": "<allowed target criterion value>",
          "contains_any": ["<conservative phrase>"]
        }
      ],
      "rationale": "<why this is evidence for this criterion>"
    }
  ],
  "no_criterion": [
    {
      "field": "<field>",
      "reason": "<why no current criterion fits>",
      "suggests_vocabulary_extension": "<optional proposed neutral criterion id>"
    }
  ],
  "needs_review": [
    {
      "field": "<field>",
      "reason": "<why human review or adapter-field confirmation is needed>"
    }
  ]
}
```

If the adapter source type is not yet known, use the same object but omit the `source_type` property.

Before returning JSON, internally check:
1. every criterion exists in the uploaded vocabulary;
2. every mapped target value is allowed;
3. no composite DPC status/risk conclusion is being treated as a primitive criterion;
4. no action/tool recommendation is being treated as neutral hazard evidence;
5. `institution_scoped` is not used for a global DPC source;
6. uncertain mappings are declined rather than guessed;
7. root `claim_review_status` is exactly `unreviewed`;
8. no literal placeholder is used as `source_id`, `source_type`, `criterion`, or `from_field` in a supposedly tool-ready draft.
