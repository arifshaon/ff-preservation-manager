# Human and system preservation-risk queries

The preservation risk manager exposes **one canonical request/execution layer with two presentation modes**:

```text
Human user
  natural-language question
      -> AI routes intent/parameters only
      -> canonical request
      -> deterministic registry/framework execution
      -> human-readable detailed answer

System/API
  canonical structured request
      -> deterministic registry/framework execution
      -> canonical JSON
```

The human and machine paths therefore do not have separate preservation logic.

## Human mode is for questions, not JSON

A person should ask a normal preservation question:

```powershell
python -m preservation_risk_manager ask `
  "What are the software dependency and environment risks of PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

Normal `ask` output is detailed prose for a preservation professional. Depending on the requested action it can include:

- resolved format;
- assessment conclusion/status;
- evidence coverage;
- relevant domain/question headings;
- question-by-question controlled assessments;
- derivation status;
- supporting evidence provenance;
- evidence gaps;
- coverage warnings;
- draft/calibration warnings;
- at-risk format lists;
- evidence-remediation priorities.

The renderer is deterministic over the canonical result; it does not ask the AI model to invent a narrative answer.

## Human debugging/audit mode

Add `--json` when you want to inspect the canonical payload and router metadata behind a human question:

```powershell
python -m preservation_risk_manager ask `
  "What are the software dependency and environment risks of PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --json
```

This is useful for routing tests and audits, not the normal human presentation.

The JSON includes `router` metadata such as provider/model, token usage, the raw structured route, and any deterministic mechanical repairs.

## Machine/system mode

A system that already knows what operation it needs should bypass the natural-language router.

Example:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["software_dependencies_environment"]
  },
  "scope": "global"
}
```

Execute a request file:

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

No AI provider is called.

A future HTTP API/dashboard/scheduler should wrap this canonical request/result layer rather than reproduce the CLI or natural-language router.

## Common request shape

The normalized request can contain:

```json
{
  "action": "...",
  "format": null,
  "query": null,
  "filters": {
    "family": null,
    "risk_bands": [],
    "domains": [],
    "question_ids": [],
    "content_type": null
  },
  "scope": "global",
  "institution_id": null,
  "limit": 100
}
```

Not every field is required for every action. `normalize_request` fills omitted optional filter arrays with safe defaults.

## Supported actions

### `assess_format`

Assess one resolved format against the full active framework.

Human:

```text
What is the obsolescence risk of PDF?
```

Machine:

```json
{
  "action": "assess_format",
  "format": "PDF",
  "scope": "global"
}
```

Use a calibrated/banding-enabled framework when the requirement is an overall Low/Moderate/High result. With the broad draft framework, question-level analysis is available but overall banding is intentionally disabled.

### `assess_format_questions`

Assess one format against selected domains/questions/content type.

Human:

```text
What are the software dependency and environment risks of PDF?
```

Machine:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["software_dependencies_environment"]
  },
  "scope": "global"
}
```

Specific questions:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "question_ids": [
      "q_platform_dependency",
      "q_external_assets",
      "q_open_source_tooling"
    ]
  },
  "scope": "global"
}
```

Content-type selection:

```json
{
  "action": "assess_format_questions",
  "format": "TIFF",
  "filters": {
    "domains": ["essential_characteristics"],
    "content_type": "image"
  },
  "scope": "global"
}
```

### `list_assessment_questions`

List/filter the framework's question catalog.

Human:

```text
What preservation-risk questions do you assess?
```

```text
What questions do you use for software dependency risk?
```

Machine:

```json
{
  "action": "list_assessment_questions",
  "filters": {
    "domains": ["software_dependencies_environment"]
  },
  "scope": "global"
}
```

The output includes stable question IDs, labels, domains, definitions, guidance, applicability, evidence fields, and controlled answer options.

### `search_formats`

Discover matching current canonical formats without running assessment.

Human:

```text
Find formats matching JPEG 2000.
```

Machine:

```json
{
  "action": "search_formats",
  "query": "JPEG 2000",
  "scope": "global",
  "limit": 100
}
```

General search can consider names, identifiers, MIME types, extensions, and related searchable fields. It is intentionally broader than family membership.

### `assess_format_family`

Assess/rank all plausible members of a named family.

Human:

```text
Assess the PDF family.
```

Machine:

```json
{
  "action": "assess_format_family",
  "filters": {
    "family": "PDF"
  },
  "scope": "global",
  "limit": 500
}
```

Family discovery uses explicit family metadata when present; otherwise it uses names/aliases. Extensions/MIME/authority identifiers alone do not establish family membership.

### `list_at_risk_formats`

Assess a set and return formats in requested risk bands. If bands are omitted, the controlled default is `Moderate` + `High`.

Human:

```text
Give me the PDF formats that are at risk.
```

Machine:

```json
{
  "action": "list_at_risk_formats",
  "filters": {
    "family": "PDF",
    "risk_bands": ["Moderate", "High"]
  },
  "scope": "global",
  "limit": 500
}
```

Batch output also reports how many candidates are High, Moderate, Low, and **Unbanded**.

An empty `results` list means no **banded** candidate met the requested bands. It does not mean all candidates are safe. Always inspect `unbanded_count`, `unbanded_results`, and `coverage_warning`.

Use this action with a framework whose overall banding has been validated/enabled.

### `list_evidence_gaps`

Explain why one format or a family cannot be fully assessed.

Human:

```text
Why can't PDF 1.7 be assessed?
```

