# Data model

This is the canonical backend-neutral data model for File Format Preservation Manager.

MongoDB is the normal persistent implementation, but the logical objects below are the model. Physical MongoDB indexes/key escaping are documented separately in [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md).

## 1. Model at a glance

```text
upstream publication / local evidence
              |
              v
        SourceSnapshot
              |
              v
       RawFormatRecord
              |
     +--------+---------+
     |                  |
     v                  v
identifier claims   source-native evidence
     |                  |
     v                  +-------------------------------+
authority-aware                                         |
reconciliation                                           |
     |                                                   |
     v                                                   |
CanonicalFormat                                          |
     |                                                   |
     +--------------------+------------------------------+
                          |
              governed persisted evidence
                          |
        +-----------------+------------------+
        |                 |                  |
        v                 v                  v
 criterion_claims  risk_assessment_claims  source_relationship_claims
        |                 |                  |
        +-----------------+------------------+
                          |
                          v
                    RegistryReader
                          |
                 +--------+--------+
                 |                 |
                 v                 v
        governed overall      framework/question
        risk synthesis        diagnostics
                 |                 |
                 +--------+--------+
                          |
                          v
                 optional AI synthesis
                          |
                          v
               CLI / batch / web / API
```

Core separation rules:

```text
source observation != canonical identity
identifier claim   != verified identifier
criterion claim    != overall risk assessment
source risk        != question-framework score
AI synthesis       != source evidence
institution fact   != universal format fact
```

## 2. In-flight acquisition objects

### `SourceSnapshot`

A snapshot records the artifact/evidence acquired for a source run.

Typical fields:

| Field | Meaning |
| --- | --- |
| `source_id` | Configured source instance. |
| `source_type` | Adapter implementation/type. |
| `uri` | Original/local source location. |
| `acquired_at` | Retrieval timestamp. |
| `sha256` | Content hash of acquired artifact. |
| `local_path` | Cached working path. |
| `changed` | Whether content changed relative to known prior snapshot where available. |
| `from_cache` | Whether cached evidence was reused. |
| `metadata` | Release/ref/acquisition-specific metadata. |

Snapshots support audit, change detection and offline replay.

### `Identifier`

An identifier is a claim with provenance, not merely a string.

Conceptually:

```text
kind
value
source
source_record_id
verified
```

Examples:

```text
PUID from PRONOM -> verified PUID
PUID copied by Wikidata -> unverified PUID assertion
LOC FDD ID from LOC -> verified LOC identity
NARA ID from NARA -> verified NARA identity
QID from Wikidata -> verified Wikidata source identity
```

### `RawFormatRecord`

The adapter boundary. It preserves a source's extracted representation before canonical reconciliation.

Common fields:

```text
source_id
source_type
source_record_id
record_role
name / category / description
extensions / mime_types
identifier claims
urls
risk_assessments
institution evidence/policy
hazard/readiness/trend fields where source-native
native_fields
raw
evidence/provenance
```

Two fields matter especially for extensibility:

```text
native_fields
    source-native values exposed for reviewed declarative mapping

raw
    retained source payload/provenance that should not be lost during normalization
```

Adapters should retain source meaning rather than convert every source into a single QNL risk vocabulary.

## 3. `CanonicalFormat`

`CanonicalFormat` is the reconciled current identity view.

Typical content includes:

```text
canonical_id
preferred_name
category / description
identifiers
identifier_claims
source_records / provenance
institution overlays/evidence references
current derived relationship/context
current synthesized_risk where materialized
```

A canonical format does not replace historical/source evidence. It provides a stable read target assembled from governed active contributions.

A canonical ID such as:

```text
puid-fmt-276
```

is an internal registry identity. The external authority identifier remains:

```text
fmt/276
```

## 4. Logical persisted collections

The active persistent model includes the following important logical collections.

