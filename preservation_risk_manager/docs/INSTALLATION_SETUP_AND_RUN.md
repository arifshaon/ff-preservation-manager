# Preservation Risk Manager: installation, setup, and run guide

This is the primary operator runbook for `preservation_risk_manager`.

It covers installation, registry/storage access, frameworks, AI configuration, and every current execution mode.

## 1. What this module does

The risk manager reads preservation evidence from the registry and applies explicit frameworks:

```text
format query
 -> RegistryReader
 -> format resolution
 -> criterion claims
 -> evidence pack
 -> framework questions
 -> deterministic derivation/scoring
 -> canonical result
 -> human text or JSON
```

It is normally a **read/assessment layer**. Registry creation and updates are handled by `qnl_format_registry_builder`.

Read the architecture first for design details:

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)

## 2. Requirements

- Python 3.10 or later.
- A registry source:
  - registry-builder storage backend/config, or
  - compatible exported registry JSON.
- The sibling registry-builder package installed when using its storage backends such as MongoDB/file.
- `openai` extra only for AI provider/routing/AI-assisted modes.

## 3. Recommended installation with the registry builder

For operational use against MongoDB, install both packages into the same environment.

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

cd qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"

cd ..\preservation_risk_manager
python -m pip install -e ".[dev,ai]"
pytest -q
```

Using an existing virtual environment is also supported.

### Risk manager only

For deterministic analysis from JSON exports:

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev]"
pytest -q
```

For AI provider support:

```powershell
python -m pip install -e ".[dev,ai]"
```

## 4. Important CLI entry-point note

For all commands in this guide, prefer:

```powershell
python -m preservation_risk_manager ...
```

The module dispatcher routes `ask` and `query-json` to the integration CLI and all core analysis commands to the deterministic/AI analysis CLI.

## 5. Registry/storage setup

### Option A: MongoDB or another registry-builder backend

Pass a registry-builder storage block or a full builder config containing a top-level `storage` object.

Example:

```text
..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

Example content:

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "format_registry",
    "collection_prefix": "",
    "server_selection_timeout_ms": 5000,
    "ping": true
  }
}
```

The risk manager passes this to the common registry-builder storage factory and reads it through `RegistryReader`.

### Option B: exported registry JSON

Commands that support `--registry-json` can read a registry export through `JsonRegistryStore`.

For useful risk assessment, the export should include the relevant evidence/criterion-claim collections, not only canonical names.

## 6. Framework setup

Current examples:

### Small scoring example

```text
examples/qnl_sustainability.framework.example.json
```

Purpose:

- tests/example deterministic scoring;
- 3 questions;
- overall Low/Moderate/High banding enabled.

This is not the full QNL preservation-obsolescence model.

### Broad draft question framework

```text
examples/qnl_preservation_risk_questions.framework.draft.json
```

Purpose:

- 8 assessment domains;
- 22 stable question IDs;
- targeted evidence/question assessment;
- human and machine query use.

Status:

```text
calibration_status = draft_unvalidated
banding_enabled = false
```

The questions can be used operationally, but the framework must not present an overall Low/Moderate/High band until QNL validates scoring weights/thresholds.

See [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md).

## 7. AI provider setup

AI is required for natural-language `ask` routing and AI-assisted analysis modes. It is **not** required for `query-json` or deterministic `analyze-format`.

Copy the example to a local ignored config:

```powershell
New-Item -ItemType Directory -Force config | Out-Null
Copy-Item examples\ai.azure.example.json config\ai.local.json
```

Fill in the deployment/key values locally. Do not commit real credentials.

Inspect/redact config without a generation request:

```powershell
python -m preservation_risk_manager.ai info `
  --config config\ai.local.json
```

Provider smoke test:

```powershell
python -m preservation_risk_manager.ai query `
  --config config\ai.local.json `
  --prompt "Reply with a short confirmation that the provider is available."
```

Structured-output validation:

```powershell
python -m preservation_risk_manager.ai validate-structured `
  --config config\ai.local.json
```

Tool-calling validation:

```powershell
python -m preservation_risk_manager.ai validate-tools `
  --config config\ai.local.json
```

Full provider documentation: [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md).

## 8. Mode: human question (`ask`)

Use this for preservation staff/interactive use.

```powershell
python -m preservation_risk_manager ask `
  "What are the software dependency and environment risks of PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

Normal output is detailed human-readable text.

Flow:

```text
human prompt
 -> AI routes to controlled action only
 -> deterministic registry/framework execution
 -> canonical result
 -> human renderer
```

The AI router does not calculate the risk answer.

More examples: [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md).

## 9. Mode: human question with canonical JSON (`ask --json`)

Use this to debug/audit how a human prompt was routed.

```powershell
python -m preservation_risk_manager ask `
  "Which PDF formats need more evidence and what is missing?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --limit 500 `
  --json
```

JSON includes:

- normalized canonical request;
- deterministic result;
- router provider/model/usage;
- raw routed request;
- deterministic router repairs, if any.

Do not use natural-language routing when a system already knows the intended structured action; use `query-json` instead.

## 10. Mode: machine/system request (`query-json`)

This is the preferred integration interface.

Example request file `request.json`:

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

Execute:

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

Literal JSON is also supported:

```powershell
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"fmt-pdf","scope":"global"}' `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

No AI provider call occurs.

See [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md) for all current actions.

## 11. Mode: deterministic single-format analysis (`analyze-format`)

Use this for full auditable JSON analysis of one format.

