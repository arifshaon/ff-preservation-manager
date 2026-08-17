# Repository architecture

This document explains how the active modules fit together and where each responsibility belongs.

## System purpose

The repository supports a repeatable preservation-risk workflow:

```text
collect evidence
 -> normalize and preserve provenance
 -> reconcile format identities
 -> map source evidence to neutral criteria
 -> persist a queryable registry
 -> assess formats against explicit frameworks
 -> identify evidence gaps / remediation work
 -> present results to people or systems
```

The important architectural choice is separation of concerns. The registry builder produces and updates evidence. The preservation risk manager consumes that evidence and applies assessment frameworks. A storage backend such as MongoDB connects them, but MongoDB is not the application architecture itself.

## Top-level modules

### `qnl_format_registry_builder`

**Responsibility:** evidence ingestion and registry construction.

It owns:

- source configuration;
- acquisition and content-addressed snapshots;
- adapter-specific extraction;
- normalization into common source records;
- verified identifier claims;
- conservative reconciliation into canonical formats;
- preservation of raw/native source fields;
- declarative criterion mapping;
- generation and replacement/supersession of criterion claims;
- institutional evidence and policy overlays;
- persistence through `RegistryStore`;
- run history and change detection;
- optional JSON/JSONL/CSV/SQLite/Markdown exports.

It does **not** own the final configurable risk framework used by the risk manager.

### `preservation_risk_manager`

**Responsibility:** evidence access, framework application, risk analysis, and presentation.

It owns:

- format resolution;
- reading canonical formats and criterion claims;
- global vs institution-scoped evidence selection;
- evidence-pack construction;
- framework loading and question definitions;
- deterministic answer derivation;
- deterministic scoring and band suppression;
- targeted domain/question assessment;
- evidence-gap diagnosis;
- evidence-remediation planning;
- local posture/policy proposal context;
- natural-language request routing;
- canonical structured request execution;
- human-readable rendering;
- bounded AI review/fill-gap workflows.

It does **not** normally write or mutate the registry. Registry updates remain a registry-builder/storage workflow.

## End-to-end data flow

```text
                 SOURCE LAYER
 NARA   PRONOM   LOC FDD   QNL evidence   future sources
   \       |        |          |              /
    \      |        |          |             /
             source adapters
                    |
                    v
             source snapshots
                    |
                    v
              RawFormatRecord
                    |
        normalize + reconcile identity
                    |
                    v
             CanonicalFormat
                    |
      declarative criterion mappings
                    |
                    v
              criterion_claims
                    |
                    v
        RegistryStore / persistence layer
          |          |           |
        memory      file       MongoDB
                    |
                    v
              RegistryReader
                    |
             FormatResolver
                    |
              evidence pack
                    |
             RiskFramework
                    |
      deterministic answer derivation
                    |
            deterministic scoring
                    |
       +------------+-------------+
       |                          |
 canonical JSON                 human renderer
 system/API use                archivist-facing text
```

## Registry identity model

A source record is not automatically a canonical format. Adapters emit source-specific observations and identifier claims. Reconciliation combines records only when configured identifier evidence supports the relationship.

Examples of strong authority identifiers include verified PRONOM PUIDs, LOC FDD identifiers, and NARA identifiers. A copied PUID-like string from an institutional spreadsheet is useful evidence but is not treated as authority-verified merely because it resembles a PUID.

This separation allows the system to retain conflicting or incomplete upstream information without forcing unsafe merges.

## Evidence model

The architecture separates several concepts that should not be conflated:

```text
source snapshot
    raw acquired artifact retained for audit/replay

source record
    adapter-extracted representation of one upstream record

canonical format
    reconciled identity used as the registry's current format view

criterion claim
    normalized evidence statement mapped from source-native data

institution evidence
    institution-scoped evidence/context, e.g. QNL capability

institution policy overlay
    local decision/policy rather than universal format fact

risk assessment
    result of applying a selected framework to available claims
```

The risk manager should not infer a source fact merely from a format name, extension, or common knowledge when the framework requires evidence. Missing evidence remains visible.

## Common storage boundary

The registry builder defines a generic `RegistryStore` interface. The minimum write/read operations are:

```python
upsert(collection, key, document)
query(collection, filter)
```

Built-in implementations:

- `memory`
- `file` / `json_file`
- `mongodb`

A trusted external backend can be loaded through a `module:ClassName` plugin path if it subclasses `RegistryStore`.

The risk manager deliberately depends on a smaller protocol: it needs `query(...)`. `RegistryReader` can instantiate a registry-builder backend from the same storage configuration or read a registry JSON export through `JsonRegistryStore`.

