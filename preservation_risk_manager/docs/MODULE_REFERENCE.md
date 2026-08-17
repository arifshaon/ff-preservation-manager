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
| `integration_cli.py` | Human `ask` and machine `query-json` commands; constructs reader/framework/router execution and selects human vs JSON output. |
| `request_api.py` | Canonical structured request validation/execution for human-routed and system requests. Defines supported actions, family/general search, ranking and batch output. |
| `human_renderer.py` | Converts canonical request results into detailed preservation-professional prose for human `ask` mode. |

## Registry/data access

| Module | Responsibility |
| --- | --- |
| `data_access.py` | `RegistryReader`, storage-config loading, export-backed `JsonRegistryStore`, institution-scope filtering, strong-ID expansion for claims. Export mode also loads sibling `criterion_claims.jsonl/json`. |
| `format_resolver.py` | Conservative resolution of canonical IDs, authority IDs, names, aliases, MIME types and extensions; reports ambiguity rather than guessing. |
| `evidence_packs.py` | Builds normalized global/institution evidence packs, applies review-status filtering, deduplicates normalized vs legacy evidence and produces evidence hashes. |
| `currency.py` | Evidence/source currency helpers used to reason about age/currentness where supported. |

## Framework and deterministic analysis

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
| `config.py` | AI provider configuration loader, environment-key resolution and redacted configuration display. |
| `factory.py` | Resolves configured provider type to implementation. |
| `cli.py` / `__main__.py` | AI provider diagnostic commands such as info/query/structured/tool validation. |
| `analysis.py` | Bounded `fill-gaps` interpretation of unresolved deterministic framework questions. |
| `review.py` | Independent `review-all` calibration path using raw-source-only evidence views and post-response comparison. |
| `request_router.py` | Natural-language question → canonical structured request. AI routes intent/parameters; it does not calculate risk. |
| `providers/azure_openai.py` | Azure OpenAI adapter. |
| `providers/openai_compatible.py` | OpenAI-compatible hosted/local adapter for local servers and compatible APIs. |

## Main dependency flow

```text
integration_cli / cli
        |
        +--> data_access -> RegistryStore
        |
        +--> format_resolver
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
        +--> canonical result
                |
                +--> human_renderer
                +--> JSON
```

AI-enabled paths add one of:

```text
request_router
fill-gaps analysis
review-all comparison
```

without replacing the deterministic scoring layer.

## Where to make changes

| Change | Primary module(s) |
| --- | --- |
| Add a new structured request action | `request_api.py`, router schema/examples, tests, human renderer if human output is needed |
| Change format resolution | `format_resolver.py` + regression tests |
| Change storage/backend access | registry-builder `RegistryStore`; only `data_access.py` for read-side adaptation |
| Add a framework field/semantic | `frameworks.py` + framework JSON/tests |
| Change evidence→answer mapping semantics | `answer_derivation.py` and/or framework-local `evidence_value_map` |
| Change scoring/band policy | framework JSON + `scoring.py` only if engine behavior changes |
| Add gap/remediation category | `evidence_gaps.py` / `evidence_remediation.py` |
| Change human prose | `human_renderer.py`; do not duplicate assessment logic there |
| Add AI provider | `ai/base.py`, provider implementation, `ai/factory.py`, provider tests |
| Change human routing | `ai/request_router.py`; keep canonical action execution in `request_api.py` |

## Design boundary

Business logic should not drift into the CLI, renderer or provider adapters.

Preferred rule:

```text
CLI/router chooses operation
core modules determine result
renderer/provider only presents/transports it
```

## Related documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)
