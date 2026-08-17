# Preservation Risk Manager

The risk manager is a standalone Python package under `preservation_risk_manager/`.
Install it before running module or CLI commands; do not rely on `PYTHONPATH=src`.

It contains the deterministic preservation-risk engine and now also provides a provider-neutral AI interface for the future File Format Preservation Risk Assistant.

## Setup

From the package directory:

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev]"
```

To use hosted or OpenAI-compatible AI providers:

```powershell
python -m pip install -e ".[dev,ai]"
```

CI uses the editable install before running tests.

## Run tests

```powershell
pytest -q
```

## Analyze one format from a registry export

```powershell
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --registry-json ..\qnl_format_registry_builder\out\registry.json `
  --format fmt/18 `
  --institution qnl `
  --readiness-status Covered `
  --exposure-level High
```

## Analyze one format from the registry-builder storage backend

```powershell
python -m preservation_risk_manager analyze-format `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --format fmt/18 `
  --institution qnl `
  --readiness-status Covered `
  --exposure-level High
```

`--storage-config` may point to either a storage block or a full registry-builder config containing a top-level `storage` object.

## Resolution failures

Ambiguous or missing format resolution returns JSON with a top-level `status` and exits non-zero. For example, extension-based `pdf` resolution may match many PDF variants; use a canonical ID or PUID instead.

## AI provider interface

The AI layer is intentionally provider-neutral. Preservation evidence, framework rules, scoring, risk bands, and institutional posture remain application-owned and deterministic. The provider supplies model inference only.

The first concrete provider is Azure OpenAI. The example configuration already contains the QNL endpoint:

```text
examples/ai.azure.example.json
```

Copy it to a local ignored file and replace the API-key and deployment placeholders:

```powershell
mkdir config
Copy-Item examples\ai.azure.example.json config\ai.local.json
```

Validate/redact the configuration without contacting Azure:

```powershell
python -m preservation_risk_manager.ai info `
  --config config\ai.local.json
```

Run a manual provider smoke test after supplying a real key and deployment name:

```powershell
python -m preservation_risk_manager.ai query `
  --config config\ai.local.json `
  --prompt "Reply with a short confirmation that the preservation AI provider is available."
```

The same interface also has an `openai_compatible` provider path for future hosted or local inference servers. See [`docs/AI_PROVIDER_INTERFACE.md`](docs/AI_PROVIDER_INTERFACE.md) for configuration, structured-output, tool-calling, local-model, and secret-handling details.

The next implementation step is to expose preservation tools such as `assess_format` and connect AI interpretation to unresolved framework questions while keeping final scoring deterministic.
