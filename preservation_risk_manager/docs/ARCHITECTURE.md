# Preservation Risk Manager architecture

`preservation_risk_manager` is the **assessment and access layer** of the repository. It consumes a registry built by `qnl_format_registry_builder`, applies explicit preservation-risk frameworks, and exposes the same assessment through human-readable and machine-readable interfaces.

## Architectural principles

1. **Evidence first.** Risk answers must be traceable to registry evidence and framework rules.
2. **Deterministic scoring is authoritative.** AI does not own scores, bands, local posture, or policy approval.
3. **Backend-neutral access.** Assessment code reads through `RegistryReader`, not MongoDB-specific calls.
4. **One canonical request layer.** Human and machine interfaces execute the same controlled actions.
5. **Unknown is not Low.** Missing or unmappable evidence remains visible and may suppress a band.
6. **Institutional evidence is scoped.** QNL evidence supplements global evidence only in QNL-scoped assessment.
7. **Frameworks are versioned configuration.** Questions, evidence fields, answers, weights, and banding status are explicit.
8. **AI is bounded and auditable.** Routing, fill-gap interpretation, and independent review are separate from deterministic truth.

## End-to-end assessment flow

```text
RegistryStore backend
       |
       v
RegistryReader
       |
       v
FormatResolver
       |
       v
canonical format + strong identity aliases
       |
       v
criterion claims selected by scope
       |
       v
EvidencePack
       |
       v
RiskFramework
       |
       v
answer_derivation
       |
       v
scoring
       |
       +--> evidence-gap diagnosis
       +--> remediation planning
       +--> local posture / policy context
       |
       v
canonical result JSON
       |
       +--> human_renderer
       +--> system/API consumer
```

## Data-access layer

### `data_access.py`

Defines the risk manager's minimal storage dependency:

```python
class RegistryStore(Protocol):
    def query(collection, filt=None) -> list[dict]: ...
```

`RegistryReader` provides higher-level operations over that contract.

It can:

- read current canonical formats;
- get a canonical format by ID;
- gather strong identity aliases (canonical/PUID/LOC/NARA);
- retrieve criterion claims across those identities;
- apply global vs institution evidence scope;
- read legacy format-evidence claims.

When passed a storage config, it lazily calls the sibling registry builder's `create_store(...)`, which centralizes MongoDB/file/plugin behavior.

It can also use `JsonRegistryStore` for exported JSON.

Shared data model: [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md).

## Format resolution

### `format_resolver.py`

Resolves a user's/system's format reference to one current canonical record.

Resolution considers controlled forms such as:

- canonical ID;
- verified authority identifiers;
- authority identifiers;
- exact names/aliases;
- MIME types/extensions where appropriate.

Strong authority identifiers and exact canonical names have precedence over weak/generic matches. Ambiguous matches are returned as ambiguity rather than silently choosing a format.

Family discovery in `request_api.py` is deliberately narrower than general search: a `.pdf` extension or PDF-related identifier does not by itself make a format a member of the PDF family.

## Evidence assembly

### `evidence_packs.py`

Builds a normalized evidence pack for analysis.

Evidence is separated into sections such as:

- global evidence;
- institution evidence;
- migration-pathway evidence;
- local migration readiness.

Current/review-state filtering prevents rejected/superseded/draft evidence from being silently treated as approved unless explicitly requested in modes that support it.

### Scope

Global assessment:

```text
external/global claims only
```

Institution assessment:

```text
global claims
+ claims scoped to the requested institution
```

This keeps local operational limitations from becoming universal statements about a file format.

## Framework model

### `frameworks.py`

Loads and validates `RiskFramework` configuration.

A question can declare:

- `id`
- human label
- domain ID/label
- definition/guidance
- aliases
- applicability/content types
- critical flag
- weight
- evidence fields
- question-local evidence-value mapping
- controlled answers and points

A framework declares:

- ID/version/label/description;
- source basis;
- calibration status;
- unknown answer ID;
- scoring direction;
- completeness threshold;
- score bands;
- whether overall banding is enabled.

Question-local value mappings allow different frameworks to use different controlled answer IDs without changing source adapters or the legacy global map.

## Deterministic answer derivation

### `answer_derivation.py`

For each framework question:

