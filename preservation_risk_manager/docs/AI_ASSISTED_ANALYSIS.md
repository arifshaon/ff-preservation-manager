# AI-assisted preservation analysis

AI support is optional and bounded by the preservation application.

The application owns:

```text
registry evidence
format resolution
framework questions
controlled answers
scoring
risk bands
gap/remediation logic
policy approval boundaries
```

The AI provider supplies language-model inference only.

## Supported provider styles

- Azure OpenAI
- OpenAI-compatible hosted/local endpoints

Provider-neutral setup details: [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md).

## Install AI support

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev,ai]"
```

## Azure example

Copy:

```powershell
New-Item -ItemType Directory -Force config | Out-Null
Copy-Item examples\ai.azure.example.json config\ai.local.json
```

Then replace the deployment/API-key placeholders locally. Do not commit real secrets.

## Local model example

The repository now ships:

```text
examples/ai.local.example.json
```

Example:

```json
{
  "ai": {
    "provider": "openai_compatible",
    "endpoint": "http://127.0.0.1:8000/v1",
    "model": "<LOCAL_MODEL_NAME>",
    "temperature": 0.0,
    "max_output_tokens": 1200,
    "timeout_seconds": 60
  }
}
```

Copy it to a local config:

```powershell
Copy-Item examples\ai.local.example.json config\ai.local.json
```

Set `endpoint` and `model` to match the local server. An API key is optional for compatible local servers that do not require one.

## Validate configuration

No network call:

```powershell
python -m preservation_risk_manager.ai info `
  --config config\ai.local.json
```

Provider smoke test:

```powershell
python -m preservation_risk_manager.ai query `
  --config config\ai.local.json `
  --prompt "Reply with a short confirmation."
```

Structured-output capability:

```powershell
python -m preservation_risk_manager.ai validate-structured `
  --config config\ai.local.json
```

Tool-calling capability:

```powershell
python -m preservation_risk_manager.ai validate-tools `
  --config config\ai.local.json
```

## Mode 1: human-question routing

Command:

```powershell
python -m preservation_risk_manager ask `
  "What are the software dependency risks of PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

AI responsibility:

```text
natural language
 -> controlled request action/parameters
```

AI does **not** calculate the risk result.

The canonical request is executed by deterministic application code, then rendered for the human.

Use `--json` to inspect the router's raw request and any deterministic route repairs.

## Mode 2: `fill-gaps`

Command:

```powershell
python -m preservation_risk_manager analyze-format-ai `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --ai-config config\ai.local.json `
  --ai-mode fill-gaps
```

Purpose:

- deterministic derivation runs first;
- only unresolved/ambiguous questions are eligible for AI interpretation;
- AI receives bounded registry evidence;
- the returned answer must be one of the framework-declared answer IDs;
- fabricated evidence references are rejected;
- deterministic evidence remains unchanged.

Use this mode when the evidence exists but deterministic mappings cannot yet fully interpret it.

It is **not** permission for the model to use outside general knowledge.

## Mode 3: `review-all`

Command:

```powershell
python -m preservation_risk_manager analyze-format-ai `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --ai-config config\ai.local.json `
  --ai-mode review-all
```

Purpose: calibration and quality assurance.

The model is given a raw-source-only review view and independently answers eligible framework questions. It is not shown deterministic answers/scores as review evidence.

After response, the application compares AI answers with deterministic answers and records agreements/divergences.

A divergence does **not** automatically change the deterministic result.

## Raw-evidence review boundary

`review-all` deliberately excludes normalized/scoring leakage such as:

```text
normalized mapped value
answer_id
mapping_rule_id
score
band
posture
deterministic derivation status
```

The review view retains source-level information such as source identity, source field/value, raw text and provenance where available.

If usable raw payload is absent, the question may be skipped rather than letting AI infer from normalized conclusions.

## AI and policy proposals

`propose-policy-change` produces a bounded proposal package for human approval.

Example:

```powershell
python -m preservation_risk_manager propose-policy-change `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --institution qnl `
  --goal "Review whether the local preservation action should change"
```

This does not automatically write institutional policy.

## AI and source mapping

The registry builder also contains an AI **mapping-draft** workflow. That is separate from risk analysis.

For example, an AI agent can be given a DPC Bit List export, the neutral criteria vocabulary, exact adapter field profile, accepted examples and negative rules, then asked to return an unreviewed mapping JSON draft.

AI cannot approve its own mapping.

See:

[`../../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)

## Safety rules

1. AI must not invent evidence.
2. AI must not silently change canonical registry data.
3. AI must not alter deterministic resolved answers merely because it disagrees.
4. AI must return framework-declared controlled answers for assessment tasks.
5. AI-generated mapping/policy changes remain drafts until human approval.
6. Local/institution evidence remains institution-scoped.
7. Provider/model identity and usage metadata should be retained for audits.

## Choosing a mode

| Need | Mode |
| --- | --- |
| Human asks natural-language question | `ask` routing |
| Machine already knows action | `query-json` — no AI |
| Interpret unresolved evidence | `fill-gaps` |
| Calibrate/check deterministic mappings | `review-all` |
| Test deterministic engine only | `analyze-format` |
| Draft policy/action proposal | `propose-policy-change` |

## Related docs

- [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md)
- [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
