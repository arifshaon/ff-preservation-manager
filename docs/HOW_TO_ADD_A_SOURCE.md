# Add a new dataset/source: A to Z

A source is not fully integrated just because the code can download it. A complete integration must preserve provenance, model identifier authority correctly, expose source-native evidence, define update behavior, and prove that the Risk Manager can consume the intended evidence without inventing semantics.

Use this guide for a new external preservation source or a new institutional dataset.

## 1. Create a source record before coding

Document these facts first:

```text
source name
publisher/authority
official upstream URL
machine-readable download/API URL
release/edition/version model
licence/terms relevant to reuse
update frequency or release process
structured vs unstructured
identifier namespaces owned by the source
risk terminology used by the source
whether evidence is global or institution-specific
```

Create a source guide under:

```text
docs/sources/<SOURCE>.md
```

Use the existing PRONOM/LOC/NARA/DPC/Wikidata guides as templates.

## 2. Decide the source's authority role

Ask separately:

### Identity authority

Does the source own a stable identifier namespace?

Examples:

```text
PRONOM owns PUIDs
LOC owns FDD IDs
NARA owns NARA format IDs
Wikidata owns QIDs only
```

Do not mark copied identifiers as verified merely because they appear in the new dataset.

### Preservation evidence authority

What does the source actually assert?

Examples:

```text
format identity/technical description
preservation-risk classification
sustainability characteristics
software/support observations
contextual relationships
institution-specific capability/policy
```

### Scope

Determine whether its evidence applies to:

```text
exact format/version
format family
format group
content type
contextual topic
institution-specific format
```

Scope must be explicit enough for later governed synthesis.

## 3. Decide how the source will be acquired

Preferred order:

```text
official stable machine-readable artifact/API
-> official repository/release archive
-> reviewed local file when automation is not suitable
```

Acquisition must produce `SourceSnapshot` provenance, including source URI, acquisition time and SHA-256/content metadata where supported.

Do not hide acquisition inside an untracked ad-hoc preprocessing script.

### Structured source

CSV, JSON, XML, ZIP/repository archive or API can normally enter through a source adapter directly.

### Unstructured source

For PDF/prose/scanned/narrative sources:

```text
original publication
 -> manual or AI-assisted transcription
 -> human-reviewed versioned structured artifact
 -> normal adapter
```

AI extraction should not occur invisibly inside the final risk calculation.

See [`TRANSCRIBING_UNSTRUCTURED_SOURCES.md`](TRANSCRIBING_UNSTRUCTURED_SOURCES.md).

## 4. Reuse an adapter or implement a new one

Source adapters implement the acquisition/extraction boundary conceptually as:

```python
acquire() -> list[SourceSnapshot]
extract(snapshots) -> list[RawFormatRecord]
```

First check existing adapters/config patterns. Reuse `standard_json` or another generic adapter if it can preserve the source semantics without special-case code.

Create a source-specific adapter when you need source-specific:

- automatic acquisition/release discovery;
- schema parsing/validation;
- identifier extraction;
- native-field preservation;
- risk-assessment extraction;
- source locators/provenance;
- evidence-only/identity-projection restrictions.

Implementation reference:

[`../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md)

## 5. Preserve native and raw data

A new adapter should preserve enough information to audit every derived claim.

Use:

```text
native_fields
    source-native fields intended for later mapping/review

raw
    retained source payload/provenance/fields that should not be lost
```

Do not convert a native source term such as:

```text
"Vulnerable"
```

into only:

```text
"moderate"
```

and throw the original away.

## 6. Model identifiers conservatively

For every extracted identifier determine:

```text
kind
value
who owns namespace
whether this source owns it
verified true/false
source record provenance
```

Test collision/reconciliation behavior before letting a new source affect production canonical identity.

Detailed reference:

[`../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md`](../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md)

If the source is contextual/evidence-only, explicitly prevent identity projection rather than relying on convention.

## 7. Decide whether the source contributes overall risk

If the source publishes a native risk/endangerment/safety assessment, preserve it as source-native risk evidence with:

```text
native label
native numeric value where present
native scale
native direction where relevant
scope type/name
source record ID
source URL/provenance
```

Do **not** average or normalize away the native scale inside the adapter.

### Map risk terminology through configuration

The Risk Manager understands cross-source semantic levels through the synthesis policy's `source_rules`.

Add/review a rule only when the source's native terminology is understood.

Conceptually:

```json
{
  "rule_id": "my-source-native-risk-v1",
  "source_match": {
    "source_id": "my_source"
  },
  "value_fields": ["native_label"],
  "value_map": {
    "stable": "low",
    "at risk": "high"
  },
  "default_scope": "format_group"
}
```

The exact mapping must reflect the source's meaning; this example is illustrative only.

Unknown terms remain unmapped. Never add generic keyword logic such as "contains danger => high" to application code.

See:

[`../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md`](../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md)

## 8. Decide whether the source contributes criterion evidence

For preservation characteristics rather than an overall source risk conclusion, map native fields to the neutral criteria vocabulary.

Current vocabulary:

```text
qnl_format_registry_builder/config/criteria/v1.json
```

Mappings:

```text
qnl_format_registry_builder/config/criterion_mappings/
```

Flow:

```text
native source observation
 -> reviewed declarative mapping
 -> criterion_claim
 -> framework question/diagnostic
```

Normally add a mapping rather than a new criterion. Add a criterion only if the existing vocabulary genuinely cannot represent the observation safely.

Detailed workflow:

[`../qnl_format_registry_builder/docs/criterion_mapping_workflow.md`](../qnl_format_registry_builder/docs/criterion_mapping_workflow.md)

## 9. Keep overall risk and criterion evidence separate

A source can contribute both, but they are not interchangeable.

```text
source says "Vulnerable"
 -> source-level risk assessment

source says "specification is publicly disclosed"
 -> sustainability.disclosure criterion evidence
```

Do not reverse-engineer primitive criterion values from a composite source risk classification unless the source explicitly supports those statements.

## 10. Add the source configuration

Create an isolated test configuration first.

Typical shape:

```json
{
  "id": "my_source",
  "type": "my_source_adapter",
  "enabled": true,
  "required": false,
  "uris": ["https://publisher.example/data.json"]
}
```

Add source-specific release/pinning fields where needed.

Questions to answer in configuration/documentation:

```text
Does refresh follow latest or a pin?
What counts as a complete release?
Is a local-file fallback supported?
Can offline cached replay work?
Is optional-source failure allowed to retain prior successful evidence?
```

## 11. Unit-test the adapter

At minimum test:

- acquisition metadata/snapshot behavior;
- representative parsing;
- malformed/changed source behavior;
- native-field preservation;
- identifier verification semantics;
- source risk extraction/scope if applicable;
- evidence-only/identity restrictions if applicable;
- offline/local fallback if supported.

Use source fixtures small enough to review manually.

## 12. Test mappings separately

Validate criterion mappings:

```powershell
cd qnl_format_registry_builder
python -m registry_builder mapping validate `
  --criteria config\criteria\v1.json `
  --mappings config\criterion_mappings
```

For a new risk terminology rule, add synthesis-policy tests showing:

```text
native term -> intended semantic level
unknown native term -> remains unmapped
```

If adding a new semantic vocabulary level or synthesis behavior, prove it through policy configuration rather than source-specific Python branching.

## 13. Run the source in isolation

Before touching the shared production config/database, run the source alone against a controlled test store/database/export.

Review:

```text
snapshot URI/hash
record count
sample raw/native records
identifier claims
canonical matches/new canonicals
unmatched/collision review
criterion claims
risk assessments
source relationships
validation/change output
```

If a contextual source creates unexpected canonical records, stop.

## 14. Verify the consumer boundary

Do not declare source onboarding complete when the adapter passes.

Use the Risk Manager to prove the intended evidence is visible.

Example one-format query:

```powershell
cd ..\preservation_risk_manager
python -m preservation_risk_manager ask `
  "What is the preservation risk of <STRONG_IDENTIFIER>?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-mode off
```

Check:

- correct canonical resolution;
- native source evidence visible;
- terminology mapping correct;
- scope correct;
- governed headline/context behavior correct;
- criterion evidence visible to intended questions;
- missing evidence remains missing.

Then optionally test AI synthesis separately.

## 15. Integrate incrementally

After review, add the source to the reviewed production/source configuration.

Normal update behavior should support:

```text
new successful source contribution
+ latest successful contributions from untouched sources
-> complete active reconciliation/current view
```

Do not require a full clean reinstall merely because one source was added/updated unless the integration specifically requires a deliberate clean-room rebuild.

## 16. Add the operator refresh procedure

Document the exact command.

For a normal selected source:

```powershell
python -m registry_builder.refresh `
  --config config\sources.qnl.json `
  --source my_source `
  --workdir work `
  --out output `
  --report monitoring\my-source-refresh.json
```

If the source requires a special guarded workflow such as Wikidata, document that instead.

## 17. Add the source guide

A source-specific guide under `docs/sources/` should contain:

```text
what the source is
publisher/authority
exact official URLs
exact machine acquisition URL/pattern
current project source ID/type
current release/pin
identity authority role
risk/evidence role
native terminology/scales
scope rules
refresh command
new-release adoption procedure
what operator must review
links to deep implementation references
```

This is mandatory operational documentation, not optional prose.

## 18. Add tests for regression/governance

A production source integration should have tests that protect the important semantics, not merely parser coverage.

Examples:

```text
copied PUID stays unverified
DPC-like group evidence does not create canonical identity
native score survives normalization
unknown risk label stays unmapped
institution evidence stays institution-scoped
refresh replaces only its source contribution
```

## 19. Review security/licensing

Before committing source data/artifacts:

- confirm licence/terms permit redistribution if committing a snapshot/fixture;
- do not commit API keys/credentials;
- do not commit private institutional content as an example fixture;
- avoid retaining copyrighted source text beyond what is necessary/permitted;
- keep local/private inputs out of public source configs.

## 20. Completion checklist

A source is complete when all of these are true:

- [ ] official publisher/source and exact acquisition URL documented;
- [ ] release/update strategy documented;
- [ ] source role/scope documented;
- [ ] identifier authority rules explicit;
- [ ] snapshot/provenance retained;
- [ ] adapter preserves native/raw data;
- [ ] source risk assessments modeled natively where applicable;
- [ ] native risk terminology mapping reviewed/configured where applicable;
- [ ] criterion mappings reviewed where applicable;
- [ ] institution evidence scoped correctly where applicable;
- [ ] isolated run reviewed;
- [ ] reconciliation/collision behavior reviewed;
- [ ] Risk Manager consumer test passes;
- [ ] incremental refresh/update procedure works;
- [ ] source-specific guide exists in `docs/sources/`;
- [ ] regression/governance tests exist;
- [ ] no secrets/private content accidentally committed.

## Existing source examples

Use these as working patterns:

- [`sources/PRONOM.md`](sources/PRONOM.md) — identity authority.
- [`sources/LOC_FDD.md`](sources/LOC_FDD.md) — identity + criterion evidence + reviewed crosswalk.
- [`sources/NARA.md`](sources/NARA.md) — native numeric risk scale + exact-format risk.
- [`sources/DPC_BIT_LIST.md`](sources/DPC_BIT_LIST.md) — evidence-only broader risk vocabulary.
- [`sources/WIKIDATA.md`](sources/WIKIDATA.md) — evidence-only relationships with drift-gated special refresh.
- [`sources/QNL_LOCAL.md`](sources/QNL_LOCAL.md) — institution-scoped evidence/policy.

## Deep implementation references

- Adapter implementation: [`../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md`](../qnl_format_registry_builder/docs/ADAPTER_IMPLEMENTATION_GUIDE.md)
- Source patterns: [`../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_AND_RUNNING_DATA_SOURCES.md)
- Identifier reconciliation: [`../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md`](../qnl_format_registry_builder/docs/IDENTIFIER_RECONCILIATION.md)
- Criterion mapping: [`../qnl_format_registry_builder/docs/criterion_mapping_workflow.md`](../qnl_format_registry_builder/docs/criterion_mapping_workflow.md)
- Data model: [`DATA_MODEL.md`](DATA_MODEL.md)
- Operations: [`OPERATIONS.md`](OPERATIONS.md)
