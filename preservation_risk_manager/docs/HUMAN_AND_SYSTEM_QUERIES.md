# Human and system preservation-risk queries

The preservation-risk manager exposes one canonical request/response layer for both conversational use and system integration.

## Human prompt

A human question is routed by the configured AI provider into a controlled request. The AI does not calculate or invent the risk result; it selects an action and parameters only.

```powershell
python -m preservation_risk_manager ask `
  "What is the obsolescence risk of PDF?" `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

```powershell
python -m preservation_risk_manager ask `
  "Give me the PDF formats that are at risk" `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json
```

Use `--institution qnl` when the same human question should default to QNL-scoped evidence.

The command always emits JSON, including the routed request and router metadata.

## Structured system request

Systems can bypass natural-language routing and submit the controlled request directly.

```json
{
  "action": "assess_format",
  "format": "fmt-pdf",
  "scope": "global"
}
```

```json
{
  "action": "list_at_risk_formats",
  "filters": {
    "family": "PDF",
    "risk_bands": ["Moderate", "High"]
  },
  "scope": "global",
  "limit": 500
}
```

Execute a request file:

```powershell
python -m preservation_risk_manager query-json `
  --request request.json `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

Or submit literal JSON:

```powershell
python -m preservation_risk_manager query-json `
  --request-json '{"action":"assess_format","format":"fmt-pdf","scope":"global"}' `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json
```

## Supported actions

- `assess_format` — resolve and assess one format.
- `search_formats` — discover matching canonical formats without scoring them.
- `assess_format_family` — assess and rank formats matching a family/search term.
- `list_at_risk_formats` — assess, filter, and rank matching formats by requested risk bands. If bands are omitted, `Moderate` and `High` are used.

## Canonical response

A successful single-format response contains the framework identity, normalized request, scope, format identity, deterministic risk band/score, evidence completeness, question results, main non-zero risk factors, criterion-claim count, and evidence hash.

A batch response contains the same assessment object for each result plus `candidate_count`, `result_count`, and applied filters. Batch results are ordered High → Moderate → Low, then by descending score.

The AI router is deliberately outside the deterministic scoring path. A human prompt and an equivalent structured request therefore use the same registry evidence and scoring engine.
