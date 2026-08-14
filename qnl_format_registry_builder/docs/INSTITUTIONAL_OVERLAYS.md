# Institutional Policy Overlays

## Purpose

The registry builder must be usable by QNL and by other libraries, archives, repositories, and memory institutions. For that reason, the core model is institution-neutral.

The core registry answers questions such as:

- What file format is this?
- Which identifiers belong to it?
- What do authoritative sources say about it?
- What is the reconciled hazard assessment?
- Which reusable preservation method profiles apply?

An institutional overlay answers different questions:

- Does this institution currently track this format?
- What local identifier does this institution use?
- What local risk term was recorded in its policy spreadsheet?
- What preservation action or plan has the institution selected?
- Which local tools, workflows, or readiness assumptions are recorded?

QNL is therefore not hard-coded into the model. QNL is the first configured institutional profile.

## Core principle

```text
Canonical registry = global format identity and shared evidence
Institutional overlay = local policy, local terminology, local action state
```

The same canonical format can have several institutional overlays:

```json
{
  "canonical_id": "fmt-chemical-markup-language",
  "preferred_name": "Chemical Markup Language",
  "institution_policy_overlays": [
    {
      "institution_id": "qnl",
      "institution_name": "Qatar National Library",
      "institution_format_id": "QNL_095_Chemical_Markup_Language_(CML)",
      "local_risk_level": "Moderate Risk",
      "local_preservation_action": "Preserve"
    },
    {
      "institution_id": "example_university",
      "institution_name": "Example University Repository",
      "institution_format_id": "EUR-FMT-118",
      "local_risk_level": "Watch",
      "local_preservation_action": "Review"
    }
  ]
}
```

## Source adapter

The preferred spreadsheet adapter is now:

```text
institution_policy_xlsx
```

It accepts institution metadata in configuration:

```json
{
  "id": "qnl_policy_current",
  "type": "institution_policy_xlsx",
  "institution_id": "qnl",
  "institution_name": "Qatar National Library",
  "institution_format_id_prefix": "QNL",
  "uris": ["input/QNL File Format Policy and Action Plan_27_November_2025.xlsx"],
  "field_map": {
    "institution_format_id": ["QNL Format ID"],
    "name": ["Digital file"],
    "extensions": ["File Extension(s)"],
    "risk_level": ["QNL Risk Level", "Risk Level", "Risk"]
  }
}
```

The old adapter name remains available as a compatibility alias:

```text
qnl_policy_xlsx
```

New configurations should not use it.

## Field mapping

Institutional spreadsheets are expected to differ. The adapter therefore does not assume fixed QNL column names. Each source declares a field map.

Logical fields include:

| Logical field | Meaning |
|---|---|
| `institution_format_id` | Local institutional identifier for the policy row |
| `name` | Format display name in the spreadsheet |
| `extensions` | File extensions claimed by the institution |
| `mime_types` | MIME/media types claimed by the institution |
| `category` | Local category, collection plan, or format family |
| `description` | Local description/justification text |
| `risk_level` | Local risk term |
| `preservation_action` | Local preservation action |
| `proposed_preservation_plan` | Local plan or treatment |
| `preferred_tools` | Local tools named in the policy |
| `conversion_process` | Local conversion or processing pathway |
| `pronom_url` | PRONOM link or PUID column |
| `loc_url` | Library of Congress FDD link or identifier |
| `wikidata_url` | Wikidata link or identifier |

Each mapping can be a single header or a list of acceptable headers:

```json
{
  "description": [
    "Description and Justification",
    "Description/Justification",
    "Description",
    "Justification"
  ]
}
```

If a declared field cannot be found, extraction fails loudly. This avoids silent binding errors such as mapping `format` to `qnl_format_id`.

## Output model

Institutional policy data is stored on canonical format records as:

```text
institution_policy_overlays
```

The old name `qnl_policy_overlay` should not be used in new code.

The generic overlay uses local-policy field names:

```json
{
  "institution_id": "qnl",
  "institution_name": "Qatar National Library",
  "institution_format_id": "QNL_095_Chemical_Markup_Language_(CML)",
  "local_risk_level": "Moderate Risk",
  "local_preservation_action": "Preserve",
  "local_preservation_plan": "Preserve original CML and validate XML/CML where possible.",
  "local_preferred_tools": "Open Babel",
  "local_conversion_process": "Generate chemistry-aware access derivative if needed.",
  "source_file": "input/QNL File Format Policy and Action Plan_27_November_2025.xlsx",
  "source_row": 95
}
```

## Hazard reconciliation

Local institutional risk terms can be one estimator of hazard, but they are not automatically the source of truth.

The hazard model should reconcile:

```text
external estimator + institutional estimator
```

It should not add them together.

When only an institutional policy spreadsheet is loaded, the expected basis is usually:

```text
qnl_only or institutional_only, depending on current label naming
```

When a NARA adapter is added, the system can produce:

```text
external_only
corroborated
qnl_override / institutional_override
divergence requiring review
```

Future code should rename the remaining `qnl_only` basis label to `institution_only`; until then, the semantics are local-institution-only.

## Data quality

Duplicate institutional policy IDs should be warnings, not silent merges.

For example, if two PDF/X rows share the same local format ID, the registry builder should surface this as a source-data quality warning. It should not silently decide that the rows are the same format unless strong verified identifiers support that conclusion.

## Migration notes

Preferred names going forward:

| Deprecated / QNL-specific | Preferred / institution-neutral |
|---|---|
| `qnl_policy_xlsx` | `institution_policy_xlsx` |
| `qnl_policy_overlay` | `institution_policy_overlays` |
| `qnl_format_id` | `institution_format_id` |
| `spreadsheet_risk_level` | `local_risk_level` |
| `preservation_action` | `local_preservation_action` |
| `proposed_preservation_plan` | `local_preservation_plan` |
| `preferred_tools` | `local_preferred_tools` |
| `conversion_process` | `local_conversion_process` |

QNL-specific examples are still useful, but they belong in configuration and documentation, not in the core domain model.
