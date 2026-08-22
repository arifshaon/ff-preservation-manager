# Preservation-risk assessment questions

This document summarizes the broad QNL working question set implemented in:

```text
examples/qnl_preservation_risk_questions.framework.draft.json
```

It is intended for file-format sustainability, obsolescence, data-loss, and institutional-feasibility assessment. It is informed by preservation concepts used by memory institutions, including Library of Congress sustainability factors and NARA preservation considerations, but it is **not** a verbatim LOC or NARA questionnaire.

Current framework status:

```text
framework_id: qnl_preservation_risk_questions
version: 0.1.0-draft
calibration_status: draft_unvalidated
banding_enabled: false
```

The questions are usable for evidence collection, targeted assessment, gap analysis, and human/system queries. Overall framework Low/Moderate/High banding remains disabled until QNL validates the weighting and thresholds.

## Domains at a glance

| Domain ID | Domain | Questions |
| --- | --- | ---: |
| `specification_governance` | Specification Disclosure & Governance | 3 |
| `software_dependencies_environment` | Software Dependencies & Environment | 3 |
| `adoption_community_support` | Adoption & Community Support | 3 |
| `technical_structure_transparency` | Technical Structure & Transparency | 3 |
| `intellectual_property_rights` | Intellectual Property & Rights Management | 2 |
| `metadata_self_documentation` | Metadata & Self-Documentation | 2 |
| `essential_characteristics` | Essential Characteristics / Content Fidelity | 3 |
| `local_institutional_feasibility` | Local Institutional Feasibility | 3 |
|  | **Total** | **22** |

## 1. Specification Disclosure & Governance

### `q_specification_disclosure`

Is the specification fully disclosed and publicly accessible? Could an independent developer implement a reader or converter without reverse-engineering?

### `q_specification_governance`

Who maintains the specification? Is stewardship distributed through an open standards body or concentrated in one vendor/organization?

### `q_specification_stability`

Is the specification stable over time, or do major revisions create backward-compatibility or preservation problems?

## 2. Software Dependencies & Environment

### `q_platform_dependency`

Does rendering depend on specific operating systems, proprietary software, specialist runtimes, or legacy hardware?

This concerns dependencies outside the file that are required to use it.

### `q_external_assets`

Does successful rendering depend on resources outside the file, such as unembedded fonts, DLLs, linked spreadsheets, plugins, or network endpoints?

An asset successfully embedded inside the file is not an external dependency merely because the format supports embedding.

### `q_open_source_tooling`

Are viable open-source viewers, validators, extraction tools, or converters available, or is use concentrated in licensed vendor software?

## 3. Adoption & Community Support

### `q_adoption`

How widely is the format adopted within its actual creator/user community? Domain-specific use is not automatically equivalent to abandonment.

### `q_third_party_support`

Are third-party applications actively maintaining read/write support, rather than merely retaining historical compatibility?

### `q_registry_recognition`

Can the format be reliably identified through formal identifiers such as a PRONOM PUID, MIME type, or comparable registry identifier?

An extension alone is weak evidence of reliable identification.

## 4. Technical Structure & Transparency

### `q_byte_transparency`

How transparent is the internal representation? Is it directly inspectable text/XML or an opaque binary representation?

Binary does not automatically mean High risk; documentation and tooling matter.

### `q_compression`

What compression mechanism is used: uncompressed, lossless, or lossy? Does the encoding choice materially constrain preservation or future transformation?

Compression itself is not obsolescence.

### `q_lossy_migration`

If migration/transcoding becomes necessary, could it irreversibly lose essential/significant characteristics?

This is distinct from whether the source format itself happens to use lossy compression.

## 5. Intellectual Property & Rights Management

### `q_ip_constraints`

Do active patents, licensing fees, implementation restrictions, or comparable IP constraints materially affect preservation tooling?

Ordinary trademark ownership is not automatically an implementation barrier.

### `q_tpm_drm`

Can DRM, encryption, passwords, keys, or other technological protection measures prevent indexing, validation, extraction, or transformation?

The framework distinguishes a format's capability to support protection from an actual protected file that cannot be processed.

