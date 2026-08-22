# Preservation Risk Manager module reference

This document maps the Python package to responsibilities so maintainers can understand where behavior belongs.

Package:

```text
preservation_risk_manager/src/preservation_risk_manager/
```

## Entry points and interfaces

| Module | Responsibility |
| --- | --- |
| `__main__.py` | Top-level module dispatch. Routes `ask` and `query-json` to the integration CLI; other commands to the analysis CLI. |
| `cli.py` | Deterministic single-format analysis, AI-assisted analysis, fixture analysis, policy-proposal CLI, registry/storage argument handling. |
| `integration_cli.py` | Human `ask` and machine `query-json` commands; constructs reader/framework/router execution, optional format-identification AI plugin, optional overall AI synthesis, and selects human vs JSON output. |
| `request_api.py` | Canonical structured request validation/execution for human-routed and system requests. Defines supported actions, family/general search, ranking and batch output. |
| `human_renderer.py` / `human_renderer_multi.py` | Converts canonical results into preservation-professional prose, including governed and AI-assisted synthesis audit information. |

## Registry/data access and format identification

| Module | Responsibility |
| --- | --- |
| `data_access.py` | `RegistryReader`, storage-config loading, export-backed `JsonRegistryStore`, institution-scope filtering, strong-ID expansion for claims. Export mode also loads sibling `criterion_claims.jsonl/json`. |
| `format_resolver.py` | Conservative exact resolution of canonical IDs, authority IDs, names, aliases, MIME types and extensions; reports ambiguity rather than guessing. |
| `format_identification.py` | Front-end identification orchestration. Applies safe syntax normalization, creates fuzzy local candidate shortlists, supports the `FormatIdentificationPlugin` protocol, implements bounded `AIFormatIdentificationPlugin`, preserves programmatic fallback on AI errors, and blocks unsafe AI arbitration of strong-ID/extension/MIME ambiguities. |
| `evidence_packs.py` | Builds normalized global/institution evidence packs, applies review-status filtering, deduplicates normalized vs legacy evidence and produces evidence hashes. |
| `currency.py` | Evidence/source currency helpers used to reason about age/currentness where supported. |

The intended boundary is:

```text
format observation / PUID / DROID-Siegfried output
        ↓
IdentificationResolver
        ↓
FormatResolver
        ↓ optional bounded plugin fallback
CanonicalFormat
        ↓
evidence/risk workflow
```

The risk engine does not need to know whether the upstream observation came from a human, AIP metadata, DROID, Siegfried, or another service.

## Governed source-risk synthesis

| Module | Responsibility |
| --- | --- |
| `synthesis_policy.py` | Loads and executes the versioned source-risk synthesis policy. Maps approved source-native risk labels/scores into semantic levels, applies scope precedence, and combines same-scope results conservatively. |
| `risk_context.py` | Assembles source risk assessments, governed/config synthesis, compatibility views, and provenance needed by human/system output and AI synthesis. |
| `source_evidence.py` | Supplies source-native evidence for review/AI context without turning raw records into deterministic scores. |

This path is separate from the draft 22-question framework. A source may contribute an overall governed risk assessment, criterion evidence, both, or neither.

## Framework and deterministic question analysis

| Module | Responsibility |
| --- | --- |
| `frameworks.py` | Parses/validates framework JSON: questions, answers, domains, guidance, applicability, evidence maps, weights, scales and calibration/banding state. |
| `answer_derivation.py` | Maps framework-declared evidence fields to controlled answers. Handles missing evidence, unknown values and conservative conflict resolution. |
| `scoring.py` | Calculates weighted scores, completeness, analysis status, suppression reasons and overall band when permitted. |
| `question_assessment.py` | Lists/filter question catalog and performs targeted question/domain/content-type assessment. |
| `posture.py` | Computes local institutional risk posture from analysed band plus separately supplied readiness/exposure context. |
| `actions.py` | Deterministic preservation-action context/logic used by local decision workflows. |
| `responses.py` | Shared response/formatting structures used by deterministic workflows. |

## Evidence gaps and remediation

| Module | Responsibility |
| --- | --- |
| `evidence_gaps.py` | Diagnoses why framework questions cannot be answered: no matching evidence, matched-but-unmapped evidence, unrelated claims and related gap classifications. |
| `evidence_remediation.py` | Converts diagnosed gaps into deterministic remediation items such as mapping-rule work, evidence acquisition and framework-alignment review with priorities. |

## Policy/proposal boundary

| Module | Responsibility |
| --- | --- |
| `policy_proposals.py` | Builds bounded evidence-grounded proposal packages for human review. It does not automatically alter institutional policy. |

