# Persistent source integration

## Storage boundary

Source-native acquisition artifacts remain immutable files under `work/snapshots/` (or another configured snapshot location). MongoDB does not replace those artifacts and is not used as a binary source-file store.

MongoDB stores the structured integration state produced from those acquisitions, including:

- runs
- source snapshot metadata and hashes
- source records
- canonical formats
- identifier claims
- institutional policy overlays
- hazard/risk assessments
- readiness assessments
- trend observations
- criterion claims
- assessment changes

This keeps source acquisition auditable while allowing the integrated registry to evolve incrementally.

## Production-style config

`config/sources.qnl.json` uses:

```json
{
  "storage": {
    "type": "mongodb",
    "uri": "mongodb://localhost:27017",
    "database": "qnl_format_registry"
  }
}
```

The MongoDB backend is the persistent registry store. File exports are review/interchange products only.

## First persistent ingest: DPC only

Use `config/sources.qnl.dpc-only.json` for the first persistence test. It contains only the pinned 2025 DPC Bit List source and disables file exports.

Expected behavior:

- 84 latest DPC source records
- all 84 records have `record_role=evidence_only`
- zero canonical formats are created

Install Mongo support:

```powershell
python -m pip install -e ".[mongo]"
```

Run the first ingest:

```powershell
python -m registry_builder run `
  --config config/sources.qnl.dpc-only.json `
  --workdir work `
  --out out/dpc-first-ingest
```

Verify the persistent store:

```powershell
python -m registry_builder.storage_status `
  --config config/sources.qnl.dpc-only.json `
  --expect-source dpc_bit_list_2025 `
  --expect-records 84 `
  --expect-evidence-only 84 `
  --expect-canonical 0
```

The verification command exits non-zero if any expectation fails.

## Incremental integration sequence

After the DPC-only persistence check succeeds, add validated identity/risk sources one at a time against the same `qnl_format_registry` database:

1. DPC evidence
2. NARA
3. PRONOM
4. LOC FDD
5. Wikidata only after its source-native projection/classification layer is implemented and validated
6. QNL institutional policy when ready

With `incremental_source_updates=true`, each successful source run uses its fresh contribution plus the latest successful stored contributions from other sources, then rebuilds the canonical registry. Historical source runs and immutable acquisition snapshots remain available for audit.