1. inspect only claims whose criterion/field matches the question's declared `evidence_fields`;
2. honor an explicit allowed answer ID when present;
3. otherwise normalize the claim value;
4. map the value using the question-local map first, then the legacy global map as fallback;
5. return a controlled answer or an explicit unresolved status.

Statuses include:

- `derived`
- `missing_evidence`
- `unknown` (matching claims exist but do not map)
- `derived_conflict_conservative`

When mapped evidence conflicts, the deterministic path chooses the highest-risk allowed answer and exposes conflict metadata instead of ignoring the conflict.

It does not infer from general file-format knowledge, extensions, or names.

## Scoring

### `scoring.py`

Consumes only framework-declared answer IDs.

It calculates:

- per-question points and weighted points;
- answered/missing/abstention counts;
- evidence completeness;
- analysis status;
- score/max score;
- overall band when banding is enabled and completeness/critical-question requirements are satisfied.

Band suppression reasons include:

- `not_assessed`
- `critical_abstention`
- `insufficient_evidence_completeness`
- `framework_banding_disabled`

The broad draft 22-question framework deliberately disables overall banding until QNL validates calibration.

## Targeted question assessment

### `question_assessment.py`

Supports assessment of selected domains/questions/content types without requiring the user to interpret the whole framework.

It powers requests such as:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["software_dependencies_environment"]
  }
}
```

It returns each selected question with:

- question/domain metadata;
- controlled answer;
- derivation status;
- points;
- matched evidence;
- question-level evidence gaps;
- selected-set completeness;
- overall framework calibration/banding status.

`list_assessment_questions` uses the same module to expose the question catalog.

## Evidence-gap diagnosis

### `evidence_gaps.py`

Diagnoses why a framework question cannot be answered.

Key distinctions:

```text
no_matching_evidence
  no claim matches the question's evidence field

claims_exist_but_do_not_map
  relevant claim exists but value cannot be mapped to an allowed answer

claims_exist_but_not_for_framework
  the format has claims, but none address active framework fields
```

This prevents all unresolved formats from being lumped into one generic "missing evidence" bucket.

## Evidence remediation

### `evidence_remediation.py`

Converts deterministic evidence-gap states into a bounded action queue.

Current action types:

- `mapping_rule_needed`
- `source_evidence_needed`
- `framework_alignment_review`
- bounded manual review where necessary

Priorities:

- **P1** — critical framework question blocked;
- **P2** — non-critical mapping/normalization work where usable evidence already exists;
- **P3** — non-critical new source-evidence work.

The planner does not invent preservation facts.

## Canonical request interface

### `request_api.py`

This is the shared execution layer for human and machine requests.

Supported actions currently include:

- `assess_format`
- `assess_format_questions`
- `search_formats`
- `assess_format_family`
- `list_at_risk_formats`
- `list_assessment_questions`
- `list_evidence_gaps`
- `plan_evidence_remediation`

`normalize_request(...)` validates/defaults incoming requests; `execute_request(...)` runs them through the same resolver/evidence/framework code.

A web API, scheduler, dashboard, or other integration should wrap this layer rather than reimplement risk logic.

## Human interface

### `integration_cli.py`

Dispatches two integration-oriented commands:

```text
ask
query-json
```

`ask`:

```text
natural-language question
 -> AI request router
 -> normalized canonical request
 -> execute_request
 -> canonical result
 -> human renderer
