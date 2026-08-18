# Rebuild the Registry from Stored Source Records

Use this workflow when source acquisition is already present in the persistent RegistryStore but canonical reconciliation or criterion attribution needs to be rerun after builder changes.

The command does **not** redownload PRONOM, NARA, LOC, QNL, or other configured authorities. It selects the latest completed stored source-record set for each source, re-normalizes it under the current identifier rules, then reruns:

```text
stored source records
  -> normalization
  -> canonical reconciliation
  -> method-profile assignment
  -> validation
  -> approved criterion mapping
  -> change detection
  -> reviewable exports
  -> optional persistence with --apply
```

## Why this rebuild exists

A reconciliation regression could split one real format across several current canonical records. For example, a NARA record that cited both PRONOM `fmt/14` and LOC `fdd000316` could stop merging into the PRONOM canonical after the LOC source was added to a later run.

The corrected model uses the verified PRONOM PUID as the preferred exact format/version identity where available. Copied authority identifiers remain provenance/cross-reference evidence. Multi-PUID LOC records remain independently addressable by LOC ID and are linked as evidence sources to each explicitly cited PUID rather than being collapsed into one arbitrary PUID.

See `IDENTIFIER_RECONCILIATION.md` for the full rules.

## 1. Install/update

From the repository root:

```powershell
cd "C:\Users\Arif Shaon\Tools\ff-preservation-manager"
git switch main
git pull --ff-only origin main

cd .\qnl_format_registry_builder
python -m pip install -e ".[dev,mongo]"
pytest -q
```

Do not apply a registry rebuild until the builder tests pass locally.

## 2. Dry run first

The rebuild is dry-run by default:

```powershell
python -m registry_builder.rebuild_store `
  --config config\sources.criterion-mapping.mongodb.example.json `
  --out output-rebuild-dry-run
```

A dry run:

- reads MongoDB;
- reuses stored source records;
- does not reacquire external sources;
- does not modify current canonical formats;
- does not modify current criterion claims;
- does not write a rebuild run into MongoDB;
- writes the proposed rebuilt registry and claims to the output directory.

Review at least:

```text
output-rebuild-dry-run/registry.json
output-rebuild-dry-run/criterion_claims.json
output-rebuild-dry-run/run_report.json
```

The console must report:

```text
Persisted to store: False
```

Validation errors abort the rebuild before persistence is possible.

## 3. Inspect the PDF 1.0 repair in the dry-run export

The proposed current `puid-fmt-14` should represent the PRONOM format/version identity and should include the verified NARA ID after reconciliation.

Expected shape:

```text
canonical_id:  puid-fmt-14
PUID:          fmt/14
NARA:          NF00362
version:       1.0
```

`fdd000316` should remain a LOC canonical/source record rather than becoming an exact LOC identifier of `puid-fmt-14`.

The `puid-fmt-14.source_records` list should contain the LOC relationship with metadata similar to:

```json
{
  "source_id": "loc_fdd_xml",
  "source_record_id": "fdd000316",
  "relationship": "explicit_puid_cross_reference",
  "evidence_scope": "multi_puid_source_record",
  "related_puids": ["fmt/14", "fmt/15", "fmt/16", "fmt/17"]
}
```

Approved NARA and LOC mappings should generate criterion claims directly for `puid-fmt-14`, including the applicable PDF evidence already stored in MongoDB.

## 4. Run the criterion evidence audit on the proposed export

Use the existing read-only criterion evidence audit to see what source fields remain unmapped after the structural repair. Keep draft mappings separate from approved production claims.

The NARA approved mapping currently contains a reviewed subset of the full rubric. The full 27-rule NARA mapping remains a draft review scaffold and must not be silently promoted by the rebuild.

## 5. Apply only after reviewing the dry run

When the proposed registry looks correct:

```powershell
python -m registry_builder.rebuild_store `
  --config config\sources.criterion-mapping.mongodb.example.json `
  --out output-rebuild-applied `
  --apply
```

The console must report:

```text
Persisted to store: True
```

The apply run:

- updates/creates the rebuilt canonical records;
- marks canonical records absent from the rebuilt view as `current: false`;
- regenerates approved criterion claims and supersedes replaced current claims;
- records canonical change events;
- leaves the previously acquired source records and snapshots intact.

Historical `format_identifiers` rows may remain for provenance/history, but current identifier resolution uses `canonical_formats.identifiers`, so an obsolete historical copied identifier cannot become a current identity again.

## 6. Re-run the risk tests

After applying:

```powershell
cd ..\preservation_risk_manager
python -m pip install -e ".[dev,ai,web]"
pytest -q
```

Then test PDF 1.0 directly:

```powershell
python -m preservation_risk_manager ask "What is the risk of fmt/14?" `
  --framework examples\qnl_sustainability.framework.example.json `
  --storage-config ..\qnl_format_registry_builder\config\storage.mongodb.example.json `
  --ai-config config\ai.local.json `
  --ai-mode off
```

Use `--ai-mode off` for this verification. The purpose is to confirm that deterministic registry evidence now reaches the framework without AI filling the gaps.

## 7. Recheck broad PDF coverage

Once `fmt/14` is correct, rerun the broad PDF human query and a batch report for representative PDF PUIDs. Compare:

- criterion claims used;
- evidence completeness;
- analysis status;
- assigned/suppressed risk band;
- unresolved questions.

Any remaining gaps after the structural repair should then be classified as true mapping/evidence coverage work rather than reconciliation failures.
