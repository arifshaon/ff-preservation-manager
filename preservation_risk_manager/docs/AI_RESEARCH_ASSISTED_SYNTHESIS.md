# AI Research-Assisted Preservation-Risk Synthesis

## Purpose

When AI web research is enabled, the Preservation Risk Manager does **not** ask the model to independently determine the preservation risk of a format from scratch.

The collected registry evidence remains the primary evidence base. AI web research is an augmentation layer used to verify, qualify, update, or supplement that evidence before producing an AI-assisted synthesis.

The workflow is:

```text
MongoDB / governed registry evidence
        |
        v
Config-driven normalization and synthesis
        |
        |  governed baseline
        v
AI web research (explicit opt-in)
        |
        |-- verify source accuracy/currentness
        |-- confirm or qualify existing findings
        |-- find current supporting evidence for material gaps
        |-- retain URLs/citations
        v
Policy-guided AI synthesis
        |
        v
AI-assisted synthesized risk
+ governed baseline
+ source-native assessments
+ verification findings
+ web citations
```

This is deliberately **not**:

```text
format name -> AI general knowledge -> independent risk opinion
```

and it is not a generic web search for "the risk of PDF".

## Governed baseline remains visible

Before any web research, the normal versioned synthesis policy is applied to the source assessments already available in the registry.

That baseline continues to preserve the established rules:

- missing sources contribute nothing;
- source-native values are retained;
- configured source mappings are binding;
- the most-specific populated assessment scope determines the baseline headline;
- same-scope disagreement uses the configured conservative semantic upper bound;
- broader scopes remain context;
- heterogeneous native numeric scales are never averaged.

The web-researched result may be different from the governed baseline when current cited evidence materially confirms, contradicts, qualifies, updates, or supplements the evidence base. The baseline is retained in the result so the change remains auditable.

## What web research should investigate

The research prompt begins with the actual evidence available for the resolved canonical format. It may investigate current authoritative evidence concerning:

- accuracy and currentness of existing source findings;
- specification disclosure and governance;
- active software, viewers, validators, extractors, and open-source tooling;
- adoption and community/ecosystem support;
- platform, hardware, external-asset, plugin, or runtime dependencies;
- migration and conversion pathways;
- intellectual-property, encryption, DRM, or technical-protection constraints;
- metadata and self-documentation characteristics.

The research should prefer primary and authoritative sources such as standards bodies, specification owners, official software/tool projects, national archives and libraries, preservation organizations, and authoritative technical documentation.

Failure to find evidence is not interpreted as Low risk.

## Evidence classes

The research-assisted result keeps database and web evidence distinct.

### Database evidence

Existing registry evidence receives stable references such as:

```text
R001  governed source-level risk assessment
C001  governed criterion claim
S001  linked source-native evidence
```

### Web evidence

Cited web sources receive stable run-local references:

```text
W001
W002
...
```

Each material verification finding states whether it:

- confirms the database evidence;
- contradicts it;
- qualifies or updates it;
- supplements it; or
- remains unclear.

It also records the preservation-risk effect as raising concern, reducing concern, neutral, or uncertain.

## Source integrity boundary

Web research does not rewrite:

- NARA, DPC, LOC, PRONOM, or other source-native statements;
- reviewed source-to-semantic mappings;
- canonical format identity;
- MongoDB source records;
- approved criterion claims.

A web finding can affect the AI-assisted synthesized result, but it is retained as separate researched evidence with citations. The current workflow does not persist these findings to MongoDB.

## Explicit opt-in

Web research is disabled by default and must be enabled in the AI provider configuration:

```json
{
  "ai": {
    "provider": "azure_openai",
    "endpoint": "https://<resource>.openai.azure.com/",
    "deployment": "<deployment>",
    "web_research": {
      "enabled": true,
      "allowed_domains": [],
      "blocked_domains": []
    }
  }
}
```

An empty `allowed_domains` list allows the provider's normal public-web search scope. Organizations can instead restrict research to approved domains.

Web grounding is an external service with separate cost, data-processing, and availability considerations, so it must not be enabled implicitly.

## Azure OpenAI implementation

Normal structured AI requests continue to use Azure OpenAI Chat Completions.

When web research is enabled, the Azure provider additionally uses the Azure OpenAI Responses API with the `web_search` tool. The implementation requires:

- an Azure OpenAI deployment that supports the Responses API and web search;
- web search/grounding to be available and permitted for the subscription/resource;
- a recent OpenAI Python SDK exposing `client.responses`;
- outbound access required by the Azure service configuration.

The application requires an actual `web_search_call`. If the provider returns an ungrounded response, the research step fails closed and the deterministic config-driven synthesis is retained.

## Failure behavior

If web search or the subsequent AI synthesis fails:

```text
AI research/synthesis failed
        -> governed config synthesis retained unchanged
```

The failure is reported in the response rather than silently changing the risk.

## Example

For PDF 1.7 (`fmt/276`) the governed baseline may remain:

```text
NARA exact format: Low concern
DPC PDF group: Moderate concern (broader context)
Governed baseline: Low concern
```

With web research enabled, the AI receives those findings and related LOC/PRONOM evidence first. It then verifies or supplements material preservation facts using cited current sources.

A final output may therefore be:

```text
Overall AI-assisted synthesized risk: Low concern
Governed baseline: Low concern

Web verification:
- current specification/tooling evidence confirms the existing low-risk indicators
- current migration support supplements the registry evidence

or, where justified by current evidence:

Overall AI-assisted synthesized risk: Moderate concern
Governed baseline: Low concern

Web verification:
- cited current evidence qualifies an older source assessment
- the researched synthesis therefore raises the overall concern
```

In either case, the original source assessments remain visible and unchanged.
