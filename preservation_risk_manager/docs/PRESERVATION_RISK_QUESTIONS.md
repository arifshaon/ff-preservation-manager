# Preservation-risk assessment questions

This document describes the broad preservation-risk question set implemented in:

```text
examples/qnl_preservation_risk_questions.framework.draft.json
```

It is a **QNL working synthesis** for operational file-format sustainability, obsolescence, data-loss, and institutional-feasibility assessment. It is informed by concepts used by memory institutions and preservation guidance such as Library of Congress sustainability factors and NARA preservation considerations.

It is **not** presented as an official verbatim LOC or NARA questionnaire, and it is **not yet approved/calibrated QNL risk policy**.

Current framework metadata:

```text
framework_id: qnl_preservation_risk_questions
version: 0.1.0-draft
calibration_status: draft_unvalidated
banding_enabled: false
```

The questions can be used now for evidence collection, gap analysis, targeted human questions, and machine queries. Overall Low/Moderate/High banding remains disabled until weights/thresholds are validated.

## Domain summary

| Domain ID | Domain | Questions |
| --- | --- | ---: |
| `specification_governance` | Specification Disclosure & Governance | 3 |
| `software_dependencies_environment` | Software Dependencies & Environment | 3 |
| `adoption_community_support` | Adoption & Community Support | 3 |
| `technical_structure_transparency` | Technical Structure & Transparency | 3 |
| `intellectual_property_rights` | Intellectual Property & Rights Management | 2 |
| `metadata_self_documentation` | Metadata & Self-Documentation | 2 |
| `essential_characteristics` | Essential Characteristics (Content Fidelity) | 3 content-specific |
| `local_institutional_feasibility` | Local Institutional Feasibility | 3 |
|  | **Total** | **22** |

## 1. Specification Disclosure & Governance

Domain ID:

```text
specification_governance
```

### `q_specification_disclosure`

**Human question:** Is the format specification fully disclosed and publicly accessible? Can developers build a reader or converter without reverse-engineering?

What it is trying to establish:

- whether a normative specification is available;
- whether it is sufficiently complete to support independent implementation;
- whether preservation tooling could be recreated without depending on undocumented vendor behavior.

Example human prompts:

```text
How well documented is PDF?
Can an independent developer implement this format without reverse-engineering?
Is the specification public and complete?
```

### `q_specification_governance`

**Human question:** Who maintains the format specification? Is it governed by an open standards body such as ISO, W3C, or IETF, or controlled by a single commercial vendor?

What it is trying to establish:

- governance durability;
- concentration of control;
- openness/transparency of maintenance;
- likelihood that stewardship survives one vendor or product lifecycle.

Example prompts:

```text
Who governs this format?
Is the format controlled by one vendor?
Is it maintained through an open standards body?
```

### `q_specification_stability`

**Human question:** How frequently is the specification updated? Is the format stable, or do major revisions create backward-compatibility problems?

What it is trying to establish:

- healthy maintenance vs disruptive churn;
- backward compatibility;
- repeated migration/interpretation burden caused by major incompatible revisions.

Example prompts:

```text
Is this format stable across versions?
Do newer versions break backward compatibility?
Does the specification change frequently enough to create preservation risk?
```

## 2. Software Dependencies & Environment

Domain ID:

```text
software_dependencies_environment
```

### `q_platform_dependency`

**Human question:** Is rendering dependent on specific operating systems, proprietary software, or legacy hardware?

Important interpretation rule: this concerns resources **outside the file/environment needed to use it**, not simply resources that the format requires to be embedded in the file.

Example prompts:

```text
Does this format depend on proprietary software?
Can it only be opened on a legacy operating system?
Does it require obsolete hardware or a specialist runtime?
```

### `q_external_assets`

**Human question:** Does the format rely on external assets? Does opening the file require unembedded fonts, external DLLs, linked spreadsheets, plugins, or online endpoints?

Important interpretation rule: a font or other resource that is successfully embedded in the file is not an external dependency merely because the format specifies that it must be embedded.

Example prompts:

```text
Does PDF rely on external assets?
Can linked resources make this format incomplete later?
Does the file need remote services or unembedded fonts to render?
```

### `q_open_source_tooling`

**Human question:** Are open-source viewers, validators, extraction tools, or converters available? Can the format be used without relying exclusively on licensed vendor software?

Example prompts:

```text
Are open-source viewers available for this format?
Can we validate or extract metadata without vendor software?
How dependent is this format on licensed tooling?
```

## 3. Adoption & Community Support

Domain ID:

```text
adoption_community_support
```

### `q_adoption`

