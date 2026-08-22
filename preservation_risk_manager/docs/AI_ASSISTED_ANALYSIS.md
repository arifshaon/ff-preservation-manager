# AI-assisted preservation analysis

This is the technical reference for the Risk Manager's AI-assisted analysis layer. Provider setup for operators is documented in [`../../docs/AI_PROVIDERS.md`](../../docs/AI_PROVIDERS.md).

AI is optional. The application supplies the model with collected preservation evidence and methodology while keeping registry evidence, governed synthesis and write authority outside automatic model control.

## Analysis layers

```text
current registry evidence
        |
        v
governed config synthesis   <- auditable application baseline
        |
        +--> framework/question diagnostics
        |
        v
complete bounded AI context
        |
        v
configured provider/model
        |
        v
AI-assisted synthesis       <- separate advisory result
```

The AI result may agree or disagree. It does not silently replace the governed baseline.

## `--ai-mode synthesize`

This is the primary overall-risk AI path.

The model receives:

- resolved format identity;
- governed source-level risk assessments;
- source-native evidence;
- approved criterion claims;
- governed/config baseline;
- active synthesis policy/methodology;
- assessment framework/context.

The prompt asks for structured fields including:

```text
semantic_level
confidence
rationale
database_evidence_refs
considerations
config_rules_considered
governed_baseline_relation
uncertainty
```

The application validates the returned level against the configured semantic vocabulary and deterministically checks the baseline relation. For example, Low vs Low is `same` even if model prose incorrectly reports `higher_concern`.

## Capability-driven behavior

The core does not prescribe a mandatory research sequence.

```text
provider/model capabilities available
        |
        +--> expose supported capabilities when permitted
        |
        +--> model may use or decline them
        |
        v
one final structured synthesis result
```

### Azure OpenAI

The native Azure provider uses one Responses request for global/public synthesis and exposes `web_search` with automatic tool choice.

The runtime audits:

- whether hosted web search was available;
- whether it was actually used;
- search queries returned by the provider;
- consulted URLs;
- citation/source metadata when returned.

### OpenAI-compatible endpoints

The generic compatibility provider uses one structured Chat Completions request and advertises no provider-hosted web-search capability. A vendor-specific native provider can add richer search/grounding later without changing this core contract.

## External information versus registry evidence

AI must not turn external/model information into a false NARA, DPC, LOC, PRONOM or other source statement.

The evidence package uses local references such as:

```text
R... governed/source risk assessment
C... criterion claim
S... source-native supporting evidence
```

External URLs returned by a provider are recorded separately.

Evidence-reference fidelity is a quality/audit signal. Unknown references can be warned about/filtered rather than causing useful model output to become source evidence.

## Missing evidence

Missing information remains missing information.

```text
no supplied evidence
!= Low
!= Moderate
!= High
```

Framework gaps can increase uncertainty/completeness concerns without automatically changing the governed source-level overall risk.

## Privacy boundary

When institution-scoped/private assessment evidence is present, public web-search tooling is suppressed for that synthesis call.

The configured AI provider may still receive the assessment prompt. Provider selection/data handling remains an institutional deployment decision.

## TPM-aware prompt budgeting

Provider config can declare:

```json
{
  "ai": {
    "tokens_per_minute": 10000,
    "max_output_tokens": 1200
  }
}
```

For structured overall synthesis, the runtime may reserve a larger output allowance than the generic helper setting so valid JSON is not cut off mid-object. The prompt budget shrinks correspondingly.

Current policy:

- structured output floor: up to 20% of TPM, capped at 2,000 tokens;
- per-request output ceiling: 25% of TPM;
- safety reserve: 15% of TPM, minimum 500 tokens;
- remaining allowance: estimated prompt budget.

For 10,000 TPM / `max_output_tokens=1200` this normally gives:

```text
generic helper output       1,200
structured synthesis output 2,000
safety reserve              1,500
prompt budget               6,500
```

The prompt builder prioritizes:

1. governed/config-normalized source risk;
2. governed criterion claims;
3. source-native risk assessments;
4. source-native sustainability/documentation evidence;
5. other descriptive evidence.

Budget metadata records evidence supplied/omitted and whether compaction occurred.

A static per-request budget cannot know other concurrent/shared provider usage, so it does not guarantee that a deployment will never return a rate-limit response.

## Response verbosity

Azure Responses verbosity is configurable:

```json
"response_verbosity": "medium"
```

Allowed values in project config are `low`, `medium`, and `high`; provider/model support can differ. The default is `medium` because the validated deployment supports it.

The synthesis prompt separately asks for concise rationale/considerations.

## Exact AI input logging

Opt in with:

```json
"input_log_file": "logs/ai-inputs.jsonl"
```

The provider wrapper appends the actual post-budget request handed to the model, including messages, structured-output schema, token allowance and capability options.

Credentials are not logged, but prompt/evidence content can be sensitive. Protect this file and do not commit it.

## Quality warnings

A useful model result is not automatically rejected because:

- web capability was available but not used;
- it omitted explicit database evidence refs;
- it returned an unknown evidence ref alongside valid evidence;
- prose was more cautious than its semantic level.

The application retains quality warnings so the consumer can judge the result while preserving the governed baseline.

## `fill-gaps`

`fill-gaps` is the older/narrower question-level interpretation workflow:

```text
deterministic framework derivation
 -> only unresolved/ambiguous questions
 -> bounded AI interpretation
```

It does not replace already-resolved deterministic answers and is not the primary periodic overall-risk synthesis mode.

## `review-all`

`review-all` is a calibration/QA mode that compares AI interpretation of supplied raw/source evidence with deterministic framework answers. Divergence is a review signal, not an automatic policy/mapping change.

## Authority boundary

AI-assisted analysis does not automatically:

1. rewrite canonical identity;
2. rewrite source-native records;
3. approve/change mappings;
4. persist web/model findings as source evidence;
5. overwrite governed synthesis;
6. convert missing evidence into Low risk;
7. write institutional policy.

## Main command

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --ai-mode synthesize
```

## Related documentation

- Operator/provider setup: [`../../docs/AI_PROVIDERS.md`](../../docs/AI_PROVIDERS.md)
- Risk terminology/governance: [`RISK_SYNTHESIS_AND_TERMINOLOGY.md`](RISK_SYNTHESIS_AND_TERMINOLOGY.md)
- AI provider developer contract: [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md)
- Input logging: [`AI_INPUT_LOGGING.md`](AI_INPUT_LOGGING.md)
- Monitoring/batch reports: [`RISK_MONITORING_AND_REPORTING.md`](RISK_MONITORING_AND_REPORTING.md)
