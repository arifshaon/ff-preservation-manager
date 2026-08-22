# Repository architecture

This document is the canonical description of how File Format Preservation Manager works.

The system has two applications with a shared evidence boundary:

```text
qnl_format_registry_builder
    owns evidence acquisition and registry writes

preservation_risk_manager
    owns evidence consumption, risk synthesis and presentation
```

MongoDB normally connects them, but the architecture is not MongoDB-specific.

## 1. End-to-end architecture

```text
                           SOURCE LAYER

 PRONOM       LOC FDD        NARA        DPC        Wikidata       QNL/local
    |             |             |          |            |              |
    +-------------+-------------+----------+------------+--------------+
                                  |
                                  v
                     qnl_format_registry_builder
                                  |
                     acquisition / SourceSnapshot
                                  |
                     source-specific extraction
                                  |
                           RawFormatRecord
                                  |
                  normalize identifiers and evidence
                                  |
                  authority-aware identity reconciliation
                                  |
                           CanonicalFormat
                                  |
             +--------------------+---------------------+
             |                    |                     |
             v                    v                     v
       criterion_claims   risk_assessment_claims  relationship/context
                                                   claims/evidence
             |                    |                     |
             +--------------------+---------------------+
                                  |
                                  v
                         RegistryStore
                  MongoDB | file | memory | plugin
                                  |
                                  v
                         RegistryReader
                                  |
                         FormatResolver
                                  |
                         resolved format
                                  |
                  +---------------+----------------+
                  |                                |
                  v                                v
          governed overall risk            framework diagnostics
          source-risk synthesis            questions/completeness
                  |                                |
                  +---------------+----------------+
                                  |
                       preservation_risk_manager
                                  |
                   +--------------+---------------+
                   |              |               |
                   v              v               v
              human CLI      batch reports     web/API
                   |
                   +---- optional AI-assisted synthesis
```

## 2. Registry Builder responsibility

`qnl_format_registry_builder` is the normal write/update owner.

It is responsible for:

- source configuration and release policy;
- online/local/offline acquisition;
- content-addressed snapshots and hashes;
- source adapters;
- preservation of raw/native source values;
- identifier claims and authority verification;
- conservative canonical reconciliation;
- source-native risk assessments;
- declarative criterion mappings;
- governed risk/criterion/relationship projections where configured/reviewed;
- institution-scoped evidence/policy overlays;
- incremental source replacement/reuse;
- change detection and run provenance;
- persistence and optional review exports.

A source adapter should describe what the source actually says. It should not invent QNL policy or fill gaps merely to improve coverage.

## 3. Preservation Risk Manager responsibility

`preservation_risk_manager` is normally read-only with respect to registry evidence.

It is responsible for:

- resolving a user identifier/name to a canonical format;
- reading current source evidence/claims;
- applying the configured overall risk-synthesis policy;
- preserving source-native labels/scales/scopes in output;
- applying the separate question/framework model for evidence diagnostics;
- evidence completeness/gap/remediation analysis;
- optional AI-assisted synthesis;
- human-readable output;
- canonical JSON responses;
- batch/watchlist monitoring and curator reports;
- FastAPI web/API/Swagger presentation.

It does not normally update MongoDB because an AI/model/user query reached a new conclusion.

## 4. Identity is separate from evidence

A source record is not automatically a canonical format.

```text
source record
    -> identifier claims
    -> authority/reconciliation rules
    -> canonical format
```

Strong identifier ownership is explicit:

```text
PRONOM -> PUID
LOC    -> LOC FDD ID
NARA   -> NARA ID
Wikidata -> QID only
```

A PUID copied by Wikidata/NARA/LOC/local data remains a useful cross-reference claim but is not automatically authority-verified.

This rule prevents a convenient copied identifier from silently merging the wrong records.

## 5. Evidence layers are separate

The architecture deliberately preserves several different objects:

```text
SourceSnapshot
    exact acquired artifact / URI / hash / time

source_record
    source-specific extracted evidence

canonical_format
    reconciled current identity view

criterion_claim
    normalized preservation observation with mapping provenance

risk_assessment_claim
    source-native overall/summary risk assessment with scope/provenance

source_relationship_claim
    governed contextual/cross-registry relationship

institution evidence/policy
    local evidence/decision, scoped to an institution

Risk Manager result
    a read-time interpretation/synthesis, not a source fact
```

Do not collapse these layers into one generic risk record.

## 6. Two different risk-analysis layers

The current system intentionally has **two separate analysis layers**.

### 6.1 Governed source-level overall risk synthesis

This answers questions such as:

```text
What is the preservation risk of fmt/276?
```

Input is current governed source-level risk evidence, for example NARA and DPC.

Rules are loaded from the versioned synthesis policy:

```text
preservation_risk_manager/src/preservation_risk_manager/config/
  qnl_preservation_risk_synthesis.v1.json
```

The policy controls:

- semantic risk vocabulary and rank;
- source-native terminology mapping;
- source roles;
- scope precedence;
- scope selection;
- same-scope aggregation;
- broader-scope treatment;
- missing-assessment behavior;
- numeric aggregation policy.

The executor is generic: policy choices are selected by configuration rather than hard-coded NARA/DPC headline logic.

Key invariant:

```text
missing source evidence != Low
```

### 6.2 Question/framework evidence assessment

The 8-domain / 22-question draft framework asks preservation-relevant questions and reports evidence coverage, unanswered questions and diagnostic scoring.

This is **not** the same object as governed source-level overall risk.

The broad framework currently remains draft/unvalidated with operational banding disabled. Missing questions contribute to uncertainty/completeness diagnostics, not automatically to a higher/lower source-risk level.

## 7. Scope-aware synthesis

Source assessments can apply at different scopes:

```text
exact format / format version
format family
format group
content type
contextual
institution-specific format
```

The active policy decides precedence and aggregation.

Under the current QNL policy, more specific populated scope contributes the governed headline and broader assessments remain visible context.

Example:

```text
PDF 1.7 / fmt/276

NARA: exact PDF 1.7 -> Low
DPC:  PDF group      -> Vulnerable / Moderate

headline -> Low under configured exact-scope precedence
context  -> DPC Vulnerable remains visible
```

The engine does not average heterogeneous source numeric scales.

## 8. Configurable risk terminology

A source may use its own vocabulary:

```text
NARA: Low Risk / native numeric matrix
DPC: Vulnerable / Endangered / ...
future source: another native vocabulary
```

The original native value is retained.

A source-specific configured rule maps it to the semantic vocabulary understood by governed synthesis and AI integration:

```text
native term
 -> source rule
 -> semantic level
```

Unknown values remain unmapped rather than being guessed by keywords.

See [`../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md`](../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md).

## 9. AI-assisted synthesis

AI is an optional second analysis result, not the evidence authority.

The Risk Manager prepares one context containing:

```text
resolved format identity
+ collected registry/source evidence
+ governed source-level synthesis
+ active synthesis methodology
+ framework/context
```

Then:

```text
AI provider receives context
 -> model uses available capabilities when useful
 -> returns structured AI-assisted synthesis
 -> application validates/normalizes audit metadata
 -> result is displayed beside governed baseline
```

The AI may agree or disagree with the governed result.

Application-owned integrity rules remain:

- source-native evidence is not rewritten;
- AI output is not automatically written to MongoDB;
- external information must not be attributed to registry sources;
- missing evidence stays missing;
- governed baseline stays visible;
- institution/private evidence suppresses public web-search tooling;
- baseline-relation metadata is deterministically checked from semantic levels.

### Provider capabilities

Azure OpenAI has a native single-call Responses path with optional `web_search` exposed automatically.

Generic OpenAI-compatible endpoints use a one-call structured Chat Completions path and do not assume vendor-hosted web search.

See [`AI_PROVIDERS.md`](AI_PROVIDERS.md).

## 10. Human, machine, batch and web interfaces

All presentation modes should reuse the same core evidence/risk logic.

```text
one-format CLI `ask`
       |
machine `query-json`
       |
batch `batch-report`
       |
FastAPI background job
       |
       +--> same RegistryReader / resolver / governed synthesis / optional AI core
```

This avoids a dashboard or scheduler silently acquiring its own risk rules.

## 11. Batch/periodic monitoring

Periodic assessment is a normal application mode:

```text
controlled watchlist of PUIDs/IDs
 -> resolve each format
 -> governed risk from current registry
 -> optional AI synthesis
 -> HTML/CSV/JSON/ZIP report
```

The report leads with governed source-level risk; framework completeness and AI output are supporting/separate layers.

The same batch core is used by CLI and web background jobs.

## 12. Incremental source updates

Normal source maintenance is not a reinstall.

```text
refresh selected source A
       |
       +--> new successful A evidence
       +--> latest successful B/C/D evidence reused
       |
       v
reconcile complete active evidence set
       |
       v
persist new current view + retain history
```

A failed optional source is not treated as an empty source. Required-source failure fails the run.

Pinned release behavior remains controlled by source configuration.

Wikidata is a special guarded preflight/apply refresh rather than an ordinary broad crawl.

See [`OPERATIONS.md`](OPERATIONS.md).

## 13. Storage boundary

The Registry Builder defines `RegistryStore`; Risk Manager consumes a smaller query/read contract through `RegistryReader`.

Supported storage modes include:

- memory;
- file/JSON;
- MongoDB;
- trusted plugin backend.

MongoDB is the normal persistent implementation, not the definition of the data model.

Detailed physical schema/indexes: [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md).

## 14. Global versus institutional scope

Global evidence and institution-specific evidence remain separate.

```text
global assessment
 -> global/external evidence only

institution assessment
 -> global/external evidence
  + matching institution-scoped evidence
```

A local statement such as "QNL has no current migration tool" must not become a universal claim that no tool exists.

## 15. Extension points

The supported architecture has explicit extension points:

1. **Source adapter** — add another preservation-data source.
2. **Criterion/risk mapping configuration** — map a source-native vocabulary without changing the source record.
3. **Synthesis policy** — change risk vocabulary/scope/aggregation rules through reviewed configuration.
4. **Storage adapter** — persist the common model elsewhere.
5. **AI provider** — call another model/provider without changing governance semantics.
6. **Presentation layer** — CLI/API/dashboard/report consuming the same application core.

## 16. What must not be hard-coded by a source

Avoid source-specific application logic such as:

```text
if source == NARA then headline wins
if label contains "bad" then High
if source missing then Low
average NARA score with DPC classification
```

Instead:

```text
source preserves native evidence
 -> configured source terminology mapping
 -> configured scope/aggregation synthesis policy
```

Provider/API code may be provider-specific, but risk semantics should remain governed configuration.

## 17. Where to go next

- Data objects/collections: [`DATA_MODEL.md`](DATA_MODEL.md)
- Install: [`INSTALLATION.md`](INSTALLATION.md)
- Operate/update: [`OPERATIONS.md`](OPERATIONS.md)
- Add a source: [`HOW_TO_ADD_A_SOURCE.md`](HOW_TO_ADD_A_SOURCE.md)
- Source catalogue: [`sources/README.md`](sources/README.md)
- Curator examples: [`USE_CASES.md`](USE_CASES.md)
- AI providers: [`AI_PROVIDERS.md`](AI_PROVIDERS.md)
- API/Swagger: [`API_AND_SWAGGER.md`](API_AND_SWAGGER.md)