```powershell
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --compact-evidence `
  --evidence-summary
```

Useful options:

```text
--institution qnl
--readiness-status Covered
--exposure-level High
--include-unapproved
--evidence-summary
--compact-evidence
```

`--include-unapproved` should be used deliberately for investigation/debugging, not routine approved-evidence assessment.

## 12. Mode: AI-assisted fill gaps

```powershell
python -m preservation_risk_manager analyze-format-ai `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --ai-config config\ai.local.json `
  --ai-mode fill-gaps `
  --compact-evidence
```

Behavior:

- deterministic answers are derived first;
- AI receives only unresolved/ambiguous questions and bounded evidence;
- AI must choose a framework-declared answer ID;
- already resolved deterministic answers are not overwritten;
- no usable evidence means the model should not be asked to invent an answer.

## 13. Mode: independent AI review (`review-all`)

```powershell
python -m preservation_risk_manager analyze-format-ai `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --ai-config config\ai.local.json `
  --ai-mode review-all `
  --compact-evidence
```

Purpose: calibration/evaluation, not automatic override.

The review model receives a raw-source-only evidence view. Deterministic answer/status and normalized mapped values are withheld. AI output is compared with deterministic output only after the response.

A disagreement is a review signal; it does not rewrite deterministic scoring.

## 14. Mode: fixture analysis

Useful for framework/scoring tests without a registry backend.

```powershell
python -m preservation_risk_manager analyze-fixture `
  --framework examples\qnl_sustainability.framework.example.json `
  --evidence-pack examples\pdf.evidence_pack.example.json `
  --answers examples\pdf.answers.example.json
```

The fixture command scores the supplied controlled answers against the framework.

## 15. Mode: policy/action proposal package

```powershell
python -m preservation_risk_manager propose-policy-change `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --institution qnl `
  --readiness-status Covered `
  --exposure-level High `
  --goal "Review whether the current QNL handling posture should change" `
  --compact-evidence
```

This prepares an evidence-grounded proposal/context package for human review. It does not approve policy and does not write policy changes into the registry.

## 16. Global vs institution scope

### Global

Use when assessing general format sustainability:

```json
"scope": "global"
```

Institution-scoped claims are excluded.

### QNL/institution

Human mode:

```powershell
python -m preservation_risk_manager ask `
  "Can QNL sustainably manage this format?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --institution qnl
```

Machine mode:

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

Institution mode includes global evidence plus matching institution-scoped claims.

## 17. Common human questions

Examples:

```text
What is the obsolescence risk of PDF?
What are the software dependency and environment risks of PDF?
Does PDF depend on external assets or proprietary software?
How well documented and governed is PDF?
Which PDF formats are at risk?
Which PDF formats cannot currently be assessed, and why?
What should we fix first so the PDF family can be assessed?
What preservation-risk questions do you assess?
Can QNL sustainably manage this format?
Are there tested migration pathways for this format at QNL?
```

See [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md) and [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md).

## 18. Machine actions

Current controlled actions:

```text
assess_format
assess_format_questions
search_formats
assess_format_family
list_at_risk_formats
list_assessment_questions
list_evidence_gaps
plan_evidence_remediation
```

Machine clients should use action IDs and stable domain/question IDs instead of trying to reproduce the natural-language router.

## 19. Coverage behavior

An empty at-risk list does not automatically mean all candidates are safe.

Batch output explicitly distinguishes:

```text
High
Moderate
Low
Unbanded
```

Unbanded formats may be `Not Assessed`, `Partially Assessed`, or `Needs Assessment` because evidence is insufficient or a critical question is unresolved.

Similarly, the broad draft framework can answer individual questions while suppressing an overall band because `banding_enabled=false`.

## 20. Evidence-gap/remediation workflow

Human examples:

```text
Which PDF formats need more evidence and what is missing?
Why can't PDF 1.7 be assessed?
What should we fix first so the PDF family can be assessed?
```

Machine equivalents:

```json
{
  "action": "list_evidence_gaps",
  "filters": {"family": "PDF"},
  "scope": "global",
  "limit": 500
}
```

```json
{
  "action": "plan_evidence_remediation",
  "filters": {"family": "PDF"},
  "scope": "global",
  "limit": 500
}
```

The deterministic remediation planner distinguishes mapping work, new evidence acquisition, and framework-alignment review.

## 21. Troubleshooting

### `registry_builder is not importable`

Install the sibling builder package in the same environment when using `--storage-config`:

```powershell
cd ..\qnl_format_registry_builder
python -m pip install -e ".[mongo]"
```

### Format is ambiguous

Use a more specific canonical ID or authority identifier. The resolver intentionally does not guess when multiple formats genuinely match.

### Many questions are unknown

Use evidence-gap/remediation actions. The likely causes are:

- no matching source evidence;
- source evidence exists but no criterion mapping;
- criterion claim exists but value is not mapped to a framework answer;
- framework question requires a new evidence field;
- institution-specific evidence has not been supplied.

### No overall risk band with the broad framework

Expected: `qnl_preservation_risk_questions.framework.draft.json` has banding disabled until calibration is approved.

## 22. Tests

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev,ai]"
pytest -q
```

For changes to routing/providers, run the provider capability checks where appropriate. For framework changes, test both deterministic question derivation and human/machine request paths.

## Related documentation

- Documentation map: [`DOCUMENTATION_MAP.md`](DOCUMENTATION_MAP.md)
- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Human/system queries: [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- Question domains: [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md)
- AI providers: [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md)
- Shared data/store interface: [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
