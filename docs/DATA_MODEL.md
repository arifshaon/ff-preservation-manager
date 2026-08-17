# File Format Preservation Manager data model

This is the **canonical backend-neutral data model** for the repository.

Use this document when you need to understand what data exists, how it moves through the system, and which objects are source evidence versus normalized evidence versus risk conclusions.

MongoDB is only one physical storage implementation. MongoDB indexes, key escaping, collection setup, and administration remain documented separately in [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md).

## Model at a glance

```text
source artifact / publication
        |
        v
SourceSnapshot
        |
        v
SourceAdapter.extract()
        |
        v
RawFormatRecord + Identifier claims
        |
        v
normalization + reconciliation
        |
        v
CanonicalFormat
        |
        +--------------------+
        |                    |
        v                    v
source-native evidence   institution evidence
        |                    |
        +----------+---------+
                   |
                   v
          declarative criterion mapping
                   |
                   v
             criterion_claims
                   |
                   v
             RiskFramework
                   |
                   v
       deterministic question answers
                   |
                   v
       score / band / gaps / remediation
```

A major architectural rule is that these layers remain separate:

```text
source observation != normalized criterion claim
criterion claim     != risk conclusion
risk conclusion     != preservation action
institution evidence != universal format fact
```

## 1. In-flight Python types

These objects exist while the registry builder is acquiring, extracting, and reconciling evidence. They are not MongoDB-specific.

### `SourceSnapshot`

Defined in `registry_builder/models.py`.

A snapshot records the exact artifact used as evidence for a source run.

Typical fields:

| Field | Meaning |
| --- | --- |
| `source_id` | Configured source instance. |
| `source_type` | Adapter implementation/type. |
| `uri` | Original or local source location. |
| `acquired_at` | Acquisition timestamp. |
| `sha256` | Content hash of the acquired artifact. |
| `local_path` | Cached/temporary local path used for extraction. |
| `content_type` | Optional media/content type. |
| `note` | Retrieval/acquisition note. |
| `changed` | Whether the artifact changed from the previous known snapshot where available. |
| `from_cache` | Whether cached evidence was reused. |
| `metadata` | Adapter-specific acquisition metadata. |

Retained snapshots make source acquisition reproducible and auditable. Temporary snapshots may be deleted after extraction when the useful source payload is preserved in `RawFormatRecord.raw`.

### `Identifier`

An `Identifier` is an identifier **claim**, not merely a string.

```text
kind
value
source
verified
source_record_id
```

`verified=true` means the claim came from the authority that owns the namespace.

Examples:

```text
PUID from PRONOM      -> verified
PUID copied by NARA   -> useful claim, not PRONOM-verified
LOC FDD ID from LOC   -> verified
LOC URL in local XLSX -> useful claim, not LOC-verified
```

This distinction is central to conservative reconciliation.

### `RawFormatRecord`

`RawFormatRecord` is the source-adapter boundary.

Important fields include:

```text
source_id
source_type
source_record_id
name
category
description
extensions
mime_types
puids / loc_ids / nara_ids / wikidata_ids
identifiers
urls
institution_policy
institution_evidence
hazard
readiness
trend
evidence
native_fields
raw
```

Two fields are particularly important for source onboarding:

- `native_fields`: source-native observations intended for declarative criterion mapping;
- `raw`: retained source payload/provenance that should not be lost during normalization.

Adapters should not calculate QNL risk bands in `RawFormatRecord`. They should preserve what the source actually says.

### `CanonicalFormat`

`CanonicalFormat` is the current reconciled identity view.

Typical fields:

```text
canonical_id
preferred_name
category
description
identifiers
identifier_claims
source_records
institution_policy_overlays
institution_evidence_claims
external_hazard
hazard_assessment
readiness
trend
preservation_method
provenance
```

The canonical format is a current view over retained source evidence. It does not replace the source records.

## 2. Logical persisted collections

`RegistryStore` exposes logical collection names independent of physical backend.

