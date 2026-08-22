# AI-assisted preservation analysis

AI support is optional and bounded by the preservation application.

The application owns:

```text
registry evidence
format resolution
source-native assessments
configured source mappings
synthesis policy
framework questions
controlled answers
scoring
gap/remediation logic
policy approval boundaries
```

AI has different permissions depending on the explicitly selected mode. The normal evidence source remains the QNL format registry.

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

Then replace deployment/API-key placeholders locally. Do not commit real secrets.

The Azure example contains an optional `web_research` block. It is disabled by default.

## Local model example

The repository ships:

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

Copy it to a local config and set `endpoint` and `model`. An API key is optional for compatible local servers that do not require one.

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

The canonical request is executed by application code. Routing does not itself calculate preservation risk.

## Mode 2: `synthesize`

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --ai-mode synthesize
```

There are two controlled behaviors under the same mode.

### Without web research

The application starts with governed source assessments and the versioned synthesis policy. If all source-level risk is already understood by configuration, no AI call is needed. AI is used only when an explicit source-native risk value remains unmapped or when policy permits synthesis from supplied supporting evidence.

### With web research explicitly enabled

Azure provider config:

```json
{
  "ai": {
    "provider": "azure_openai",
    "web_research": {
      "enabled": true,
      "allowed_domains": [],
      "blocked_domains": []
    }
  }
}
```

The workflow changes to:

```text
registry evidence
 -> config-driven governed synthesis baseline
 -> cited public-web verification/supplementation
 -> policy-guided AI-assisted synthesis
```

This is **not** an independent AI opinion and is not a generic search for "the risk of PDF". Research begins with the actual NARA/DPC/LOC/PRONOM and other evidence available for the resolved canonical format.

The web-grounded research may:

- confirm existing evidence;
- identify that a source statement has become stale or needs qualification;
- contradict an existing preservation-relevant claim with newer authoritative evidence;
- add current evidence about specification/governance, tooling, adoption, dependencies, migration, rights/DRM, or metadata characteristics.

Source-native assessments and configured mappings remain immutable. Missing evidence still contributes nothing. Web findings are retained with URLs/citations and are not automatically persisted to MongoDB.

Because public web grounding is an external service, institution-scoped evidence and private/local operational details are excluded from the web-search payload.

Full design: [`AI_RESEARCH_ASSISTED_SYNTHESIS.md`](AI_RESEARCH_ASSISTED_SYNTHESIS.md).

## Mode 3: `fill-gaps`

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
- only unresolved/ambiguous questions are eligible;
- AI receives bounded registry evidence;
- returned answers must use framework-declared answer IDs;
- fabricated evidence references are rejected;
- deterministic evidence remains unchanged.

Question-level `fill-gaps` is **not** permission to use outside general knowledge. The optional web research described above applies to the overall synthesis stage, not to silently fill individual framework answers from the internet.

## Mode 4: `review-all`

```powershell
python -m preservation_risk_manager analyze-format-ai `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format PDF `
  --ai-config config\ai.local.json `
  --ai-mode review-all
```

Purpose: calibration and quality assurance.

The model is given a raw-source-only review view and independently answers eligible framework questions. It is not shown deterministic answers/scores as review evidence. Divergence is recorded but does not automatically change deterministic answers.

## Raw-evidence review boundary

`review-all` excludes normalized/scoring leakage such as:

```text
normalized mapped value
answer_id
mapping_rule_id
score
band
posture
deterministic derivation status
```

If usable raw payload is absent, the question may be skipped rather than letting AI infer from normalized conclusions.

## AI and policy proposals

`propose-policy-change` produces a bounded proposal package for human approval and does not automatically write institutional policy.

## AI and source mapping

The registry builder has a separate AI **mapping-draft** workflow. AI cannot approve its own mapping.

See:

[`../../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md)

## Safety rules

1. Missing evidence is never interpreted as Low risk.
2. AI must not silently change canonical registry data.
3. Source-native assessments and reviewed mappings remain visible and immutable.
4. Bounded question-level AI must cite supplied evidence and use controlled answers.
5. Web-researched synthesis must start from registry evidence, not replace it with an independent opinion.
6. Web-research findings require citations and are not automatically persisted.
7. Institution-scoped/private evidence is not sent to public web grounding.
8. AI-generated mapping/policy changes remain drafts until human approval.
9. Provider/model identity and usage metadata should be retained for audits.

## Choosing a mode

| Need | Mode |
| --- | --- |
| Human asks natural-language question | `ask` routing |
| Machine already knows action | `query-json` — no AI by default |
| Overall source synthesis, optionally with cited current web verification | `--ai-mode synthesize` |
| Interpret unresolved bounded framework evidence | `fill-gaps` |
| Calibrate/check deterministic mappings | `review-all` |
| Test deterministic engine only | `analyze-format` |
| Draft policy/action proposal | `propose-policy-change` |

## Related docs

- [`AI_RESEARCH_ASSISTED_SYNTHESIS.md`](AI_RESEARCH_ASSISTED_SYNTHESIS.md)
- [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md)
- [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