**Human question:** How widely adopted is the format across its target industry or creator community?

The relevant comparison is within the format's actual community. Domain-specific use is not automatically equivalent to abandonment, but declining or legacy-only use can increase risk.

Example prompts:

```text
Is this format still widely adopted?
Is use of this format declining?
Is it mainstream in the community that produces it?
```

### `q_third_party_support`

**Human question:** Are third-party applications actively maintaining read/write support for the format?

This is about maintained implementations, not simply historical compatibility claims.

Example prompts:

```text
How many actively maintained applications still support this format?
Is read/write support concentrated in one application?
Is support legacy-only?
```

### `q_registry_recognition`

**Human question:** Is the format recognized in technical registries? Does it possess a formal PUID, MIME type, or comparable identifier that supports automated identification?

An extension alone is weak evidence of reliable identification.

Example prompts:

```text
Does this format have a PRONOM PUID?
Can it be reliably identified automatically?
Does it have a formal MIME type or registry identifier?
```

## 4. Technical Structure & Transparency

Domain ID:

```text
technical_structure_transparency
```

### `q_byte_transparency`

**Human question:** Is the byte structure transparent? Is the content stored as directly inspectable text/XML or as an opaque binary representation?

This criterion should be used narrowly: a well-documented binary format can still be preservable. Binary does not automatically mean High risk.

Example prompts:

```text
Is this format directly inspectable or opaque binary?
Can the internal structure be understood without proprietary parsing?
How transparent is the byte structure?
```

### `q_compression`

**Human question:** What compression mechanism is used? Is the representation uncompressed, losslessly compressed, or lossily compressed?

Compression itself is not obsolescence. The risk question is whether encoding choices constrain preservation/future transformation.

Example prompts:

```text
Is this format lossless or lossy?
What compression does it use?
Does compression materially constrain preservation?
```

### `q_lossy_migration`

**Human question:** If migration/transcoding is required, could it cause irreversible loss of essential characteristics?

Migration should be evaluated against documented essential/significant characteristics rather than assuming all conversions are equivalent.

Example prompts:

```text
Would migrating this format cause irreversible loss?
Can we preserve the significant properties during conversion?
What fidelity risks exist in migration?
```

## 5. Intellectual Property & Rights Management

Domain ID:

```text
intellectual_property_rights
```

### `q_ip_constraints`

**Human question:** Is the format subject to active patents, trademark constraints, licensing fees, or implementation restrictions that materially affect preservation tooling?

Ordinary trademark ownership should not be confused with an actual restriction on implementation or preservation use.

Example prompts:

```text
Are patents or licensing restrictions a preservation problem for this format?
Does implementing a converter require royalties?
Are preservation tools constrained by active IP restrictions?
```

### `q_tpm_drm`

**Human question:** Does the file contain or commonly use Technological Protection Measures such as DRM, encryption, hardcoded passwords, or keys that prevent automated indexing, validation, or transformation?

The framework distinguishes a format's optional capability from an actual protected file that cannot be processed without credentials/keys.

Example prompts:

```text
Can DRM prevent preservation actions for this format?
Does encryption block validation or migration?
Are passwords or keys required to access the content?
```

## 6. Metadata & Self-Documentation

Domain ID:

```text
metadata_self_documentation
```

### `q_embedded_metadata`

**Human question:** Can the file self-document through embedded technical, descriptive, or structural metadata such as EXIF, XMP, or comparable native tags?

Example prompts:

```text
Can this format preserve embedded metadata?
Does it support XMP/EXIF or structured internal metadata?
Does important metadata have to live outside the file?
```

### `q_accessibility_features`

**Human question:** Can relevant accessibility features be represented and preserved natively, for example tagged text, alternate text, structured tables, captions, or comparable semantics?

Apply the features relevant to the content type rather than requiring every accessibility mechanism in every format.

Example prompts:

```text
Can accessibility features survive preservation in this format?
Can it preserve alt text or tagged structure?
Can captions/subtitles be represented natively where relevant?
```

## 7. Essential Characteristics (Content Fidelity)

Domain ID:

```text
essential_characteristics
```

This domain is content-type specific. Machine requests should supply `content_type` where possible so irrelevant questions are not selected.

### `q_image_fidelity`

Applicability:

```text
image
graphics
```

**Human question:** For image content, can the format preserve required bit depth, colour profiles, and vector scale?

Example prompts:

```text
Can TIFF preserve the image characteristics we require?
Does this format retain colour profiles and bit depth?
Can vector scale remain reliable through preservation/migration?
```

### `q_av_fidelity`

Applicability:

```text
audio
video
audiovisual
```