```text
Which PDF formats need more evidence and what is missing?
```

Single format machine request:

```json
{
  "action": "list_evidence_gaps",
  "format": "PDF 1.7",
  "scope": "global"
}
```

Family machine request:

```json
{
  "action": "list_evidence_gaps",
  "filters": {
    "family": "PDF"
  },
  "scope": "global",
  "limit": 500
}
```

Gap diagnoses distinguish cases such as:

```text
no_matching_evidence
claims_exist_but_do_not_map
claims_exist_but_not_for_framework
mixed mapping/evidence gaps
```

### `plan_evidence_remediation`

Convert diagnosed gaps into a deterministic work queue.

Human:

```text
What should we fix first so the PDF family can be assessed?
```

Machine:

```json
{
  "action": "plan_evidence_remediation",
  "filters": {
    "family": "PDF"
  },
  "scope": "global",
  "limit": 500
}
```

Current remediation types include:

```text
mapping_rule_needed
source_evidence_needed
framework_alignment_review
```

Priorities use controlled P1/P2/P3 rules. Critical blocked questions are prioritized before non-critical enrichment work.

## Human prompt examples by preservation domain

The natural-language router is intended to understand ordinary preservation questions such as:

### Specification / governance

```text
How well documented is PDF?
Can an independent developer implement this format from a public specification?
Who governs this format?
Is this format stable across versions?
```

### Software/environment

```text
Does this format depend on proprietary software or legacy hardware?
Does PDF require external assets to render correctly?
Are open-source viewers or validators available?
```

### Adoption/community

```text
Is this format still widely adopted?
Is third-party read/write support still actively maintained?
Can the format be reliably identified through PRONOM or MIME identifiers?
```

### Technical structure

```text
Is the format transparent or an opaque binary format?
Does it use lossy compression?
Would migration lose essential characteristics?
```

### Rights/TPM

```text
Are patents or licensing restrictions a preservation problem for this format?
Can DRM or encryption prevent automated preservation actions?
```

### Metadata/accessibility

```text
Can the format preserve embedded metadata?
Can it preserve accessibility features such as tags, alt text or captions?
```

### Essential characteristics

```text
Can TIFF preserve the image characteristics we need?
Can this video format retain timecodes, multi-track audio and subtitles?
Can this spreadsheet format preserve formulas and typed relationships?
```

### Local QNL feasibility

```text
Can QNL currently manage this format with our software and staff?
Does QNL have a tested migration pathway for this format?
Would this format create unsustainable storage/network overhead for QNL?
```

Stable domain/question IDs are documented in [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md).

## Global vs institution-scoped queries

### Global

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["specification_governance"]
  },
  "scope": "global"
}
```

Global scope excludes institution-scoped claims.

### QNL

Human:

```powershell
python -m preservation_risk_manager ask `
  "Can QNL sustainably manage PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --institution qnl
```

Machine:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["local_institutional_feasibility"]
  },
  "scope": "institution",
  "institution_id": "qnl"
}
```

Institution scope includes global claims plus claims for that institution.

## Human output behavior

For targeted question assessment the human renderer reports, for example:

```text
PDF preservation-risk assessment

Evidence coverage: 2 of 3 selected questions answered (67%).
Overall Low/Moderate/High banding is not reported because the framework
is draft_unvalidated and banding is disabled.

Software Dependencies & Environment
- Is rendering dependent on specific operating systems ...?
  Assessment: ...
  Derivation: ...
  Supporting evidence: ...

- Does opening or rendering depend on external assets ...?
  Assessment: Unknown / insufficient evidence.
  Evidence gap: ...

Interpretation
This is a partial assessment. Unresolved questions must not be read as
proof that no preservation risk exists.
```

Human rendering is based on the canonical response and retains coverage/caveats.

## Canonical JSON response behavior

A successful response contains common fields such as:

```text
status
request
framework
scope
institution_id
result/result_count or results/result_count
```

Action-specific data can include:

- format identity;
- score/risk band;
- calibration/banding status;
- evidence completeness;
- question results;
- evidence hashes;
- family candidate counts;
- unbanded candidates;
- coverage warnings;
- gap summaries;
- remediation summaries.

Exact response shape is action-specific; clients should key behavior off `action`, `status`, and documented fields rather than scraping human output.

## Error and resolution behavior

The API intentionally returns structured ambiguity/not-found states rather than guessing.

Examples:

```text
status = ambiguous
status = not_found
status = error
```

A machine client should handle these explicitly.

A human `ask` command renders a concise readable failure unless `--json` was requested.

## AI router boundaries

For human prompts, the router may determine:

```text
action
format/query/family
risk bands
question domains / IDs
content type
scope / institution
limit
```

It may not determine:

```text
risk score
risk band
framework answer from general knowledge
registry evidence
QNL policy
```

Where a routed request is mechanically inconsistent, deterministic repair rules may normalize it before request validation. The repair is recorded in `ask --json` router metadata.

## Which interface should an application use?

Use:

```text
query-json / canonical request layer
```

when the caller is software and already knows the intended operation.

Use:

```text
ask
```

when the caller is a person expressing preservation intent in ordinary language.

Do not make an automated integration depend on a model reinterpreting a prompt on every run if the integration can send a stable action and IDs directly.

## Related documentation

- All question/domain IDs: [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md)
- Installation and all modes: [`INSTALLATION_SETUP_AND_RUN.md`](INSTALLATION_SETUP_AND_RUN.md)
- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Shared registry/data interface: [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