```

Normal `ask` prints human-readable prose. `ask --json` prints canonical JSON plus router audit metadata.

`query-json` bypasses the AI router and emits canonical JSON only.

### `human_renderer.py`

Transforms canonical results into archivist-facing answers. It renders:

- conclusion/status;
- evidence coverage;
- question-by-question findings;
- supporting evidence provenance;
- missing/unresolved evidence;
- coverage/calibration cautions;
- at-risk lists;
- evidence gaps;
- remediation priorities.

It does not call an AI model to embellish findings.

## Natural-language request routing

### `ai/request_router.py`

The router's only job is to translate a human question into one supported action and parameters.

It must not:

- answer the preservation question;
- estimate risk;
- invent formats;
- supply unsupported evidence.

The result can include audit metadata such as:

- provider/model;
- token usage;
- raw routed request;
- deterministic repair rules applied to mechanically inconsistent routes.

## AI-assisted evidence modes

### `ai/risk_analysis.py`

Supports `fill-gaps`.

AI is given bounded evidence for unresolved questions and may choose only framework-declared answer IDs. It does not overwrite already resolved deterministic questions.

### `ai/review.py`

Supports `review-all` calibration.

The model receives a sanitized raw-source-only evidence view. Deterministic answer/status and normalized mapped values are withheld from the prompt. After the model responds, its controlled answer is compared with deterministic output.

A divergence is evidence for framework/mapping review; it does not automatically change the deterministic result.

## AI provider abstraction

The `ai/` package contains:

- `base.py` — provider-neutral request/response/tool/usage abstractions;
- `config.py` — safe provider configuration loading/redaction;
- `factory.py` — provider selection;
- `providers/azure_openai.py` — Azure OpenAI implementation;
- `providers/openai_compatible.py` — OpenAI-compatible implementation;
- `cli.py` — provider info/smoke/capability validation;
- `request_router.py` — human intent routing;
- `risk_analysis.py` — fill-gap interpretation;
- `review.py` — independent raw-evidence review.

See [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md).

## Local posture and policy context

### `posture.py`

Combines deterministic global risk with institution readiness/exposure inputs to calculate bounded local posture where those modes are used.

### `policy_proposals.py`

Builds a structured evidence-grounded proposal package for human approval. It does not automatically write institutional policy or alter the registry.

## CLI command families

`python -m preservation_risk_manager` dispatches:

```text
ask / query-json
 -> integration_cli

analyze-fixture / analyze-format / analyze-format-ai / propose-policy-change
 -> core cli
```

See [`INSTALLATION_SETUP_AND_RUN.md`](INSTALLATION_SETUP_AND_RUN.md) for exact commands.

## Source-code module map

| Python module | Responsibility |
| --- | --- |
| `data_access.py` | Backend-neutral registry reads and evidence scoping. |
| `format_resolver.py` | Canonical format resolution. |
| `evidence_packs.py` | Evidence assembly/provenance sections. |
| `frameworks.py` | Framework/question/answer/scale configuration. |
| `answer_derivation.py` | Evidence-to-controlled-answer derivation. |
| `scoring.py` | Deterministic scores, completeness, bands/suppression. |
| `question_assessment.py` | Targeted domain/question catalog and assessment. |
| `evidence_gaps.py` | Missing/unmapped evidence diagnosis. |
| `evidence_remediation.py` | Deterministic remediation action queue. |
| `request_api.py` | Canonical human/system request normalization/execution. |
| `integration_cli.py` | `ask` and `query-json` front door. |
| `human_renderer.py` | Detailed human-readable presentation. |
| `actions.py` | Preservation action helper structures. |
| `currency.py` | Evidence/assessment currency utilities. |
| `posture.py` | Institution-local posture calculation. |
| `policy_proposals.py` | Human-reviewable policy/action proposal package. |
| `responses.py` | Response helpers. |
| `cli.py` | Core deterministic/AI-assisted analysis commands. |
| `ai/*` | Provider abstraction, routing, fill-gaps, review. |

## Relationship to the registry builder

The risk manager should never need a source-specific parser or a MongoDB-specific preservation rule.

Correct dependency direction:

```text
registry source adapters
 -> common registry model/claims
 -> RegistryStore
 -> RegistryReader
 -> risk framework/assessment
```

If a risk question cannot be answered, first determine whether the missing work belongs to:

- source acquisition;
- source-to-criterion mapping;
- framework definition/calibration;
- institution-specific evidence;
- or genuinely unavailable evidence.

The evidence-gap/remediation actions are designed to make that distinction explicit.

## Related documentation

- Installation/run modes: [`INSTALLATION_SETUP_AND_RUN.md`](INSTALLATION_SETUP_AND_RUN.md)
- Human/machine requests: [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- 8-domain question set: [`PRESERVATION_RISK_QUESTIONS.md`](PRESERVATION_RISK_QUESTIONS.md)
- AI provider layer: [`AI_PROVIDER_INTERFACE.md`](AI_PROVIDER_INTERFACE.md)
- Shared data/store model: [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
