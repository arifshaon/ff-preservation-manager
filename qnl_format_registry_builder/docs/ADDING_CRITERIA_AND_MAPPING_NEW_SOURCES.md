# Adding criteria and mapping a new source

This is the simplified operator/developer guide for connecting a new evidence source to preservation-risk criteria.

The most important distinction is:

```text
A new SOURCE usually needs a new MAPPING.
It does not automatically need a new CRITERION.
```

Use the existing neutral criterion vocabulary whenever the source expresses an observation that already fits it. Add a new criterion only when the source contains a preservation-relevant observation that cannot be represented safely by an existing criterion.

## The four layers

```text
source document / API / spreadsheet
        |
        v
SourceAdapter -> RawFormatRecord.native_fields / institution_evidence
        |
        v
criterion mapping JSON
        |
        v
criterion_claims
        |
        v
preservation_risk_manager framework question
```

The adapter preserves source-native evidence. The mapping translates only the evidence that fits a neutral criterion. The risk framework decides how those claims answer questions and affect assessment.

## Quick decision tree

Ask these questions in order:

```text
1. Can the source be ingested already?
   YES -> run it and inspect the emitted fields.
   NO  -> add/configure a source adapter first.

2. Does a source field describe an existing criterion?
   YES -> add a mapping rule.
   NO  -> leave it unmapped OR consider a new criterion.

3. Is the evidence global or institution-specific?
   GLOBAL      -> source_independence = independent/source_derived
   INSTITUTION -> source_independence = institution_scoped

4. Is the field actually a conclusion/action/readiness statement?
   YES -> do not force it into a sustainability/technical criterion.
```

# Part A — Add a new external source using existing criteria

## Step 1 — Ingest the source without criterion mapping

First make sure the source adapter can acquire and normalize the source.

A source adapter should preserve useful upstream fields in:

```text
RawFormatRecord.native_fields
RawFormatRecord.raw
```

and should preserve identifiers/provenance separately.

For a new source, run the registry build before creating a mapping. This lets you map the **actual normalized field paths**, not guessed column names.

```powershell
python -m registry_builder run `
  --config config\my-new-source.json `
  --workdir work `
  --out output
```

If a dedicated adapter does not exist yet, see:

- [`ADDING_AND_RUNNING_DATA_SOURCES.md`](ADDING_AND_RUNNING_DATA_SOURCES.md)
- [`ADAPTER_IMPLEMENTATION_GUIDE.md`](ADAPTER_IMPLEMENTATION_GUIDE.md)

## Step 2 — Audit what the source actually emitted

Run:

```powershell
python -m registry_builder criterion-evidence-audit `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --source my_source_id `
  --out audit\my_source_evidence.json
```

The audit is the safest input for mapping because it shows real source fields/values in the local registry.

## Step 3 — Compare source fields with the neutral vocabulary

The current vocabulary is:

```text
config/criteria/v1.json
```

Example criterion:

```json
"sustainability.adoption": {
  "kind": "ordinal",
  "values": [
    "very_high",
    "high",
    "moderate",
    "low",
    "negligible"
  ],
  "null_value": "unknown"
}
```

A mapping can only emit values allowed by that criterion.

Do **not** invent a new target value in a source mapping.

## Step 4 — Create a draft mapping JSON

A minimal external-source rule looks like:

```json
{
  "source_type": "my_source_type",
  "mapping_version": "2026-08-17-draft",
  "criteria_version": "v1",
  "native_vocabulary": "my_source_v1",
  "mapping_mode": "manual_draft",
  "review_status": "pending",
  "claim_review_status": "unreviewed",
  "decided_by": null,
  "decided_at": null,
  "maps": [
    {
      "id": "my_source.adoption.v1",
      "criterion": "sustainability.adoption",
      "from_field": "native_fields.adoption",
      "directness": "explicit",
      "covers": "partial",
      "source_independence": "independent",
      "mapping_status": "draft",
      "values": {
        "Widely used": "high",
        "Limited use": "low"
      },
      "rationale": "The source directly describes adoption in its target community."
    }
  ]
}
```

### Directness

Use:

```text
explicit  = source directly states the same observation
derived   = interpretation/transformation is required, but evidence is still non-composite
inferred  = weak indirect evidence
```

Prefer `needs_review`/no mapping over an aggressive inferred rule.

### Source independence

Use:

```text
independent        = source expresses its own evidence
source_derived     = source copied/derived it from another authority
institution_scoped = local institutional observation only
```

## Step 5 — Validate the draft

```powershell
python -m registry_builder mapping validate `
  --criteria config\criteria\v1.json `
  --mappings drafts\my_source.v1.proposal.json
