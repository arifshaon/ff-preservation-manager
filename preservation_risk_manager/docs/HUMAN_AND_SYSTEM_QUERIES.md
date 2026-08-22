# Human and system preservation-risk queries

The Risk Manager exposes one controlled request/execution layer through two main interfaces:

```text
Human
  natural-language question
       ↓
  AI request routing
       ↓
  controlled request
       ↓
  registry + governed synthesis + framework evidence
       ↓
  optional AI-assisted synthesis
       ↓
  human-readable answer

System/API
  structured request
       ↓
  same controlled execution layer
       ↓
  canonical JSON
       ↓ optional
  AI-assisted synthesis when explicitly enabled
```

The human and machine paths therefore share the same format resolution, registry evidence, synthesis policy, question framework, and audit boundaries.

For simple copy/paste examples, start with [`../../docs/USE_CASES.md`](../../docs/USE_CASES.md).

## Human mode: `ask`

Example:

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --ai-mode synthesize
```

A normal human answer can include:

- resolved format identity;
- governed/config synthesized risk;
- source-native risk assessments such as NARA or DPC where available;
- supporting criterion/source evidence;
- AI-assisted synthesized risk when requested;
- rationale, confidence and uncertainty;
- capability/web-search audit information;
- question-level evidence/gaps when the request asks for them.

Use `--json` when you need the canonical payload and routing/AI audit data instead of prose.

## Machine mode: `query-json`

A system that already knows its operation should send a structured request directly.

Example request:

```json
{
  "action": "assess_format",
  "format": "fmt/276",
  "scope": "global"
}
```

Run it:

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json
```

This avoids using an AI model merely to reinterpret a stable machine instruction.

## Common request shape

Requests normalize to fields such as:

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

Not every field applies to every action.

## Supported actions

### `assess_format`

Assess one format and return the available overall source-risk context plus framework analysis.

```json
{
  "action": "assess_format",
  "format": "fmt/276",
  "scope": "global"
}
```

### `assess_format_questions`

Assess selected framework domains/questions for one format.

```json
{
  "action": "assess_format_questions",
  "format": "fmt/276",
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
  "format": "fmt/276",
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

### `list_assessment_questions`

Return the framework question catalogue.

```json
{
  "action": "list_assessment_questions",
  "filters": {
    "domains": ["software_dependencies_environment"]
  },
  "scope": "global"
}
```

### `search_formats`

Search current canonical formats without running risk analysis.

```json
{
  "action": "search_formats",
  "query": "JPEG 2000",
  "scope": "global",
  "limit": 100
}
```

### `assess_format_family`

Assess plausible members of a named family.

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

Family membership is deliberately conservative; a shared extension or MIME type alone is not sufficient proof of family membership.

### `list_at_risk_formats`

Return formats matching requested risk bands where the selected framework/policy supports banded results.

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

Always inspect unbanded/unknown counts. An empty banded result does not mean every candidate is safe.

### `list_evidence_gaps`

Explain why one format or a family lacks enough evidence for selected framework questions.

```json
{
  "action": "list_evidence_gaps",
  "format": "fmt/276",
  "scope": "global"
}
```

### `plan_evidence_remediation`

Convert evidence gaps into a controlled remediation queue.

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

Current work types include mapping review, source-evidence acquisition, and framework-alignment work. Missing evidence is never silently converted to Low risk.

## Global vs institution scope

### Global

```json
{
  "action": "assess_format_questions",
  "format": "fmt/276",
  "scope": "global"
}
```

Global scope excludes institution-scoped evidence.

### Institution

```json
{
  "action": "assess_format_questions",
  "format": "fmt/276",
  "filters": {
    "domains": ["local_institutional_feasibility"]
  },
  "scope": "institution",
  "institution_id": "qnl"
}
```

Institution scope adds evidence explicitly associated with that institution. Local capability statements must not become universal format facts.

## Human prompt examples

The router is intended to handle questions such as:

```text
What is the preservation risk of fmt/276?
What are the source assessments for PDF 1.7?
What are the software dependency risks of PDF 1.7?
How well documented is this format?
Does it rely on proprietary software or external assets?
Which PDF formats are at risk?
Why can this format not be fully assessed?
What evidence should we collect next?
Can QNL currently manage this format?
```

The 22 framework questions and stable IDs are summarized in [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md).

## AI boundaries

For human prompts, AI routing may determine request parameters such as:

```text
action
format/query/family
question domains / IDs
risk bands
content type
scope / institution
limit
```

The application still owns format resolution, registry evidence retrieval, governed synthesis, framework execution, and validation of the returned request.

With `--ai-mode synthesize`, AI receives the assembled evidence/methodology and returns a separate AI-assisted overall result. That result may agree or disagree with the governed baseline, but it does not rewrite the source-native evidence or MongoDB.

## Format ambiguity

Format resolution may return:

```text
resolved
ambiguous
not_found
```

The application must not choose an arbitrary PDF/version merely because an extension such as `.pdf` matches many canonical records.

Optional bounded AI identification can be enabled separately; see [`FORMAT_IDENTIFICATION.md`](FORMAT_IDENTIFICATION.md).

## Canonical JSON response

Common response areas can include:

```text
status
request
framework
scope
resolved format
source risk assessments
governed_synthesis
question/framework analysis
evidence gaps/remediation
ai_assisted_synthesis
identification audit
provider/capability audit
```

Exact fields are action-specific. Machine clients should use structured fields, not scrape human prose.

## Which interface should software use?

Use `query-json` or the HTTP API when the caller already knows the requested action.

Use `ask` when a person expresses preservation intent in ordinary language.

For HTTP/Swagger integration see [`../../docs/API_AND_SWAGGER.md`](../../docs/API_AND_SWAGGER.md).

## Related documentation

- Installation: [`../../docs/INSTALLATION.md`](../../docs/INSTALLATION.md)
- Operator use cases: [`../../docs/USE_CASES.md`](../../docs/USE_CASES.md)
- Repository architecture: [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- API/Swagger: [`../../docs/API_AND_SWAGGER.md`](../../docs/API_AND_SWAGGER.md)
- Format identification: [`FORMAT_IDENTIFICATION.md`](FORMAT_IDENTIFICATION.md)
- AI analysis: [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)
- CLI reference: [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