**Human question:** For audio/video content, can required timecodes, uncompressed/multi-track audio, subtitles, and other significant characteristics be preserved?

Example prompts:

```text
Can this video format retain timecodes and subtitles?
Can it preserve multi-track audio?
Would migration lose important AV characteristics?
```

### `q_data_fidelity`

Applicability:

```text
data
dataset
spreadsheet
```

**Human question:** For data/spreadsheets, can explicit data types, formulas, and relationships be preserved instead of being flattened to static values?

Example prompts:

```text
Can this spreadsheet format preserve formulas and relationships?
Will migration retain explicit data types?
Would the data be flattened or lose semantics?
```

## 8. Local Institutional Feasibility

Domain ID:

```text
local_institutional_feasibility
```

These questions should normally use institution-scoped evidence. They are not universal properties of the format.

### `q_local_capability`

**Human question:** Does the institution currently possess the software infrastructure and staff expertise required to manage the format?

Example prompts:

```text
Can QNL currently manage this format?
Do we have the required software and staff expertise?
Is the workflow dependent on one specialist member of staff?
```

### `q_migration_pathways`

**Human question:** Are established migration pathways and tools available, including tested institutional workflows or evidence from preservation action registries?

A hypothetical converter is weaker evidence than a tested preservation pathway.

Example prompts:

```text
Does QNL have a tested migration pathway for this format?
What tools can migrate this format?
Has the migration route been verified rather than assumed?
```

### `q_storage_overhead`

**Human question:** Are storage, transfer, network, and processing overheads sustainable for the institution at collection scale?

Large files are not automatically High risk if the institution has sufficient capacity.

Example prompts:

```text
Would this format create unsustainable storage overhead for QNL?
Are typical file sizes manageable at our collection scale?
Would transfer or processing requirements become an operational constraint?
```

## Machine: list the question catalog

All questions:

```json
{
  "action": "list_assessment_questions",
  "scope": "global"
}
```

One domain:

```json
{
  "action": "list_assessment_questions",
  "filters": {
    "domains": ["software_dependencies_environment"]
  },
  "scope": "global"
}
```

Specific question IDs:

```json
{
  "action": "list_assessment_questions",
  "filters": {
    "question_ids": [
      "q_platform_dependency",
      "q_external_assets",
      "q_open_source_tooling"
    ]
  },
  "scope": "global"
}
```

## Machine: assess selected domains/questions

One domain:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["software_dependencies_environment"]
  },
  "scope": "global"
}
```

Multiple domains:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": [
      "specification_governance",
      "adoption_community_support",
      "metadata_self_documentation"
    ]
  },
  "scope": "global"
}
```

One or more explicit questions:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "question_ids": [
      "q_specification_disclosure",
      "q_external_assets",
      "q_registry_recognition"
    ]
  },
  "scope": "global"
}
```

Content-specific fidelity:

```json
{
  "action": "assess_format_questions",
  "format": "TIFF",
  "filters": {
    "domains": ["essential_characteristics"],
    "content_type": "image"
  },
  "scope": "global"
}
```

QNL institutional feasibility:

```json
{
  "action": "assess_format_questions",
  "format": "PDF",
  "filters": {
    "domains": ["local_institutional_feasibility"]
  },
  "scope": "institution",
  "institution_id": "qnl"
}
```

## Evidence coverage expectations

The framework contains questions that current sources may not yet answer for many formats. An `unknown` or missing answer is therefore expected during registry enrichment.

Do not convert unknown into Low risk merely to increase completeness.

Use:

```text
list_evidence_gaps
plan_evidence_remediation
```

to determine whether the missing work is:

- new source evidence;
- a source-to-criterion mapping;
- a claim-value-to-framework-answer mapping;
- a framework alignment issue;
- institution-specific evidence.

## Calibration and governance

The current answer options use low/moderate/high **question-level risk semantics** to make evidence interpretation explicit, but the overall framework banding is disabled.

Before enabling overall Low/Moderate/High banding, QNL should validate at minimum:

- whether all 22 questions belong in the production framework;
- which questions are critical;
- content-type applicability rules;
- question weights;
- handling of unknown/abstention;
- evidence-completeness threshold;
- score-band thresholds;
- treatment of version/family evidence;
- local-vs-global scope;
- calibration against known low/moderate/high-risk formats.

Framework changes should be versioned and tested rather than embedded in AI prompts.

## Related documentation

- Human/system interface: [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- Installation and run modes: [`INSTALLATION_SETUP_AND_RUN.md`](INSTALLATION_SETUP_AND_RUN.md)
- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Shared evidence/data model: [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md)