```

Validation checks target criteria/values and rejects several unsafe patterns.

## Step 6 — Human review and approval

AI or automation may draft a mapping, but a human should approve it.

For an accepted mapping, set appropriate review metadata, for example:

```json
{
  "review_status": "approved",
  "claim_review_status": "approved",
  "decided_by": "QNL Digital Curation, Preservation, and Access",
  "decided_at": "2026-08-17"
}
```

and change approved rule(s) to:

```json
"mapping_status": "accepted"
```

Then move/copy the approved file into:

```text
config/criterion_mappings/
```

## Step 7 — Dry-run a criterion-claim backfill

If source evidence is already stored, do not reacquire everything just to test a new mapping.

```powershell
python -m registry_builder criterion-claims backfill `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings\my_source.v1.approved.json `
  --dry-run
```

Inspect the generated count/coverage before writing.

## Step 8 — Write the claims

```powershell
python -m registry_builder criterion-claims backfill `
  --storage-config config\storage.mongodb.example.json `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings\my_source.v1.approved.json
```

Or include the approved mapping in the normal integrated build and rerun the pipeline.

## Step 9 — Verify through the risk manager

Example:

```powershell
cd ..\preservation_risk_manager
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"fmt-pdf","scope":"global"}' `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

Verify that the criterion claim is visible in the evidence used for the intended format and scope.

# Part B — Institution-level evidence

Institution evidence follows the same pipeline but must remain scoped.

Example source configuration:

```json
{
  "id": "qnl_format_evidence_2026",
  "type": "qnl_institution_format_evidence",
  "enabled": true,
  "institution_id": "qnl",
  "institution_name": "Qatar National Library",
  "retrieval_mode": "local_files",
  "uris": ["examples/qnl_institution_format_evidence.seed.json"]
}
```

A mapping rule for institution-authored evidence must use:

```json
"source_independence": "institution_scoped"
```

Example pattern:

```json
{
  "id": "qnl.external_dependencies.v1",
  "criterion": "sustainability.external_dependencies",
  "from_collection": "institution_evidence_claims",
  "from_field": "evidence_value",
  "where": {
    "criterion_id": "sustainability.external_dependencies"
  },
  "directness": "explicit",
  "covers": "partial",
  "source_independence": "institution_scoped",
  "mapping_status": "accepted",
  "values": {
    "low_dependency_in_qnl_environment": "low",
    "specialist_software_dependency": "high"
  }
}
```

The result is available to:

```text
scope = institution
institution_id = qnl
```

and excluded from global-only evidence use.

### What not to turn into a global criterion claim

Institution evidence often contains operational decisions such as:

```text
preferred preservation action
local processing tool
staff assignment
migration decision
accept/reject policy
collection priority
```

These are not automatically global sustainability facts.

Keep local evidence, policy, readiness and actions separate.

# Part C — Add a genuinely new criterion

Only do this when an important source observation cannot be represented by the existing neutral vocabulary.

## Step 1 — Define the neutral observation

A criterion should describe evidence, not a final risk band or action.

Good pattern:

```text
technical.renderer_availability
```

Bad pattern:

```text
risk.high
migrate_now
preferred_format
```

## Step 2 — Add the criterion to the vocabulary

Edit:

```text
config/criteria/v1.json
```

Example:

```json
"local.migration_pathways": {
  "kind": "ordinal",
  "values": [
    "tested_pathway",
    "unverified_pathway",
    "manual_only",
    "no_known_pathway"
  ],
  "null_value": "unknown"
}
```

If a criterion describes institution-specific capability, a `local.*` namespace is clearer than pretending the observation is universally true. Claims mapped to it should still be institution-scoped.

The current broad 22-question risk framework already refers to some `local.*` evidence fields such as local capability, migration pathways and storage overhead. These are not all represented in the current `criteria/v1.json`; adding them should therefore be an explicit vocabulary change, not an accidental mapping workaround.

## Step 3 — Add/update mapping rules

The source mapping must emit only values declared in the new criterion.

## Step 4 — Bind the criterion to a risk question

Adding the vocabulary criterion alone does **not** change a preservation-risk score.

A risk framework must explicitly consume the criterion through its question configuration, for example:

```json
{
  "id": "q_migration_pathways",
  "evidence_fields": ["local.migration_pathways"],
  "evidence_value_map": {
    "tested_pathway": "low_risk",
    "unverified_pathway": "moderate_risk",
    "manual_only": "moderate_risk",
    "no_known_pathway": "high_risk"
  }
}
```

The framework owns risk interpretation. The criterion vocabulary owns neutral evidence values.

## Step 5 — Revalidate/calibrate the framework

If the new question/value changes scoring, weights, maximum score or risk thresholds, the framework must be reviewed/calibrated before production banding is trusted.

# Part D — AI-assisted mapping workflow

AI is useful for **drafting** a source-to-criterion mapping, especially for complex external sources such as the DPC Bit List.

AI must not approve its own mapping.

## Recommended files to give the AI agent

For the safest result, upload/provide:

