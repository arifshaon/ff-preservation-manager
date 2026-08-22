# AI-assisted preservation analysis

AI support is optional. When enabled, the Preservation Risk Manager supplies the model with controlled preservation context while keeping source records, deterministic calculations, and approved policy outside automatic AI write control.

The application owns:

```text
registry evidence and provenance
format resolution
framework questions
controlled deterministic answers
configured synthesis rules
deterministic/config baseline
gap/remediation logic
policy approval boundaries
MongoDB writes
```

The AI provider supplies analysis using the capabilities it actually exposes.

## Supported provider styles

- Azure OpenAI
- OpenAI-compatible hosted/local endpoints

Provider-neutral setup details: [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md).

## Install AI support

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev,ai]"
```

## Configure a provider

Azure example:

```powershell
New-Item -ItemType Directory -Force config | Out-Null
Copy-Item examples\ai.azure.example.json config\ai.local.json
```

Replace deployment/key placeholders locally. Do not commit real secrets.

Optional external-research domain controls are administrative only:

```json
"external_research": {
  "allowed_domains": [],
  "blocked_domains": []
}
```

There is no active `web_research.enabled` gate. If the configured provider exposes web/search capability, the application makes it available and the provider/model decides whether to use it.

## Validate configuration

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

## Human-question routing

```powershell
python -m preservation_risk_manager ask `
  "What are the software dependency risks of PDF?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

For natural-language routing, AI maps the request to a controlled application action. The canonical request is then executed by application code.

## Overall synthesis: `--ai-mode synthesize`

This is the main AI-assisted overall-risk path.

The AI receives:

- resolved format identity;
- all relevant registry/source evidence;
- source-native assessments;
- criterion claims;
- the deterministic/config synthesized risk;
- the versioned synthesis configuration;
- the QNL preservation-risk framework.

The deterministic result is an auditable baseline, not a required AI answer.

The AI may agree or disagree. If it differs, the structured output records the relationship to the governed baseline plus rationale, confidence and uncertainty.

### Capability-driven behavior

The application does not prescribe a mandatory research sequence.

```text
AI provider available
        |
        +-- web/search supported -> capability made available automatically
        |                         -> provider/model may use it or decline it
        |
        +-- web/search unsupported -> continue from supplied evidence
```

A web capability failure does not automatically cancel the AI analysis. The model can still synthesize from the supplied context.

See [`AI_RESEARCH_ASSISTED_SYNTHESIS.md`](AI_RESEARCH_ASSISTED_SYNTHESIS.md).

## Evidence and external-information separation

Source-native records remain source-native records. AI must not silently turn external/model information into a NARA, DPC, LOC or PRONOM statement.

The result can record:

```text
R... / C... / S...  supplied registry evidence refs
W...                 external sources returned by provider capability
```

Evidence-reference use is preferred for audit but is not a hard acceptance gate. If the AI returns a useful assessment without explicitly referencing supplied registry refs, the result is returned with a quality warning so the consumer can decide whether it is sufficient.

## Privacy boundary for public search

Institution-scoped/private operational evidence is excluded from the public-search capability context.

The final AI model call can still receive the full assessment context through the configured AI provider, but public web grounding receives only public/global format evidence and public format identity.

## `fill-gaps`

`fill-gaps` remains a narrower question-level workflow:

- deterministic derivation runs first;
- unresolved/ambiguous questions may be interpreted by AI;
- framework-declared answer IDs are used;
- fabricated evidence references are rejected;
- deterministic resolved answers are not silently replaced.

This workflow is distinct from capability-driven overall synthesis.

## `review-all`

`review-all` is for calibration and QA. It presents a raw-source-oriented review view and compares controlled AI answers with deterministic answers.

A divergence is a review signal; it does not automatically change mappings, deterministic scoring or policy.

## Data-integrity rules

AI-assisted analysis does not automatically:

1. rewrite canonical registry data;
2. rewrite NARA/DPC/LOC/PRONOM source-native records;
3. change reviewed source mappings;
4. persist new external findings as approved evidence;
5. overwrite the deterministic/config baseline;
6. convert missing evidence into Low risk.

The AI-assisted result is returned alongside the governed baseline for the consumer to evaluate.

## Example overall-risk command

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --ai-mode synthesize
```

Expected output distinguishes:

```text
AI-assisted synthesized risk
Governed/config baseline
source assessments
AI rationale
capabilities available
capabilities actually used
external sources if returned
quality warnings
uncertainty
```

## Choosing a mode

| Need | Mode |
| --- | --- |
| Natural-language routing only | `ask` with AI mode off |
| AI-assisted overall synthesized risk | `--ai-mode synthesize` |
| Interpret unresolved framework questions | `--ai-mode fill-gaps` |
| Calibration/QA review | `--ai-mode review-all` |
| Deterministic engine only | `query-json` / `analyze-format` without AI |

## Related docs

- [`AI_RESEARCH_ASSISTED_SYNTHESIS.md`](AI_RESEARCH_ASSISTED_SYNTHESIS.md)
- [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md)
- [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
