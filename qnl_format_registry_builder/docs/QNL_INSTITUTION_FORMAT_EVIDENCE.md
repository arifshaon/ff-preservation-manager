# QNL institution format evidence

This document explains the QNL-specific institutional evidence source used to add local preservation-risk context to the registry.

The adapter is:

```text
qnl_institution_format_evidence
```

It is intentionally different from `institution_policy_xlsx`.

```text
institution_policy_xlsx
  -> QNL decisions, local risk labels, preservation actions, proposed plans

qnl_institution_format_evidence
  -> QNL evidence used to answer preservation-risk questions later
```

The preservation-risk analysis layer can use these claims to answer questions in the context of QNL, for example whether QNL has staff expertise, tooling, workflows, or local access capability for a format.

## Current seed file

```text
examples/qnl_institution_format_evidence.seed.json
```

The seed file currently contains QNL-specific evidence for:

```text
PDF
  broadly positive QNL evidence across sustainability, technical, media, and institutional criteria

netCDF
  domain-specific scientific-data evidence, with QNL-local gaps in staff expertise, workflow integration, validation tooling, and routine operational support
```

The file is a template. Add future formats by copying one record and changing the `format` block and `claims` list.

## Run with MongoDB

Use:

```text
config/qnl-institution-format-evidence.mongodb.example.json
```

Run:

```powershell
python -m registry_builder run `
  --config config\qnl-institution-format-evidence.mongodb.example.json `
  --workdir work\qnl-evidence `
  --out output\qnl-evidence
```

Because `incremental_source_updates` is enabled, this source can be run after NARA, PRONOM, and LOC. The current QNL evidence contribution is then combined with the latest successful external evidence already stored in the registry.

## JSON shape

```json
{
  "schema_version": "0.1.0",
  "criterion_set": "qnl_preservation_sustainability_criteria_0.1",
  "institution_id": "qnl",
  "institution_name": "Qatar National Library",
  "records": [
    {
      "source_record_id": "qnl-evidence-pdf",
      "format": {
        "name": "PDF",
        "category": "Document",
        "puids": ["fmt/18"],
        "loc_ids": ["fdd000030"],
        "extensions": ["pdf"],
        "mime_types": ["application/pdf"]
      },
      "claims": [
        {
          "criterion_group": "institution",
          "criterion_id": "institution.workflow_integration",
          "evidence_value": "integrated",
          "risk_direction": "lowers_risk",
          "statement": "PDF is integrated into QNL ingest, characterization, preservation, and access workflows.",
          "date_observed": "2026-08-15"
        }
      ]
    }
  ]
}
```

## Claim fields

Recommended fields:

| Field | Purpose |
| --- | --- |
| `criterion_group` | Broad group, for example `sustainability`, `technical`, `media.dataset`, or `institution`. |
| `criterion_id` | Stable criterion identifier used by future preservation-risk frameworks. |
| `evidence_value` | Controlled local evidence value, for example `integrated`, `not_integrated`, or `requires_specialist_review`. |
| `risk_direction` | QNL-local direction: `lowers_risk`, `raises_risk_for_qnl`, `mixed`, or `uncertain`. |
| `statement` | Human-readable QNL evidence statement. |
| `source` | Evidence source or review source. Defaults to the package source if omitted. |
| `evidence_owner` | Owning team or person. Defaults to QNL DCPA if omitted. |
| `date_observed` | Date the local evidence was observed or reviewed. |
| `review_due` | Optional date for re-review. |
| `review_status` | Defaults to `approved`. Use `needs_review` for incomplete claims. |
| `derived_by` | Defaults to `human`. AI-derived claims must be explicitly marked and should not be assessable by default. |

## Criteria covered by the seed data

The seed data uses criteria aligned with preservation sustainability and institutional readiness:

```text
sustainability.disclosure
sustainability.adoption
sustainability.transparency_readability
sustainability.self_documentation
sustainability.external_dependencies
sustainability.ip_licensing
sustainability.tpm_encryption
technical.container_complexity
technical.compression
technical.accessibility_features
media.document.text_and_layout_preservation
media.dataset.data_type_preservation
media.dataset.schema_definition
institution.software_hardware_availability
institution.staff_expertise
institution.workflow_integration
institution.validation_tooling
institution.scale_storage_cost
```

## Identifier handling

QNL evidence rows may carry copied PUIDs or LOC identifiers so the evidence can attach to the right canonical format.

Those copied identifiers are not verified by QNL. They remain claims.

If the registry already contains a verified PRONOM or LOC group for the same identifier, reconciliation may use the copied identifier as a safe bridge to attach the QNL evidence to that canonical group.

Example:

```text
PRONOM source verifies fmt/18
QNL evidence row claims fmt/18
-> QNL evidence attaches to canonical group puid-fmt-18
-> QNL's copied PUID claim remains unverified
```

This preserves the authority boundary while making local evidence usable.

## How future LLM analysis should use this

The future `preservation_risk_analysis` package should place approved human QNL claims into the assessable evidence pack:

```json
{
  "assessable": {
    "institutional_evidence": [
      {
        "criterion_id": "institution.workflow_integration",
        "evidence_value": "integrated",
        "statement": "PDF is integrated into QNL preservation workflows.",
        "institution_id": "qnl",
        "derived_by": "human",
        "review_status": "approved"
      }
    ]
  }
}
```

AI-derived claims should remain contextual until human-approved.

```text
LLM can use approved QNL evidence to answer controlled framework questions.
LLM must not convert QNL evidence directly into final risk bands or scores.
```