| Collection | Purpose |
| --- | --- |
| `runs` | Pipeline/backfill/refresh run identity, status and provenance. |
| `source_snapshots` | Acquired source artifacts and hashes. |
| `source_records` | Adapter-extracted source evidence/history. |
| `canonical_formats` | Current/historical reconciled format identities. |
| `format_identifiers` | Identifier claims/authority links for canonicals. |
| `criterion_claims` | Reviewed normalized preservation observations. |
| `risk_assessment_claims` | Source-native/governed overall risk assessments mapped to canonical targets. |
| `source_relationship_claims` | Governed contextual/cross-registry relationships such as Wikidata authority cross-references. |
| `institution_policy_overlays` | Institution-specific policy decisions. |
| `format_evidence_claims` | General/legacy evidence objects retained for compatibility where present. |
| `hazard_assessments` | Historical/other hazard assessment outputs used by builder workflows. |
| `readiness_assessments` | Local/operational readiness observations where used. |
| `trend_observations` | Time-series observations where used. |
| `assessment_changes` | Detected changes across stored assessment/registry states. |

Operational read rule:

```text
current != false -> active/current
current == false -> historical/superseded
```

Do not query historical `source_records` directly as deterministic current risk evidence. Current governed claims/current canonical views are the read layer.

## 5. `criterion_claims`

A criterion claim is a normalized evidence statement against a neutral preservation vocabulary.

Conceptual example:

```json
{
  "canonical_id": "puid-fmt-276",
  "criterion_id": "sustainability.disclosure",
  "value": "openly_documented",
  "source_id": "loc_fdd_xml",
  "source_record_id": "fdd000277",
  "source_field": "native_fields.disclosure",
  "source_value": "...native LOC value...",
  "mapping_rule_id": "...",
  "mapping_version": "...",
  "review_status": "approved",
  "current": true
}
```

A useful criterion claim answers:

1. what format?
2. what neutral observation?
3. what native source value supported it?
4. who supplied it?
5. where in the source?
6. which mapping/version transformed it?
7. what scope applies?
8. is the mapping reviewed/current?

Criterion claims support framework questions. They are not automatically an overall preservation-risk score.

## 6. Neutral criteria vocabulary

The neutral criteria vocabulary is configuration:

```text
qnl_format_registry_builder/config/criteria/v1.json
```

Source-to-criterion mappings live under:

```text
qnl_format_registry_builder/config/criterion_mappings/
```

This separates:

```text
source native observation
from
neutral preservation observation
from
risk-framework answer
```

Do not invent a new criterion merely because a source uses a different label if an existing criterion can represent the underlying observation faithfully.

## 7. `risk_assessment_claims`

This collection stores governed source-level risk assessments independently of the question framework.

Typical fields retained/compacted by the Risk Manager include:

```text
canonical_id
source_id / source_type / source_label
source_record_id
scope_type / scope_name / scope_basis
native_label
native_score
native_scale
native_direction
normalized_band/score where source projection provides it
semantic_level
mapping_rule_id / mapping_version / projection_version
current
```

Examples:

```text
NARA
  native label/score/scale
  exact format scope where reconciled

DPC
  native classification (e.g. Vulnerable)
  format-group/context scope
```

The source-native values remain authoritative descriptions of what the source said. The semantic level is a governed mapping for cross-source synthesis; it does not erase the native label.

## 8. Config-driven governed synthesis

`risk_assessment_claims` are synthesized at read time through:

```text
preservation_risk_manager/config/qnl_preservation_risk_synthesis.v1.json
```

The returned `policy_synthesized_risk` contains the governed current interpretation according to the selected policy.

Typical output concepts:

```text
semantic_level / semantic_label
selected_scope_types
contributors
contextual_contributors
unmapped_assessments
policy id/version
```

A canonical document can also carry a locked/materialized `synthesized_risk` from registry projection. Risk Manager reports parity between that stored baseline and the current policy execution so a configuration migration can be verified before changing the persisted baseline.

Do not confuse:

```text
source risk assessment
policy-synthesized current headline
AI-assisted synthesis
```

They are three different provenance layers.

## 9. Risk terminology mapping

The synthesis policy defines:

```text
semantic_levels
source_rules
synthesis operators/rules
```

A source rule may map a native vocabulary to a semantic level understood by the governed engine and AI contract.

Example:

```text
DPC native "Vulnerable"
 -> source-specific configured rule
 -> moderate
```

