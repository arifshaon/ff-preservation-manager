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
| `integration_cli.py` | Human `ask` and machine `query-json` commands; constructs reader/framework/router execution, optional format-identification AI plugin, and selects human vs JSON output. |
| `request_api.py` | Canonical structured request validation/execution for human-routed and system requests. Defines supported actions, family/general search, ranking and batch output. |
| `human_renderer.py` | Converts canonical request results into detailed preservation-professional prose for human `ask` mode. |

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

## Framework and deterministic analysis

| Module | Responsibility |
| --- | --- |
| `frameworks.py` | Parses/validates framework JSON: questions, answers, domains, guidance, applicability, evidence maps, weights, scales and calibration/banding state. |
| `answer_derivation.py` | Maps framework-declared evidence fields to controlled answers. Handles missing evidence, unknown values and conservative conflict resolution. |
| `scoring.py` | Calculates weighted scores, completeness, analysis status, suppression reasons and overall band when permitted. |
| `composite_risk.py` | Deterministic composite obsolescence risk index (NARA baseline + weighted LoC sustainability + temporal term). Advisory, additive, outside the AI boundary. See [`COMPOSITE_RISK_INDEX.md`](COMPOSITE_RISK_INDEX.md). |
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
| `literature_corpus.py` | Ingests dropped PDFs/OCR text into a versioned, page-attributed chunk store with a BM25 index. Chunk IDs are content-derived so criterion claims citing them stay replayable. See [`LITERATURE_CORPUS.md`](LITERATURE_CORPUS.md). |
| `training_corpus.py` | Builds the versioned, leakage-tiered fine-tuning corpus for the risk-answer interpreter. Reuses the inference prompt/evidence path so training and production prompts cannot drift, and fails the build on a quality-gate violation. See [`TRAINING_CORPUS.md`](TRAINING_CORPUS.md). |

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

AI-enabled paths may add one or more of:

```text
request_router
format-identification candidate selection
fill-gaps analysis
review-all comparison
```

without replacing the deterministic scoring layer.

## Where to make changes

| Change | Primary module(s) |
| --- | --- |
| Add a new structured request action | `request_api.py`, router schema/examples, tests, human renderer if human output is needed |
| Change exact format resolution | `format_resolver.py` + regression tests |
| Change format-observation normalization or fallback identification | `format_identification.py` + `test_format_identification.py` |
| Add another identification plugin | Implement `FormatIdentificationPlugin`; wire it through integration/configuration without changing the risk engine |
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
identification layer resolves canonical format
core modules determine preservation result
renderer/provider only presents/transports it
```

## Related documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`FORMAT_IDENTIFICATION.md`](FORMAT_IDENTIFICATION.md)
- [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`AI_ASSISTED_ANALYSIS.md`](AI_ASSISTED_ANALYSIS.md)