```text
1. the source itself
   e.g. DPC Bit List spreadsheet/CSV/export/document

2. config/criteria/v1.json
   the only allowed target criterion vocabulary

3. audit/my_source_evidence.json
   or another exact adapter/source field profile

4. one or more accepted mapping examples
   e.g. config/criterion_mappings/loc_fdd_xml.v1.approved.json

5. config/prompts/propose_mapping/negative_rules.v1.json

6. optionally:
   config/criterion_mappings/nara_digital_preservation_framework.v1.approved.json
   config/criterion_mappings/qnl_institution_format_evidence.v1.json
```

### Why the audit/field profile matters

The AI can understand a source document, but the tool needs exact `from_field` paths that match what the adapter stores.

For example, a DPC spreadsheet column called:

```text
Current status
```

is not automatically the same as:

```text
native_fields.current_status
```

until the source adapter/output contract says so.

Therefore the safest order is:

```text
source -> adapter -> audit/field profile -> AI mapping draft
```

If an adapter has not yet been implemented, the AI can still propose the semantic mapping, but `from_field` paths must be checked after the adapter is defined.

# Part E — Copy/paste AI prompt for DPC Bit List mapping

A reusable prompt file is also stored at:

```text
config/prompts/propose_mapping/dpc_bit_list.v1.md
```

Copy/paste version:

```text
You are drafting a criterion-mapping configuration for the QNL File Format Registry Builder.

I will upload:
1. the DPC Bit List source file/export;
2. config/criteria/v1.json;
3. a source-field audit/profile showing the exact fields emitted by the adapter, if available;
4. one or more accepted mapping examples;
5. the project's negative mapping rules.

Your task is to map ONLY preservation-relevant DPC source observations to the existing neutral criteria vocabulary.

Important architecture rules:
- Criterion claims are observations.
- Hazard/risk bands are conclusions.
- Actions are decisions.
- Readiness is capability.
- Do not map an overall DPC risk/status/ranking directly to a neutral criterion if it is a composite conclusion.
- Do not map recommended preservation actions or preferred tools to sustainability/technical criteria.
- Do not invent criterion IDs or criterion values.
- Do not force every DPC field into a criterion.
- If a field does not fit an existing criterion, place it in no_criterion.
- If semantics are unclear, place it in needs_review.
- If exact adapter from_field paths are not proven by the supplied audit/profile, do not guess that they are production-ready; flag them for adapter-field confirmation.
- AI mappings are drafts only. Do not set decided_by and do not mark rules accepted/approved.

Source independence:
- Use independent if DPC expresses the observation itself.
- Use source_derived if DPC explicitly republishes another authority's observation.
- Never use institution_scoped for DPC unless the supplied source is actually an institution-specific local dataset.

Directness:
- explicit = source states the same observation directly.
- derived = interpretation/transformation is required but remains a non-composite observation.
- inferred = indirect/weak evidence.

Output requirements:
- Return ONLY one JSON object.
- No markdown fences.
- No explanation outside JSON.
- criteria_version must match the uploaded criteria vocabulary.
- claim_review_status must be "unreviewed".
- review_status must be "pending".
- mapping_mode must be "ai_draft".
- decided_by and decided_at must be null.
- Every mapped target value must exist in the uploaded criterion enum/null value.
- Include excluded_from_criteria, maps, no_criterion and needs_review arrays.

Use this shape:
{
  "source_id": "dpc_bit_list",
  "source_type": "<exact adapter source_type if supplied>",
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

Before returning JSON, internally check:
1. every criterion exists in the uploaded vocabulary;
2. every mapped target value is allowed;
3. no composite DPC status/risk conclusion is being treated as a primitive criterion;
4. no action/tool recommendation is being treated as neutral hazard evidence;
5. institution_scoped is not used for a global DPC source;
6. uncertain mappings are declined rather than guessed.
```

# Part F — Validate the AI output

Save the AI JSON as:

```text
drafts/dpc_bit_list.v1.proposal.json
```

Then run:

```powershell
python -m registry_builder mapping validate `
  --criteria config\criteria\v1.json `
  --mappings drafts\dpc_bit_list.v1.proposal.json
```

Validation success does **not** mean the mapping is semantically correct. It means the JSON is structurally compatible with the current vocabulary/rules.

A human must still review:

- whether the DPC field means what the rule claims;
- whether a direct source field is being confused with a composite status;
- whether the target criterion is appropriate;
- whether `directness` and `source_independence` are accurate;
- whether `from_field` exactly matches adapter output;
- whether text rules are conservative enough;
- whether a proposed new criterion is truly required.

# Part G — Final verification checklist

Before an approved mapping is used in production:

```text
[ ] source adapter/output is stable
[ ] actual field audit reviewed
[ ] target criterion IDs exist
[ ] target values are allowed
[ ] no composite risk conclusion leakage
[ ] no policy/action leakage
[ ] institution-specific evidence is institution_scoped
[ ] mapping validate passes
[ ] human decided_by / decided_at recorded
[ ] dry-run backfill inspected
[ ] criterion claims written successfully
[ ] sample risk-manager query proves expected scope/evidence
[ ] tests pass
```

Run:

```powershell
pytest -q
```

and, after cross-module changes, run the preservation-risk-manager tests as well.