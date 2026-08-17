# Preservation Risk Manager: installation, setup, and run guide

This is the primary operator runbook for `preservation_risk_manager`.

For the shortest path from a fresh checkout to a real criterion-backed assessment, start with **[`../../docs/GETTING_STARTED.md`](../../docs/GETTING_STARTED.md)**. This guide then covers all execution modes in more detail.

## 1. What this module does

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

The risk manager is normally a read/assessment layer. Registry construction and normal registry updates belong to `qnl_format_registry_builder`.

Related architecture:

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
- [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)

## 2. Requirements

- Python 3.10 or later.
- A registry source:
  - a registry-builder storage backend/config, or
  - registry-builder export files.
- Criterion claims when framework-driven assessment is expected.
- The sibling registry-builder package installed when using its storage adapters.
- The optional AI dependency only for `ask`, AI provider utilities, `fill-gaps`, and `review-all`.

## 3. Install both packages

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

Using an existing virtual environment is supported.

### Deterministic export-only use

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev]"
pytest -q
```

## 4. CLI entry point

Use:

```powershell
python -m preservation_risk_manager ...
```

The module dispatcher routes `ask` and `query-json` to the integration interface and other commands to the explicit analysis CLI.

Command reference: [`CLI_REFERENCE.md`](CLI_REFERENCE.md).

## 5. Registry/evidence setup

### Option A — persistent registry backend

Pass a registry-builder storage block or a full builder config containing `storage`.

Example:

```text
..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

The risk manager reuses the registry-builder storage factory through `RegistryReader`; it does not implement separate MongoDB preservation logic.

Example deterministic command:

```powershell
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF
```

### Option B — registry-builder exports

Registry-builder normally exports canonical formats and criterion claims separately:

```text
output\registry.json
output\criterion_claims.jsonl
```

When a risk-manager command receives:

```powershell
--registry-json ..\qnl_format_registry_builder\output\registry.json
```

`JsonRegistryStore` automatically looks in the same directory for:

```text
criterion_claims.jsonl
criterion_claims.json
```

and loads the first matching claim export.

This is the supported export handoff between the two packages.

### Criterion mapping must actually have run

The generic builder config:

```text
qnl_format_registry_builder/config/sources.example.json
```

is primarily a registry-construction example and does **not** enable criterion mapping. A build can therefore contain thousands of canonical formats but still have no criterion claims usable by the risk framework.

For the no-database cross-package quickstart use:

```text
qnl_format_registry_builder/config/sources.criterion-mapping.quickstart.json
```

It enables approved criterion mappings and exports both canonical formats and criterion claims.

Verify before assessing:

```powershell
cd ..\qnl_format_registry_builder
Test-Path output\registry.json
Test-Path output\criterion_claims.jsonl
(Get-Content output\criterion_claims.jsonl | Measure-Object -Line).Lines
```

The claim count should be greater than zero when the intention is criterion-backed assessment.

## 6. Framework setup

### Small scoring example

```text
examples/qnl_sustainability.framework.example.json
```

Purpose:

- exercise deterministic scoring;
- three questions;
- Low/Moderate/High banding enabled.

It is not the final QNL preservation-risk framework.

### Broad draft preservation question set

```text
examples/qnl_preservation_risk_questions.framework.draft.json
```

Purpose:

- 8 domains;
- 22 stable question IDs;
- question/domain-specific evidence assessment;
- human and machine queries;
- evidence-gap/remediation development.

Current status:

```text
calibration_status = draft_unvalidated
banding_enabled = false
```

Question-level conclusions can be returned, but the framework deliberately suppresses an overall Low/Moderate/High band until calibration is approved.

See:

- [`FRAMEWORKS.md`](FRAMEWORKS.md)
- [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md)

## 7. AI provider setup

AI is required for natural-language `ask` routing and AI-assisted analysis modes. It is not required for `query-json` or deterministic `analyze-format`.

### Azure OpenAI

```powershell
New-Item -ItemType Directory -Force config | Out-Null
Copy-Item examples\ai.azure.example.json config\ai.local.json
```

Edit deployment/key values locally and never commit real credentials.

### Local/OpenAI-compatible model

A shipped local template is available:

```powershell
New-Item -ItemType Directory -Force config | Out-Null
Copy-Item examples\ai.local.example.json config\ai.local.json
```

Edit:

```text
endpoint
model
```

to match the local server (for example vLLM, llama.cpp, Ollama or another OpenAI-compatible endpoint).

### Validate the provider

```powershell
python -m preservation_risk_manager.ai info `
  --config config\ai.local.json

python -m preservation_risk_manager.ai query `
  --config config\ai.local.json `
  --prompt "Reply with a short confirmation that the provider is available."

python -m preservation_risk_manager.ai validate-structured `
  --config config\ai.local.json

python -m preservation_risk_manager.ai validate-tools `
  --config config\ai.local.json
```

See [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md) and [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md).

## 8. Human question mode — `ask`

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
 -> AI routes intent/parameters only
 -> canonical request
 -> deterministic registry/framework execution
 -> canonical result
 -> human renderer
```

The AI router does not calculate the preservation-risk result.

