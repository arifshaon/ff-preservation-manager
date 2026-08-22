# AI Expert Preservation-Risk Synthesis

## Purpose

The Preservation Risk Manager supports two distinct overall-risk analyses. They must not be conflated.

### 1. Governed synthesis

The governed result is produced from stored/source-native assessments using the versioned QNL synthesis policy.

It is deterministic and auditable:

- source-native assessments are preserved;
- reviewed source mappings normalize values to the common semantic scale;
- the most-specific populated scope is selected;
- multiple assessments at the selected scope use the configured conservative upper-bound rule;
- broader scopes remain context;
- missing sources contribute nothing;
- heterogeneous native numeric scales are not averaged.

This remains the institutional/auditable result.

### 2. AI expert synthesis

AI expert synthesis is a parallel advisory opinion. It receives:

- the resolved format identity;
- the governed source assessments;
- the governed/config-derived overall result;
- criterion claims and source-native evidence linked to the format;
- the QNL synthesis policy;
- the QNL preservation-risk question framework;
- permission to use the model's broader trained knowledge about digital-preservation and file-format ecosystems.

The AI may agree with or disagree with the governed result. It must explain any divergence.

The AI expert result does **not** overwrite:

- source-native assessments;
- configured source mappings;
- the governed overall synthesis;
- canonical registry data;
- MongoDB records.

## Knowledge boundary

The current AI provider is not assumed to have live web access.

`expert-synthesize` may use model-trained knowledge, but that is not live verification. The result therefore carries a currentness caveat, especially for time-sensitive facts such as:

- current software support;
- active standards maintenance;
- current adoption;
- recently discontinued products;
- newly available migration or validation tooling;
- newly disclosed vulnerabilities or dependencies.

A future researched mode may add live search/retrieval with explicit source citations. That should remain distinguishable from model-memory-based expert synthesis.

## Evidence separation

The AI output must distinguish two evidence classes:

1. **Database evidence** — references to the bounded R/C/S evidence supplied by the application.
2. **Model-knowledge findings** — claims supplied from broader model training rather than the registry.

Model-knowledge findings are never attributed to NARA, DPC, LOC, PRONOM, or another source unless the database evidence actually contains that statement.

## Interpretation of disagreement

Example:

```text
Governed preservation risk: Low concern
AI expert preservation risk: Moderate concern
Comparison: AI more concerned
```

This is not an error. It means the configured institutional synthesis and the broader AI expert assessment reached different conclusions.

The output should explain why, for example:

- governed exact-format evidence is Low;
- a broader DPC group assessment is Moderate context;
- the AI additionally considers ecosystem, tooling, dependency, adoption, or migration concerns from broader trained knowledge;
- the AI therefore advises Moderate concern with stated confidence and uncertainty.

The governed result remains the authoritative/auditable result unless QNL explicitly changes policy.

## CLI

```powershell
python -m preservation_risk_manager expert-synthesize `
  --format fmt/276 `
  --framework examples/qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ../qnl_format_registry_builder/config/sources.qnl.json `
  --ai-config config/ai.local.json
```

Add `--json` for the full machine-readable result.

## Relationship to bounded `synthesize`

`--ai-mode synthesize` remains evidence-bounded. It is intended to interpret genuinely unmapped source-native risk findings or, when no mapped source-level assessment exists, bounded supporting evidence.

If the config already produces a mapped source-level synthesis and no unmapped source-risk finding remains, bounded synthesis does not call the AI provider. Use `expert-synthesize` when a broader independent AI opinion is desired.