## 6. Metadata & Self-Documentation

### `q_embedded_metadata`

Can the file carry useful technical, descriptive, or structural metadata internally, for example XMP, EXIF, or comparable native metadata?

### `q_accessibility_features`

Can relevant accessibility semantics be represented and preserved, such as tagged structure, alternative text, captions, or other content-type-appropriate features?

## 7. Essential Characteristics / Content Fidelity

These questions are content-type specific. Machine requests should provide `content_type` when possible.

### `q_image_fidelity`

For images/graphics, can required bit depth, colour information/profiles, resolution, and vector characteristics be preserved?

### `q_av_fidelity`

For audio/video, can required timecodes, multi-track audio, subtitles/captions, and other significant AV characteristics be preserved?

### `q_data_fidelity`

For data/spreadsheets, can explicit data types, formulas, relationships, and semantics be preserved rather than flattened to static values?

## 8. Local Institutional Feasibility

These questions should normally use institution-scoped evidence. They are not universal properties of the format.

### `q_local_capability`

Does the institution currently possess the software infrastructure and staff expertise required to identify, validate, render, or otherwise manage the format?

### `q_migration_pathways`

Are established and preferably tested migration pathways/tools available for the institution?

A hypothetical converter is weaker evidence than a tested preservation pathway.

### `q_storage_overhead`

Are storage, transfer, network, and processing overheads sustainable at the institution's collection scale?

Large files are not automatically High risk when the institution has adequate capacity.

## Important interpretation rules

The question set deliberately avoids several common shortcuts:

```text
missing evidence != Low risk
binary != automatically High risk
lossy compression != lossy migration risk
format supports encryption != every file is encrypted
one open-source viewer != broad tooling resilience
one local limitation != universal format weakness
extension match != reliable identity
```

Source evidence should retain its original semantics. A source field should map to a question only when the meaning is defensible, not merely because the wording looks similar.

## List the question catalogue

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

Specific questions:

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

## Assess selected questions

One domain:

```json
{
  "action": "assess_format_questions",
  "format": "fmt/276",
  "filters": {
    "domains": ["software_dependencies_environment"]
  },
  "scope": "global"
}
```

Explicit questions:

```json
{
  "action": "assess_format_questions",
  "format": "fmt/276",
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

Content-specific assessment:

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

Institutional feasibility:

```json
{
  "action": "assess_format_questions",
  "format": "fmt/276",
  "filters": {
    "domains": ["local_institutional_feasibility"]
  },
  "scope": "institution",
  "institution_id": "qnl"
}
```

## Evidence gaps

Many formats will not have evidence for all 22 questions. That is expected.

Use:

```text
list_evidence_gaps
plan_evidence_remediation
```

to distinguish among:

- source evidence that does not exist;
- evidence present but not mapped;
- evidence mapped to a different framework area;
- framework alignment issues;
- institution-specific evidence still required.

Do not create weak mappings merely to increase completeness.

## Calibration and governance

Before overall framework banding is enabled, QNL should validate at minimum:

- whether all 22 questions belong in the production framework;
- critical-question designation;
- content-type applicability;
- weights;
- unknown/abstention handling;
- evidence-completeness threshold;
- Low/Moderate/High thresholds;
- treatment of version/family evidence;
- local-versus-global scope;
- calibration against known examples.

The question framework is one evidence-analysis layer. It is separate from the governed source-level overall-risk synthesis described in the repository architecture.

## Related documentation

- Installation: [`../../docs/INSTALLATION.md`](../../docs/INSTALLATION.md)
- Repository architecture: [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- Data model: [`../../docs/DATA_MODEL.md`](../../docs/DATA_MODEL.md)
- Human/system interface: [`HUMAN_AND_SYSTEM_QUERIES.md`](HUMAN_AND_SYSTEM_QUERIES.md)
- Framework schema/governance: [`FRAMEWORKS.md`](FRAMEWORKS.md)
- Risk-analysis workflow: [`RISK_ANALYSIS_WORKFLOW.md`](RISK_ANALYSIS_WORKFLOW.md)