| Logical collection | Purpose |
| --- | --- |
| `runs` | Pipeline/run identity, timestamps, status, configuration/provenance. |
| `source_snapshots` | Acquired source artifacts and hashes. |
| `source_records` | Adapter-extracted source records before canonical reconciliation. |
| `canonical_formats` | Current reconciled format identities. |
| `format_identifiers` | Authority/source identifier claims associated with canonical formats. |
| `institution_policy_overlays` | Institution-specific policy/decisions. |
| `format_evidence_claims` | Legacy/general evidence objects retained for compatibility. |
| `criterion_claims` | Normalized provenance-bearing observations against the neutral criteria vocabulary. |
| `hazard_assessments` | Stored hazard/conclusion outputs from builder workflows. |
| `readiness_assessments` | Local/operational readiness observations. |
| `trend_observations` | Time-based observations. |
| `assessment_changes` | Detected changes between assessment/registry states. |

A backend may store these as MongoDB collections, files, in-memory lists, SQL tables, or another compatible implementation. The logical meaning stays the same.

## 3. `criterion_claims` — normalized evidence layer

`criterion_claims` are the main harmonized evidence objects consumed by `preservation_risk_manager`.

A typical claim contains:

```json
{
  "canonical_id": "puid-fmt-18",
  "criterion_id": "sustainability.disclosure",
  "value": "openly_documented",
  "source_id": "pronom_registry",
  "source_type": "pronom_registry",
  "source_record_id": "fmt/18",
  "source_field": "native_fields.specification_status",
  "source_value": "Full",
  "native_vocabulary": "pronom",
  "directness": "explicit",
  "covers": "full",
  "source_independence": "independent",
  "criteria_version": "v1",
  "mapping_version": "2026-08-17",
  "mapping_rule_id": "pronom.disclosure.specification_status.v1",
  "review_status": "approved",
  "observed_at": "2026-08-17T00:00:00+00:00"
}
```

Not every source populates every optional field, but a usable claim should preserve enough provenance to answer:

1. **what format?** — `canonical_id`;
2. **what neutral observation?** — `criterion_id` + `value`;
3. **who said it?** — `source_id` / `source_type`;
4. **where in the source?** — `source_record_id`, `source_field`, and retained raw/source value;
5. **how was it normalized?** — mapping version/rule;
6. **was it reviewed?** — review status;
7. **is it local or global?** — `institution_id` / `source_independence`.

### Global vs institution-scoped claims

Global source evidence uses values such as:

```text
source_independence = independent
source_independence = source_derived
```

Local institutional observations use:

```text
source_independence = institution_scoped
institution_id = qnl
```

A QNL statement such as “QNL lacks software X” must not become a universal claim about the format.

## 4. Neutral criteria vocabulary

The criteria vocabulary is configuration, not adapter code:

```text
qnl_format_registry_builder/config/criteria/v1.json
```

It defines neutral preservation-relevant observations and their allowed values.

Example conceptual distinction:

```text
criterion:
  sustainability.adoption = low

not criterion:
  risk = High
  migrate_now = true
```

Source-to-criterion mappings live separately under `config/criterion_mappings/`.

This allows multiple sources to express different native vocabularies while contributing to one neutral evidence layer.

## 5. Risk framework model

`preservation_risk_manager` consumes criterion claims through a `RiskFramework`.

Main types:

```text
RiskFramework
RiskScale
ScoreBand
Question
AnswerOption
```

A question declares:

```text
id
human label
domain
critical flag
weight
evidence_fields
allowed answers
evidence-value mapping
guidance/applicability
```

The framework, not the source adapter, decides how normalized observations answer a preservation-risk question.

## 6. Derived assessment model

The risk manager transforms evidence into controlled question results.

For each question the deterministic derivation layer records states such as:

```text
derived
missing_evidence
unknown
derived_conflict_conservative
```

The scorer then returns fields such as:

```text
framework_id / version
calibration_status
banding_enabled
score / max_score
analysed_band
band_suppressed_reason
analysis_status
evidence_completeness
answered_questions
missing_count
abstention_count
question_results
```

`analysed_band = null` is a valid result when the framework is uncalibrated or evidence is insufficient.

## 7. Evidence-gap/remediation model

Unknown/unbanded evidence is not treated as Low risk.

The deterministic gap layer distinguishes conditions such as:

```text
no_matching_evidence
claims_exist_but_do_not_map
claims_exist_but_not_for_framework
```

The remediation planner can then classify work such as:

```text
mapping_rule_needed
source_evidence_needed
framework_alignment_review
```

This is intentionally separate from the risk band itself.

## 8. Transformation chain for a structured source

```text
remote/local CSV/JSON/XML
 -> SourceSnapshot
 -> adapter extraction
 -> RawFormatRecord(native_fields + raw)
 -> source_records
 -> normalization/reconciliation
 -> canonical_formats
 -> criterion mapping
 -> criterion_claims
 -> risk framework
 -> question answers
 -> risk/gap/remediation result
```

## 9. Transformation chain for an unstructured source

Narrative publications such as a PDF/web report require one additional controlled artifact:

```text
PDF / HTML publication
 -> manual or AI-assisted transcription
 -> reviewed versioned transcription JSON
 -> standard_json or thin source-specific adapter
 -> RawFormatRecord
 -> normal pipeline
 -> criterion_claims
 -> risk analysis
```

The transcription is an auditable intermediate source artifact. AI output must be treated as draft until reviewed by a named human.

See [`TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](TRANSCRIBING_UNSTRUCTURED_SOURCES.md).

## 10. Source provenance for transcribed evidence

For narrative sources, every transcribed record should retain a source locator such as:

```text
source_page
source_section
source_heading
source_url
source_excerpt
```

This allows an archivist to trace a normalized claim back to the actual passage rather than to an opaque AI response.

## 11. Storage contract

The backend-neutral persistence boundary is `RegistryStore`.

At minimum:

```python
upsert(collection, key, document)
query(collection, filter)
```

The registry builder owns normal writes/updates. The risk manager consumes the read side through `RegistryReader`.

Detailed storage/adapter behavior remains in [`DATA_MODEL_AND_STORAGE_INTERFACE.md`](DATA_MODEL_AND_STORAGE_INTERFACE.md).

## 12. File-export model

When exports are enabled, `registry.json` contains canonical format data while normalized criterion evidence may be written separately as:

```text
criterion_claims.jsonl
criterion_claims.json
```

The risk manager's export reader automatically discovers those sibling claim files when `--registry-json` points to `registry.json`.

So the supported export-backed handoff is:

```text
output/
  registry.json
  criterion_claims.jsonl
        |
        v
preservation_risk_manager --registry-json output/registry.json
```

## 13. MongoDB-specific representation

MongoDB is an implementation of this model, not the definition of it.

Use the MongoDB document for:

- physical collections;
- indexes;
- key escaping;
- Mongo-specific verification queries;
- connection configuration.

See [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md).

## Related documentation

- Storage interface/backend contract: [`DATA_MODEL_AND_STORAGE_INTERFACE.md`](DATA_MODEL_AND_STORAGE_INTERFACE.md)
- Repository architecture: [`REPOSITORY_ARCHITECTURE.md`](REPOSITORY_ARCHITECTURE.md)
- Add a source: [`HOW_TO_ADD_A_SOURCE.md`](HOW_TO_ADD_A_SOURCE.md)
- Unstructured/narrative source transcription: [`TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](TRANSCRIBING_UNSTRUCTURED_SOURCES.md)
- Criterion mapping: [`../qnl_format_registry_builder/docs/criterion_mapping_workflow.md`](../qnl_format_registry_builder/docs/criterion_mapping_workflow.md)
- Risk framework model: [`../preservation_risk_manager/docs/FRAMEWORKS.md`](../preservation_risk_manager/docs/FRAMEWORKS.md)
