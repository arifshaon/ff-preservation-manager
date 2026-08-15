# Preservation Risk Manager

The risk manager is a standalone Python package under `preservation_risk_manager/`.
Install it before running module or CLI commands; do not rely on `PYTHONPATH=src`.

## Setup

From the package directory:

```powershell
cd preservation_risk_manager
python -m pip install -e ".[dev]"
```

CI uses the same editable install before running tests.

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