### Human routing audit

Add `--json`:

```powershell
python -m preservation_risk_manager ask `
  "Which PDF formats need more evidence and what is missing?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --limit 500 `
  --json
```

This returns the canonical result plus router provider/model/usage, raw routed request and any deterministic route repairs.

## 9. Machine/system mode — `query-json`

A system should use the canonical request API directly when it already knows the intended action.

Example `request.json`:

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

Run:

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

Literal JSON is also supported:

```powershell
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"PDF","scope":"global"}' `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

No AI call occurs.

See [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md).

## 10. Deterministic single-format mode — `analyze-format`

Persistent-store example:

```powershell
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --compact-evidence `
  --evidence-summary
```

Export example:

```powershell
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --registry-json ..\qnl_format_registry_builder\output\registry.json `
  --format PDF `
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

`--include-unapproved` is an investigation/debug option, not the routine approved-evidence path.

## 11. AI-assisted mode — `fill-gaps`

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

- deterministic derivation runs first;
- AI sees only unresolved/ambiguous eligible questions and bounded evidence;
- AI must choose framework-declared answer IDs;
- resolved deterministic answers are not overwritten merely because AI disagrees;
- no usable evidence means the model should not invent an answer.

## 12. Independent AI review — `review-all`

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

The model receives a raw-source-only evidence view without deterministic answers/scores or normalized mapped conclusions. Its answers are compared with deterministic results only after response.

## 13. Fixture mode — `analyze-fixture`

```powershell
python -m preservation_risk_manager analyze-fixture `
  --framework examples\qnl_sustainability.framework.example.json `
  --evidence-pack examples\pdf.evidence_pack.example.json `
  --answers examples\pdf.answers.example.json
```

Useful for framework/scoring tests without a registry backend.

## 14. Policy/action proposal package

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

This creates an evidence-grounded proposal/context package for human review. It does not approve or write policy changes.

## 15. Global vs institution scope

### Global

Institution-scoped claims are excluded.

### Institution

Human mode can use:

```powershell
--institution qnl
```

Machine mode uses:

```json
{
  "scope": "institution",
  "institution_id": "qnl"
}
```

Institution mode includes global evidence plus matching institution-scoped claims.

## 16. Current machine actions

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

Machine clients should use stable action/domain/question IDs rather than reproduce the natural-language router.

## 17. Coverage and band suppression

An empty at-risk list does not mean every candidate is safe.

Batch results distinguish:

```text
High
Moderate
Low
Unbanded
```

For single-format results inspect:

```text
criterion_claims_used
analysis_status
evidence_completeness
missing_count
abstention_count
band_suppressed_reason
analysed_band
```

Current suppression reasons include:

```text
framework_not_calibrated
not_assessed
critical_abstention
insufficient_evidence_completeness
```

Detailed explanation: [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md).

## 18. Evidence gaps/remediation

Human examples:

```text
Why can't PDF 1.7 be assessed?
Which PDF formats need more evidence and what is missing?
What should we fix first so the PDF family can be assessed?
```

Machine examples:

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

## 19. Periodic monitoring/reporting

The machine interface is designed for external schedulers/reporting services.

Typical pattern:

```text
refresh registry sources
 -> verify source health
 -> execute query-json requests
 -> retain dated canonical JSON
 -> compare with prior report
 -> render/distribute dashboard | PDF | email | ticket | API result
```

See [`RISK_MONITORING_AND_REPORTING.md`](RISK_MONITORING_AND_REPORTING.md).

## 20. Troubleshooting

### `criterion_claims_used = 0`

Check whether:

1. the builder config enabled `criterion_mapping`;
2. `criterion_claims.jsonl` exists beside `registry.json` in export mode;
3. the persistent backend actually contains `criterion_claims` in storage mode;
4. the resolved format/strong identifier aliases correspond to the claim records;
5. claims are approved/usable for the requested scope.

Use the root [`../../docs/GETTING_STARTED.md`](../../docs/GETTING_STARTED.md) quickstart to validate the handoff independently.

### `registry_builder is not importable`

Install the sibling package when using `--storage-config`:

```powershell
cd ..\qnl_format_registry_builder
python -m pip install -e ".[mongo]"
```

### Format is ambiguous

Use a canonical ID or authority identifier. The resolver intentionally avoids guessing.

### Broad framework returns no overall band

Expected while `qnl_preservation_risk_questions.framework.draft.json` has `banding_enabled=false`.

## 21. Tests

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev,ai]"
pytest -q
```

Cross-package export changes should include a regression proving that a sibling criterion-claim export reaches deterministic assessment.

## Related documentation

- [`../../docs/GETTING_STARTED.md`](../../docs/GETTING_STARTED.md)
- [`DOCUMENTATION_MAP.md`](DOCUMENTATION_MAP.md)
- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`MODULE_REFERENCE.md`](MODULE_REFERENCE.md)
- [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
- [`FRAMEWORKS.md`](FRAMEWORKS.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)
- [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md)
- [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md)
- [`RISK_MONITORING_AND_REPORTING.md`](RISK_MONITORING_AND_REPORTING.md)
