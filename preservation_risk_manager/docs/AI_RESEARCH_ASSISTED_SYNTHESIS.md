# AI Capability-Driven Preservation-Risk Synthesis

## Purpose

When AI mode is enabled, the Preservation Risk Manager gives the AI client the preservation context already assembled by the application:

- resolved canonical format identity;
- governed source-level risk assessments;
- source-native evidence;
- approved criterion claims;
- the deterministic/config synthesis;
- the QNL synthesis configuration;
- the preservation-risk question framework.

The application does **not** prescribe a mandatory research sequence and does not require the AI to reproduce the deterministic result.

The AI client may use whatever capabilities it actually exposes. If web search is available, the capability is made available automatically and the provider/model decides whether to use it. If web search is unavailable, unsupported, fails, is suppressed for privacy, or is simply not useful, the AI can still analyse the supplied evidence.

## Workflow

```text
MongoDB / governed registry evidence
        |
        v
Config-driven deterministic synthesis
        |
        |  auditable baseline
        v
Complete AI context
  - registry evidence
  - source-native findings
  - framework
  - synthesis configuration
  - deterministic baseline
        |
        v
Configured AI client
        |
        |-- web/search capability available? make it available
        |-- provider/model may use it or decline it
        |-- institution/private evidence present? suppress public web capability
        |-- other model capabilities may also inform analysis
        v
AI-assisted synthesized risk
        |
        +-- confidence / rationale / uncertainty
        +-- relation to governed baseline
        +-- registry refs when supplied by model
        +-- external sources when returned
        +-- capability availability/use audit
```

The deterministic/config result and AI-assisted result remain separate and visible so the consumer can decide how to use them.

## What is not prescribed

The application does not tell the AI that it must:

- browse the web;
- run a fixed set of searches;
- cite both a registry ref and a web ref before its result can be returned;
- agree with the deterministic/config result;
- apply the deterministic source mappings as binding rules on its own synthesized conclusion.

Instead, those mappings and rules are supplied as methodology context. If the AI differs from the governed baseline, it should explain why.

## Data-integrity boundaries

AI freedom does not mean source data is rewritten.

The AI-assisted workflow does not automatically modify:

- NARA, DPC, LOC, PRONOM, or other source-native records;
- configured source mappings;
- canonical format identity;
- MongoDB source records;
- approved criterion claims;
- the deterministic/config synthesis.

AI output is returned to the consumer and is not automatically persisted as approved registry evidence.

## Missing evidence

Missing information remains missing information. It is not converted to Low, Moderate, or High simply because a source is silent.

The deterministic policy continues to use:

```text
missing source assessment -> contributes nothing
```

The AI receives that policy and the available evidence as context.

## External capabilities

There is no `web_research.enabled` decision switch in the active model.

Provider capability determines availability:

```text
AI enabled
    |
    +-- provider supports web search -> expose it with provider/model automatic choice
    |
    +-- provider does not support web search -> continue without it
```

Optional administrative domain controls remain available:

```json
{
  "ai": {
    "provider": "azure_openai",
    "endpoint": "https://<resource>.openai.azure.com/",
    "deployment": "<deployment>",
    "external_research": {
      "allowed_domains": [],
      "blocked_domains": []
    }
  }
}
```

The historical `web_research.enabled` property is accepted for backward compatibility but no longer controls capability availability.

## Azure OpenAI

For Azure OpenAI, global/public overall synthesis uses one Responses API request. The `web_search` tool is exposed with automatic tool choice, so the model may call it or decline it. The same response returns the final structured synthesis.

For structured Responses output, the provider requests low response verbosity to reduce avoidable output growth while preserving the required JSON fields.

The runtime records:

- whether web search capability was available;
- whether the capability request could be made;
- whether the model actually used web search;
- search queries and URLs when returned;
- external citations when returned;
- any capability error.

## Tokens-per-minute budgeting

AI provider configuration may declare the deployment's tokens-per-minute quota:

```json
{
  "ai": {
    "tokens_per_minute": 10000,
    "max_output_tokens": 1200
  }
}
```

`max_output_tokens` remains the normal limit for request routing and other AI helpers. Overall structured synthesis may derive a larger response allowance from `tokens_per_minute`, because a response cut off mid-object is not usable JSON. The synthesis prompt budget shrinks by the same amount so the total request remains within the configured deployment budget.

The current synthesis reserve policy is:

- reserve up to 20% of TPM for structured output, capped at 2,000 tokens;
- never reserve more than 25% of TPM for a single response;
- keep a separate 15% TPM safety reserve, with a minimum of 500 tokens;
- use the remaining allowance for the estimated prompt.

For a 10,000 TPM deployment with `max_output_tokens` set to 1,200:

```text
normal provider max output       1,200
synthesis output reserve         2,000
rate-limit safety reserve        1,500
estimated synthesis prompt       6,500
```

When necessary, the prompt builder compacts evidence in this order:

1. governed/config-normalized source-level risk assessments are retained first;
2. governed criterion claims;
3. source-native risk assessments;
4. source-native sustainability/documentation evidence;
5. other source-native descriptive context.

The synthesis response records the budget decision, including:

- configured TPM;
- configured and effective synthesis maximum output tokens;
- safety reserve;
- prompt token budget;
- conservative estimated prompt tokens;
- evidence items available and supplied;
- omitted evidence refs, if any;
- whether the framework or evidence context had to be compacted.

The estimator deliberately uses a conservative provider-neutral approximation of three characters per token. It is a preflight protection mechanism, not a replacement for provider-reported token usage.

If `tokens_per_minute` is omitted, the existing unbudgeted behavior is preserved.

## Privacy boundary

For global/public format assessments, the single Responses request may expose web search to the model.

When the assessment context contains institution-scoped/private operational evidence, public web-search capability is suppressed for that synthesis call. The AI provider can still analyse the supplied evidence without public web grounding. The response records this as `suppressed_for_institution_evidence=true`.

## Quality warnings rather than hard rejection

If the model returns a useful assessment but does not explicitly reference the supplied registry refs, the application returns the result and records a quality warning rather than rejecting the analysis.

Likewise:

```text
web capability available + web not used
```

is normal audit information, not an error.

The consumer decides whether the AI result is sufficient for its purpose.
