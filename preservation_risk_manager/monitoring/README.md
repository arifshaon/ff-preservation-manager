# Monitoring watchlist examples

These committed files can be used directly with `preservation_risk_manager batch-report`.

## Files

- `watchlist.single.csv` — one-format smoke test using PDF 1.7 (`fmt/276`). Useful for quickly checking governed synthesis and optional AI synthesis.
- `watchlist.csv` — small PDF-family/version watchlist covering PDF 1.4–1.7 (`fmt/18`, `fmt/19`, `fmt/20`, `fmt/276`).

The batch parser uses the recognized identifier column (`puid` here). `label` and `notes` are human-readable documentation and do not affect resolution or scoring.

## Run without AI

From `preservation_risk_manager`:

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\sample-no-ai `
  --ai-mode off
```

For the smallest smoke test, replace `watchlist.csv` with `watchlist.single.csv`.

## Run with AI-assisted synthesis

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\sample-ai `
  --ai-mode synthesize `
  --ai-config config\ai.local.json
```

Expected report artifacts:

```text
risk-report.html
risk-report.csv
risk-report.json
risk-report.zip
```

The governed database synthesis remains visible separately from the AI-assisted synthesis.

## Create an operational watchlist

Copy one of the examples and replace/add rows using verified format identifiers, preferably PRONOM PUIDs:

```csv
puid,label,notes
fmt/276,PDF 1.7,Example
```

The additional columns are optional; a file containing only a `puid` column also works.