## Error model

| Module | Responsibility |
| --- | --- |
| `errors.py` | Package-specific error base/classes used to keep failures explicit and testable. |

## AI package

Directory:

```text
preservation_risk_manager/ai/
```

| Module/area | Responsibility |
| --- | --- |
| `base.py` | Provider-neutral request/response/tool/usage contracts and AI error classes. |
| `config.py` | AI provider configuration loader, TPM/output budgeting settings, environment-key resolution and redacted configuration display. |
| `factory.py` | Resolves configured provider type to implementation. |
| `cli.py` / `__main__.py` | AI provider diagnostic commands such as info/query/structured/tool validation. |
| `analysis.py` | Bounded `fill-gaps` interpretation of unresolved deterministic framework questions. |
| `review.py` | Independent `review-all` calibration path using raw-source-only evidence views and post-response comparison. |
| `request_router.py` | Natural-language question → canonical structured request. AI routes intent/parameters; it does not calculate the underlying registry result. |
| `capability_synthesis.py` | Builds the complete overall-synthesis context, applies token budgeting/privacy boundary, performs one provider call, and returns AI-assisted preservation-risk analysis. |
| `capability_result.py` | Normalizes public AI synthesis output, checks the AI-reported relation to the governed baseline, and surfaces consulted external URLs for audit. |
| `providers/azure_openai.py` | Azure OpenAI adapter, including Responses + hosted `web_search` capability for eligible global synthesis. |
| `providers/openai_compatible.py` | OpenAI-compatible hosted/local adapter. Uses the compatible chat/structured-output contract and does not advertise Azure-style hosted web search. |

`format_identification.py` deliberately sits outside the AI package because identification orchestration is not inherently AI-driven. Its AI implementation consumes the provider-neutral `AIProvider` interface as an optional plugin.

## Main dependency flow

```text
integration_cli / cli
        |
        +--> data_access -> RegistryStore
        |
        +--> format_identification
        |      |
        |      +--> format_resolver
        |      +--> optional AIFormatIdentificationPlugin
        |
        +--> risk_context / synthesis_policy
        |
        +--> evidence_packs
        |
        +--> frameworks
        |
        +--> answer_derivation
        |
        +--> scoring
        |
        +--> gap/remediation/posture/action layers
        |
        +--> optional capability-driven AI synthesis
        |
        +--> canonical result
                |
                +--> human renderer
                +--> JSON
```

AI-enabled paths may add one or more of:

```text
request routing
format-identification candidate selection
overall AI-assisted synthesis
fill-gaps analysis
review-all comparison
```

The governed/config synthesis and source-native evidence remain separately visible and are not rewritten by AI output.

## Where to make changes

| Change | Primary module(s) |
| --- | --- |
| Add a new structured request action | `request_api.py`, router schema/examples, tests, human renderer if human output is needed |
| Change exact format resolution | `format_resolver.py` + regression tests |
| Change format-observation normalization or fallback identification | `format_identification.py` + `test_format_identification.py` |
| Add another identification plugin | Implement `FormatIdentificationPlugin`; wire it through integration/configuration without changing the risk engine |
| Change storage/backend access | registry-builder `RegistryStore`; only `data_access.py` for read-side adaptation |
| Change governed source-risk synthesis | synthesis policy JSON and `synthesis_policy.py` only when generic engine behavior changes |
| Add a framework field/semantic | `frameworks.py` + framework JSON/tests |
| Change evidence→answer mapping semantics | `answer_derivation.py` and/or framework-local `evidence_value_map` |
| Change scoring/band policy | framework JSON + `scoring.py` only if engine behavior changes |
| Add gap/remediation category | `evidence_gaps.py` / `evidence_remediation.py` |
| Change human prose | human renderer modules; do not duplicate assessment logic there |
| Add AI provider | `ai/base.py`, provider implementation, `ai/factory.py`, provider tests |
| Change overall AI synthesis | `ai/capability_synthesis.py` / `ai/capability_result.py`; preserve governed baseline/source evidence independently |
| Change human routing | `ai/request_router.py`; keep canonical action execution in `request_api.py` |

## Design boundary

Business logic should not drift into the CLI, renderer or provider adapters.

Preferred rule:

```text
CLI/router chooses operation
identification layer resolves canonical format
core modules assemble governed evidence/result
optional AI synthesis analyses supplied context
renderer/provider presents/transports it
```

## Related documentation

- Repository architecture: [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- [`FORMAT_IDENTIFICATION.md`](FORMAT_IDENTIFICATION.md)
- [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)