Therefore assessment logic is backend-neutral.

Read [`DATA_MODEL_AND_STORAGE_INTERFACE.md`](DATA_MODEL_AND_STORAGE_INTERFACE.md) for the full contract.

## Common request/execution boundary

The risk manager has another important interface: the canonical request API.

Both human and machine entry points converge on the same controlled request:

```text
Human:
"What are the software dependency risks of PDF?"
       |
       v
AI request router (intent only)
       |
       v
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["software_dependencies_environment"]
  }
}
       |
       +-------------------------+
       |                         |
       v                         v
execute_request()           system sends JSON directly
       |                         |
       +------------+------------+
                    v
          deterministic result JSON
             |              |
             v              v
       human renderer    API/integration consumer
```

The model is not allowed to substitute general AI knowledge for the registry result. It only selects a supported action/parameters for human prompts.

## Deterministic vs AI responsibilities

### Deterministic/application-owned

- format identity and resolution rules;
- framework questions and allowed answer IDs;
- evidence-field declarations;
- source-to-criterion mapping rules;
- evidence scope;
- scoring weights and score bands;
- completeness thresholds;
- final deterministic risk band;
- evidence-gap classification;
- remediation action categories/priorities;
- local posture logic;
- canonical JSON result.

### Bounded AI responsibilities

- translate human language into a supported structured request;
- in `fill-gaps`, interpret evidence only for unresolved questions and choose an allowed framework answer when supported;
- in `review-all`, independently review raw source evidence for calibration without changing deterministic answers;
- provider/model plumbing through a provider-neutral interface.

AI must not invent evidence, add unsupported formats, change stored policy, or silently override deterministic scoring.

## Human output vs machine output

The underlying result is canonical JSON. Presentation differs by mode.

### Human mode

`ask` accepts a natural-language question and renders a detailed archivist-facing answer. It should include relevant conclusions, evidence coverage, supporting evidence, unresolved questions, and calibration/coverage cautions.

### Machine mode

`query-json` accepts a controlled request and emits canonical JSON. This is the intended pattern for application integration, APIs, dashboards, scheduled processes, and automated evaluation.

`ask --json` is available for debugging/auditing the human route, including AI router metadata.

## Framework governance

A framework is configuration, not hidden model behavior.

The current repository contains:

- a small calibrated example framework used to test deterministic scoring;
- a broad 8-domain / 22-question draft framework used for operational evidence assessment.

The broad framework has overall banding disabled until QNL validates question weights and Low/Moderate/High thresholds. This prevents a comprehensive-looking draft question set from being mistaken for approved institutional policy.

## Global and institutional scope

Evidence scope is part of the architecture.

Global assessment:

```text
uses global/external evidence
excludes institution-scoped evidence
```

Institution assessment, for example `qnl`:

```text
uses global/external evidence
+ matching QNL-scoped evidence
+ local readiness/exposure context where requested
```

Institutional observations therefore enrich QNL decisions without rewriting universal statements about a format.

## Update ownership

The current normal update path is:

```text
source changes / new institutional evidence
        |
        v
registry builder / source or evidence adapter
        |
        v
RegistryStore.upsert(...)
        |
        v
new/current source records + claims + canonical view
        |
        v
risk manager reads refreshed evidence on next query
```

A future API may expose controlled write/update operations, but it should call the registry/service abstraction rather than write directly to MongoDB collections. The backend must remain replaceable and validation/provenance rules must remain in the application layer.

## Extension points

The architecture is designed for extension in three places:

1. **Source adapters** — add a new preservation registry or institutional source.
2. **Storage adapters** — persist the common document model somewhere other than memory/file/MongoDB.
3. **AI providers** — use Azure OpenAI, an OpenAI-compatible server, or future local/hosted inference without changing deterministic analysis.

Future API/web UI/scheduler layers should sit above the canonical request API and `RegistryReader`, not duplicate assessment logic.

## Related documentation

- Shared data/storage contract: [`DATA_MODEL_AND_STORAGE_INTERFACE.md`](DATA_MODEL_AND_STORAGE_INTERFACE.md)
- Registry-builder architecture: [`../qnl_format_registry_builder/docs/ARCHITECTURE.md`](../qnl_format_registry_builder/docs/ARCHITECTURE.md)
- Registry-builder adapter implementation: [`../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md)
- Risk-manager architecture: [`../preservation_risk_manager/docs/ARCHITECTURE.md`](../preservation_risk_manager/docs/ARCHITECTURE.md)
- Human/system queries: [`../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md`](../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md)
