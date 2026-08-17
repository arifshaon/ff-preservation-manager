# Getting started: clone to preservation-risk assessment

This is the shortest supported path through **both active modules**.

The goal is to prove the full handoff:

```text
source acquisition
 -> canonical registry
 -> criterion mapping
 -> criterion_claims
 -> preservation risk manager
 -> deterministic assessment
```

The quickstart deliberately enables criterion mapping. The ordinary `config/sources.example.json` is useful for registry construction, but it does **not** enable criterion mapping and therefore is not the right starting point for a risk-assessment demo.

## 1. Install both packages

Python 3.10 or later is required.

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

cd qnl_format_registry_builder
python -m pip install -e ".[dev]"

cd ..\preservation_risk_manager
python -m pip install -e ".[dev,ai]"

cd ..
```

The AI extra is not required for the deterministic command below, but installing it now also enables later human-prompt/Azure/local-model modes.

## 2. Build a registry with criterion mapping enabled

Use the dedicated quickstart config:

```powershell
cd qnl_format_registry_builder

python -m registry_builder run `
  --config config\sources.criterion-mapping.quickstart.json `
  --workdir work `
  --out output
```

This configuration:

- uses in-memory storage so MongoDB is not required;
- enables normal exports;
- enables approved criterion mappings;
- includes QNL seed evidence plus NARA, PRONOM and LOC FDD sources;
- pins the NARA release for reproducibility.

It is a demonstration configuration, not a production deployment profile.

## 3. Verify that the handoff data exists

The risk manager needs both canonical format records and criterion claims.

Check the export files:

```powershell
Test-Path output\registry.json
Test-Path output\criterion_claims.jsonl

(Get-Content output\criterion_claims.jsonl | Measure-Object -Line).Lines
```

The first two commands should return `True`, and the claim count should be greater than zero.

If `criterion_claims.jsonl` is missing or empty, do not expect a framework-driven risk assessment to be complete. Check that `criterion_mapping.enabled` is `true`, inspect the registry-builder run report, and validate the mapping configuration.

## 4. Analyse PDF from the exported files

Move to the risk manager:

```powershell
cd ..\preservation_risk_manager

python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --registry-json ..\qnl_format_registry_builder\output\registry.json `
  --format PDF `
  --evidence-summary
```

### Important export handoff behavior

When `--registry-json` points to a registry-builder `registry.json`, the risk manager now automatically looks in the same directory for:

```text
criterion_claims.jsonl
criterion_claims.json
```

and loads the first matching claims export. This fixes the earlier broken handoff where `registry.json` loaded successfully but the separate criterion-claim export was silently ignored.

The result should now show, when evidence is available for the resolved format:

```text
criterion_claims_used > 0
analysis_status = Assessed / Partially Assessed / Needs Assessment
```

and an `analysed_band` only when the framework's completeness/calibration rules permit banding.

For the current three-question example and current mapped PDF evidence, PDF is expected to resolve to the existing deterministic assessment rather than `Not Assessed` caused solely by a missing export handoff.

## 5. Understand the two framework examples

The repository ships two different framework examples.

### Small scoring example

```text
preservation_risk_manager/examples/qnl_sustainability.framework.example.json
```

Use this to exercise deterministic Low/Moderate/High scoring. It is only a three-question example, not the final QNL preservation-risk framework.

### Broad question framework

```text
preservation_risk_manager/examples/qnl_preservation_risk_questions.framework.draft.json
```

This contains the broader 8-domain / 22-question preservation assessment model. It is intentionally marked:

```text
calibration_status = draft_unvalidated
banding_enabled = false
```

It is suitable for question-level assessment and evidence-gap work, but not yet for an approved overall risk ranking.

## 6. Use persistent storage for normal operation

The export quickstart proves the two-package handoff. For operational use, prefer a persistent registry backend such as MongoDB or the file store.

With MongoDB configured, the normal pattern is:

```text
registry_builder writes/updates RegistryStore
        ↓
preservation_risk_manager --storage-config reads the same store
```

Example machine request:

```powershell
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"PDF","scope":"global"}' `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

Using `--storage-config` avoids intermediary exports entirely and is the preferred integration model for persistent services.

## 7. Ask a human question

Once an AI provider is configured:

```powershell
python -m preservation_risk_manager ask `
  "What is the obsolescence risk of PDF?" `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

Normal `ask` output is human-readable. The AI routes the question; deterministic registry/framework logic produces the assessment.

## 8. Where to go next

| Goal | Read |
| --- | --- |
| Understand the whole architecture | [`REPOSITORY_ARCHITECTURE.md`](REPOSITORY_ARCHITECTURE.md) |
| Understand collections/storage handoff | [`DATA_MODEL_AND_STORAGE_INTERFACE.md`](DATA_MODEL_AND_STORAGE_INTERFACE.md) |
| Install/run registry-builder modes | [`../qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md`](../qnl_format_registry_builder/docs/INSTALLATION_SETUP_AND_RUN.md) |
| Add criterion mapping to a source | [`../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md`](../qnl_format_registry_builder/docs/ADDING_CRITERIA_AND_MAPPING_NEW_SOURCES.md) |
| Understand risk-analysis internals | [`../preservation_risk_manager/docs/RISK_ANALYSIS_WORKFLOW.md`](../preservation_risk_manager/docs/RISK_ANALYSIS_WORKFLOW.md) |
| Author/review frameworks | [`../preservation_risk_manager/docs/FRAMEWORKS.md`](../preservation_risk_manager/docs/FRAMEWORKS.md) |
| Human and system queries | [`../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md`](../preservation_risk_manager/docs/HUMAN_AND_SYSTEM_QUERIES.md) |
| Periodic monitoring/reporting | [`../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md`](../preservation_risk_manager/docs/RISK_MONITORING_AND_REPORTING.md) |