Unknown values remain unmapped unless reviewed configuration explains them.

See [`../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md`](../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md).

## 10. `source_relationship_claims`

Relationships are persisted separately from identity.

Wikidata is the important current example:

```text
QID evidence-only source record
 -> copied authority cross-reference
 -> governed relationship claim
 -> existing canonical format
```

A relationship can be:

```text
single-target cross-reference
multi-target context
other governed source relationship
```

It does not automatically mean identity equivalence.

This separate collection lets relationships survive canonical rebuilds without allowing a contextual source to create/merge canonicals.

## 11. Institution-specific objects

Institution evidence/policy must retain institutional scope.

Examples:

```text
institution_policy_overlays
institution-scoped criterion claims
readiness/local capability evidence
```

Typical identity:

```text
institution_id = qnl
```

Global assessment excludes institution-scoped claims. Institution assessment may use global plus matching institution evidence.

## 12. Question/framework model

The Risk Manager also consumes `criterion_claims` through a `RiskFramework`.

Main concepts:

```text
RiskFramework
Question
AnswerOption
Domain
weights / applicability / evidence fields
calibration/banding settings
```

For each question the deterministic derivation/scoring layer records states such as:

```text
derived
missing_evidence
unknown
derived_conflict_conservative
abstention
```

The broad QNL working framework is separate from the source-level governed synthesis and currently has draft/unvalidated calibration/banding status.

## 13. Evidence completeness/gaps

Unknown/unmapped/missing evidence is preserved as a diagnostic state.

Examples:

```text
no_matching_evidence
claims_exist_but_do_not_map
claims_exist_but_not_for_framework
```

The remediation layer can propose review categories such as mapping work or source-evidence research.

These gaps do not automatically change the governed overall risk level.

## 14. AI synthesis data boundary

For optional AI synthesis, the application constructs a bounded evidence package containing references such as:

```text
R... governed/source risk assessment refs
C... criterion claim refs
S... source-native evidence refs
```

The AI response records:

```text
semantic_level
confidence
rationale
database_evidence_refs
considerations
config_rules_considered
governed_baseline_relation
uncertainty
external source URLs/capability metadata where applicable
```

This AI result is not a persisted source claim by default.

The application also checks model-returned metadata such as baseline relation against configured semantic ranks.

## 15. Source update model

Persistent evidence is historical, while the current read view is replaceable source-by-source.

```text
source A refreshed successfully
 -> new active A contribution
 -> old A retained historically but superseded

source B not refreshed
 -> latest successful B contribution reused
```

The active canonical/claim view is reconciled from the complete active evidence set.

This is why source update does not mean deleting/reinstalling the registry.

## 16. Storage contract

The backend-neutral persistence boundary is `RegistryStore`.

The Risk Manager reads via `RegistryReader` and needs a query-compatible store.

MongoDB is selected through registry configuration. Export-backed workflows can read `registry.json` and sibling claim exports where supported.

Storage implementation detail: [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md).

## 17. Data flow for adding a source

```text
remote/local CSV/JSON/XML/API/archive
 -> snapshot
 -> adapter
 -> RawFormatRecord
 -> native/raw preservation
 -> identifier authority classification
 -> canonical reconciliation
 -> optional criterion mapping
 -> optional governed risk terminology/projection
 -> persistence
 -> Risk Manager verification
```

For narrative/unstructured material, insert a reviewed structured transcription before the normal adapter boundary.

See [`HOW_TO_ADD_A_SOURCE.md`](HOW_TO_ADD_A_SOURCE.md).

## 18. Related documentation

- Architecture: [`REPOSITORY_ARCHITECTURE.md`](REPOSITORY_ARCHITECTURE.md)
- Add a source: [`HOW_TO_ADD_A_SOURCE.md`](HOW_TO_ADD_A_SOURCE.md)
- Source catalogue: [`sources/README.md`](sources/README.md)
- Risk synthesis: [`../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md`](../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md)
- Identifier reconciliation: [`../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md`](../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md)
- MongoDB schema: [`../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md`](../qnl_format_registry_builder/docs/MONGODB_STORAGE_SCHEMA.md)
