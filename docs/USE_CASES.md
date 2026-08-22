# Use cases

This guide is for someone who wants to use the system rather than study its implementation.

## Identifier cheat sheet

The safest way to assess one format is to use a strong authority identifier.

| Identifier | Example | Owner / meaning |
| --- | --- | --- |
| PRONOM PUID | `fmt/276` | PRONOM Unique Identifier. `fmt/276` is PDF 1.7. |
| LOC FDD ID | `fdd000030` | Library of Congress Format Description Document identifier. |
| NARA format ID | `NF00123` | NARA Digital Preservation Framework identifier. |
| Canonical ID | `puid-fmt-276` | Internal reconciled registry identity, not an external authority namespace. |
| Extension | `.pdf` | Weak/ambiguous observation; many format versions may share it. |
| MIME type | `application/pdf` | Useful but often not version-specific. |

### Why use a PUID?

A PUID such as `fmt/276` identifies a specific PRONOM format/version. It is much safer than asking for `.pdf`, because the extension can match many PDF variants.

The resolver deliberately does not guess when an identifier/name/extension is ambiguous.

---

## Use case 1 — Check one format without AI

Goal: use only governed evidence already in the local registry.

From `preservation_risk_manager`:

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-mode off
```

For PDF 1.7 in the current reviewed data, the important model is:

```text
exact-format NARA assessment
+ broader PDF-group DPC context
-> configured scope-aware governed synthesis
```

The tool preserves source-native labels and scales. It does not average NARA and DPC numeric values.

---

## Use case 2 — Check the same format with AI

```powershell
python -m preservation_risk_manager ask `
  "What is the preservation risk of fmt/276?" `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --ai-mode synthesize
```

The AI receives the resolved format, collected registry/source evidence, governed baseline, active synthesis methodology and assessment framework.

The output keeps these separate:

```text
Governed config baseline
AI-assisted synthesis
```

The AI may agree or disagree. Its risk level does not rewrite the database.

When provider-hosted web search is available and permitted, the model may use it. Any external information must remain distinguishable from registry evidence.

---

## Use case 3 — Inspect exactly what was sent to AI

Add to the local AI configuration:

```json
{
  "ai": {
    "input_log_file": "logs/ai-inputs.jsonl"
  }
}
```

Run the normal query. Each AI call is appended as JSONL after token-budget compaction, including the actual messages/schema/options sent to the provider.

The log excludes the API key, but the prompt may contain sensitive assessment evidence. Do not commit it.

---

## Use case 4 — Assess several formats as a batch

Use the committed watchlist:

```text
monitoring/watchlist.csv
```

It currently contains a small PDF version family example.

Without AI:

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\pdf-watchlist `
  --ai-mode off
```

With AI:

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\pdf-watchlist-ai `
  --ai-mode synthesize `
  --ai-config config\ai.local.json
```

Outputs:

```text
risk-report.html   curator-facing searchable report
risk-report.csv    compact summary
risk-report.json   detailed audit record
risk-report.zip    portable bundle
```

---

## Use case 5 — Make your own watchlist

CSV:

```csv
puid,label,notes
fmt/276,PDF 1.7,Example
fmt/18,PDF 1.4,Example
```

The parser recognizes identifier columns such as:

```text
puid
pronom_puid
pronom_id
format_id
format
id
```

`label` and `notes` are documentation only; resolution uses the identifier field.

A plain text file with one identifier per line also works.

---

## Use case 6 — Run a single-format smoke test before a larger AI batch

A one-row file is already committed:

```text
monitoring/watchlist.single.csv
```

```powershell
python -m preservation_risk_manager batch-report `
  --input monitoring\watchlist.single.csv `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --output monitoring-reports\smoke `
  --ai-mode synthesize `
  --ai-config config\ai.local.json
```

This is useful before spending provider tokens on a larger watchlist.

---

## Use case 7 — Ask for canonical JSON instead of human text

For system integration, use the controlled request interface rather than parsing rendered prose.

Example request file:

```json
{
  "action": "assess_format",
  "format": "fmt/276",
  "scope": "global"
}
```

Run:

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json
```

This is the better integration surface for applications/services.

---

## Use case 8 — Use the curator web application

Start:

```powershell
python -m preservation_risk_manager.web_cli `
  --framework examples\qnl_preservation_risk_questions.framework.draft.json `
  --storage-config ..\qnl_format_registry_builder\config\sources.qnl.json `
  --ai-config config\ai.local.json `
  --host 127.0.0.1 `
  --port 8080
```

Open:

```text
http://127.0.0.1:8080/
```

The web application runs human and batch requests as background jobs and exposes completed report artifacts for download.

See [`API_AND_SWAGGER.md`](API_AND_SWAGGER.md).

---

## Use case 9 — Investigate an apparently strange result

Recommended order:

1. confirm the requested identifier resolved to the intended format/version;
2. inspect source assessments and their scopes;
3. inspect native terminology and its configured mapping;
4. inspect which scope contributed to the governed headline;
5. treat broader scope as context according to the active policy;
6. inspect AI rationale/uncertainty separately;
7. enable AI input logging if you need to audit the exact prompt;
8. inspect external URLs if web search was used.

Do not change source/registry data merely because a result has low evidence coverage.

## Next

- AI setup: [`AI_PROVIDERS.md`](AI_PROVIDERS.md)
- Batch/update operations: [`OPERATIONS.md`](OPERATIONS.md)
- Risk terminology/governance: [`../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md`](../preservation_risk_manager/docs/RISK_SYNTHESIS_AND_TERMINOLOGY.md)
