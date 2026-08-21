# Persistent integration: source-by-source production runbook

This is the **operator runbook for building the QNL file-format registry from an empty MongoDB database, one source at a time**.

The intended operating model is deliberately source-by-source. Do not enable every source at once for a clean-room build. Each source is acquired, persisted, verified, and—where required—its approved criterion/risk/relationship claims are materialized before moving to the next source.

The current recommended order is:

```text
1. PRONOM
2. LOC FDD XML
3. LOC crosswalk / approved LOC-PRONOM bridge
4. LOC sustainability criterion claims
5. NARA Digital Preservation Framework
6. NARA governed risk claims
7. DPC Global Bit List
8. DPC governed risk claims
9. Wikidata evidence + governed relationships
10. Final storage/registry verification
```

This order establishes authoritative format identities before adding evidence-only and relationship-only sources.

> Important: the individual source adapters, reviewed mappings, risk semantics, Wikidata population policy, and identity rules are already encoded in the repository. An operator should not repeat the exploratory source-analysis/fine-tuning that was required during development. If a current upstream source has changed materially, the workflow should stop at its validation/drift gate for review rather than silently changing the policy.

---

## 1. Prerequisites

Run all commands from the repository subdirectory:

```text
ff-preservation-manager/qnl_format_registry_builder
```

### 1.1 Python environment

Python 3.10 or later is required.

Windows PowerShell example:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mongo]"
```

The `mongo` extra installs `pymongo`; the `dev` extra installs pytest.

### 1.2 MongoDB

The production-style QNL configs currently expect:

```text
URI:      mongodb://localhost:27017
Database: qnl_format_registry
```

MongoDB creates the database/collections on first write; you do not have to create them manually.

You can use either a normal local MongoDB service or a container. For example, with Docker:

```powershell
docker run --name qnl-format-mongo -p 27017:27017 -d mongo:8
```

If MongoDB is installed as a Windows service, confirm/start it using the normal Windows service tools.

Verify connectivity through the same Python driver used by the project:

```powershell
@'
from pymongo import MongoClient
client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=5000)
print(client.admin.command("ping"))
client.close()
'@ | python -
```

A successful response contains `ok: 1.0`.

### 1.3 Optional: deliberately start from an empty database

Only do this when you intentionally want to destroy the existing local registry and rebuild from scratch:

```powershell
@'
from pymongo import MongoClient
client = MongoClient("mongodb://localhost:27017")
client.drop_database("qnl_format_registry")
print("Dropped qnl_format_registry")
client.close()
'@ | python -
```

**This is destructive. Never use it on a database you need to keep.**

### 1.4 Recommended manual-source directory

Remote acquisition is the normal path. If a source URL is unavailable from the machine running the registry, manually download the source on another machine and place it under:

```text
inputs/
  pronom/
  loc/
  nara/
  dpc/
  wikidata/
```

The `inputs/` layout is a recommended operator convention; it is not required by the code.

When a local fallback is needed, copy the relevant production config to a local operator config instead of editing the tracked production config, for example:

```powershell
Copy-Item config/sources.qnl.pronom-only.json config/sources.local.pronom.json
```

Then change only the source-location fields described below.

Relative local paths in the examples assume commands are run from `qnl_format_registry_builder`.

---

## 2. PRONOM

### Purpose

PRONOM is the authoritative PUID identity source. PRONOM/DROID are the only sources that should verify PUID identity.

### Normal acquisition source

The `pronom_registry` adapter defaults to the National Archives PRONOM GitHub dataset and, for a full run, downloads the repository archive:

```text
https://github.com/nationalarchives/pronom/archive/refs/heads/develop.zip
```

The adapter extracts JSON records under:

```text
signatures/fmt/
signatures/x-fmt/
```

### Run

```powershell
python -m registry_builder run `
  --config config/sources.qnl.pronom-only.json `
  --workdir work `
  --out out/pronom
```

### Verify

```powershell
python -m registry_builder.storage_status `
  --config config/sources.qnl.pronom-only.json `
  --expect-source pronom_registry
```

Stop if no completed `pronom_registry` contribution is reported.

### Manual/local fallback

If the archive URL cannot be reached:

1. Download the PRONOM repository ZIP from the National Archives PRONOM GitHub repository on another machine.
2. Place it at, for example:

```text
inputs/pronom/pronom-develop.zip
```

3. Copy the config:

```powershell
Copy-Item config/sources.qnl.pronom-only.json config/sources.local.pronom.json
```

4. In the `pronom_registry` source object add:

```json
{
  "retrieval_mode": "github_archive",
  "archive_url": "inputs/pronom/pronom-develop.zip"
}
```

A plain local path is accepted by the common URI reader. A `file://` URI is also supported, including Windows paths encoded as a proper file URI.

5. Run the same generic command with the local config:

```powershell
python -m registry_builder run `
  --config config/sources.local.pronom.json `
  --workdir work `
  --out out/pronom
```

Do not unpack/rewrite the PRONOM JSON unless you specifically need the adapter's individual-JSON mode. The archive is the simplest reproducible full-source input.

---

## 3. LOC FDD XML

### Purpose

LOC FDD contributes authoritative FDD identifiers and reviewed source-native sustainability evidence. LOC is not converted into one scalar preservation-risk score.

### Normal acquisition source

Official LOC FDD XML ZIP:

```text
https://www.loc.gov/preservation/digital/formats/fddXML.zip
```

The production source config is:

```text
config/sources.qnl.loc-sustainability.json
```

and uses the reviewed `loc_fdd_xml_reviewed` projection.

### Stage 1 — acquire/persist LOC FDD XML

```powershell
python -m registry_builder run `
  --config config/sources.qnl.loc-sustainability.json `
  --workdir work `
  --out out/loc-sustainability
```

Verify the current LOC contribution exists:

```powershell
python -m registry_builder.storage_status `
  --config config/sources.qnl.loc-sustainability.json `
  --expect-source loc_fdd_xml
```

### Manual/local fallback for FDD XML

If the LOC ZIP cannot be downloaded directly:

1. Download `fddXML.zip` in a browser or on another machine.
2. Place it at:

```text
inputs/loc/fddXML.zip
```

3. Copy the config:

```powershell
Copy-Item config/sources.qnl.loc-sustainability.json config/sources.local.loc-sustainability.json
```

4. Set the source ZIP location to the local file:

```json
{
  "retrieval_mode": "fdd_xml_zip",
  "zip_uri": "inputs/loc/fddXML.zip"
}
```

5. Run the same generic pipeline with the copied config.

Alternative: if you already have individual FDD XML files rather than the ZIP, place the files in a directory such as:

```text
inputs/loc/fddXML/
```

and configure the source with:

```json
{
  "directory": "inputs/loc/fddXML"
}
```

When using `directory`, remove the ZIP-specific `retrieval_mode`/`zip_uri` values so the adapter resolves the individual `*.xml` files.

---

## 4. LOC FDD↔PRONOM↔Wikidata crosswalk and approved LOC-PRONOM bridge

LOC publishes a separate monthly crosswalk. It is evidence-only by default because LOC documents that FDD, PRONOM and Wikidata entries can differ in hierarchy/granularity.

### Reviewed crosswalk source

Current reviewed mapping date:

```text
20260713
```

CSV:

```text
https://www.loc.gov/preservation/digital/formats/mappings/fdd-puid-qid-20260713.csv
```

Mapping information page:

```text
https://www.loc.gov/preservation/digital/formats/fdd/fdd_puid_qid.shtml
```

### Persist the crosswalk as evidence only

This command is safe even without the approved bridge artifact:

```powershell
python -m registry_builder run `
  --config config/sources.qnl.loc-crosswalk-only.json `
  --workdir work `
  --out out/loc-crosswalk
```

### Manual/local fallback for the crosswalk CSV

1. Download:

```text
fdd-puid-qid-20260713.csv
```

2. Place it at:

```text
inputs/loc/fdd-puid-qid-20260713.csv
```

3. Copy `config/sources.qnl.loc-crosswalk-only.json` (or the bridge config) to a local config.
4. In the `loc_fdd_mapping_csv` source object add:

```json
{
  "local_file": "inputs/loc/fdd-puid-qid-20260713.csv"
}
```

The adapter will use `local_file` instead of `mapping_url`.

### Approved LOC-PRONOM bridge

The intended reviewed integration command is:

```powershell
python -m registry_builder run `
  --config config/sources.qnl.loc-crosswalk-bridge.json `
  --workdir work `
  --out out/loc-crosswalk-bridge
```

That config also references the approved policy artifact:

```text
config/external_identity_mappings/loc_fdd_pronom_20260713.policy-v2.json
```

**Known clean-room reproducibility gap:** that approved mapping artifact is not currently present in `main`. Therefore a fresh clone can persist the official crosswalk as evidence, but cannot reproduce the exact approved LOC-PRONOM bridge until the approved policy JSON is restored/committed or supplied separately at the path above.

Do **not** recreate the bridge by treating every crosswalk row as identity equivalence. Broad/family/version-mismatched/many-to-one relationships were intentionally excluded during review.

---

## 5. LOC sustainability criterion claims

After the reviewed LOC FDD source has been persisted, apply the already-approved seven-factor LOC criterion mapping.

Approved mapping:

```text
config/criterion_mappings/loc_fdd_xml.v2.approved.json
```

Production backfill config:

```text
config/loc_fdd_sustainability_backfill.production.json
```

### Dry-run first

```powershell
python -m registry_builder criterion-claims backfill `
  --config config/loc_fdd_sustainability_backfill.production.json `
  --dry-run
```

Review the report and stop if the mapping/source relationship is unexpectedly different.

### Apply

```powershell
python -m registry_builder criterion-claims backfill `
  --config config/loc_fdd_sustainability_backfill.production.json
```

The reviewed baseline generated **1,565** LOC criterion claims. A future current LOC release may legitimately change coverage; do not force a count merely to match historical coverage.

---

## 6. NARA Digital Preservation Framework

### Purpose

NARA contributes source-native format metadata and governed preservation-risk assessments. The project keeps NARA's native numeric direction (`higher_is_safer`) separate from the normalized semantic risk view.

### Reviewed/pinned release

Current production config pins release:

```text
20260320
```

Two CSV files are required:

```text
NARA_PreservationActionPlan_FileFormats_20260320.csv
NARA_File_Format_Risk_Matrix_20260320_Numbered.csv
```

Normal remote URLs:

```text
https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Plan_Spreadsheet/NARA_PreservationActionPlan_FileFormats_20260320.csv

https://raw.githubusercontent.com/usnationalarchives/digital-preservation/master/Digital_Preservation_Risk_Matrix/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv
```

### Stage 1 — acquire/persist NARA

```powershell
python -m registry_builder run `
  --config config/sources.qnl.nara-only.json `
  --workdir work `
  --out out/nara
```

Verify:

```powershell
python -m registry_builder.storage_status `
  --config config/sources.qnl.nara-only.json `
  --expect-source nara_digital_preservation_framework
```

### Manual/local fallback

The NARA adapter explicitly supports `release_mode: local_files`.

1. Download both CSVs above.
2. Place them at:

```text
inputs/nara/NARA_PreservationActionPlan_FileFormats_20260320.csv
inputs/nara/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv
```

3. Copy the production source config to `config/sources.local.nara.json`.
4. Replace the source release settings with:

```json
{
  "release_mode": "local_files",
  "local_files": [
    {
      "path": "inputs/nara/NARA_PreservationActionPlan_FileFormats_20260320.csv",
      "kind": "preservation_action_plan",
      "release_date": "20260320"
    },
    {
      "path": "inputs/nara/NARA_File_Format_Risk_Matrix_20260320_Numbered.csv",
      "kind": "risk_matrix_numbered",
      "release_date": "20260320"
    }
  ]
}
```

5. Run the normal generic `registry_builder run` command with `config/sources.local.nara.json`.

For a future `release_mode: latest` deployment, `fallback_local_files` is also supported, but the current reviewed production workflow intentionally uses the pinned release.

### Stage 2 — governed NARA risk claims

Dry-run:

```powershell
python -m registry_builder.nara_risk_assessment_backfill `
  --config config/nara_risk_assessment_backfill.production.json `
  --dry-run `
  --out out/nara-risk-dry-run.json
```

Apply only if the migration gate passes:

```powershell
python -m registry_builder.nara_risk_assessment_backfill `
  --config config/nara_risk_assessment_backfill.production.json `
  --out out/nara-risk-production.json
```

The currently reviewed production state contains **758 current NARA risk claims** targeting **743 canonical formats**. Four genuine same-canonical source conflicts are intentionally preserved rather than collapsed.

---

## 7. DPC Global Bit List

### Purpose

DPC entries are persisted as `evidence_only`. They cannot create or merge canonical format identities. Approved DPC-to-format risk mappings are applied in a separate governed claim stage.

### Reviewed/pinned source

Edition:

```text
2025
```

Pinned Git commit:

```text
3ad3fef626ea7c128ef8c323d92227e5cae2efc8
```

Archive URL used by the adapter:

```text
https://github.com/Digital-Preservation-Coalition/bit-list/archive/3ad3fef626ea7c128ef8c323d92227e5cae2efc8.zip
```

### Stage 1 — acquire/persist DPC evidence

```powershell
python -m registry_builder run `
  --config config/sources.qnl.dpc-only.json `
  --workdir work `
  --out out/dpc
```

Verify the pinned edition:

```powershell
python -m registry_builder.storage_status `
  --config config/sources.qnl.dpc-only.json `
  --expect-source dpc_bit_list_2025 `
  --expect-records 84 `
  --expect-evidence-only 84
```

### Manual/local fallback

1. Download the pinned commit ZIP above.
2. Place it at:

```text
inputs/dpc/bit-list-3ad3fef626ea7c128ef8c323d92227e5cae2efc8.zip
```

3. Copy the source config to `config/sources.local.dpc.json`.
4. In the DPC source object add:

```json
{
  "local_archive": "inputs/dpc/bit-list-3ad3fef626ea7c128ef8c323d92227e5cae2efc8.zip"
}
```

5. Run the same generic pipeline against the local config.

### Stage 2 — governed DPC risk claims

Approved mapping:

```text
config/external_risk_mappings/dpc_bit_list_2025.v1.approved.json
```

Dry-run:

```powershell
python -m registry_builder.dpc_risk_assessment_backfill `
  --config config/dpc_risk_assessment_backfill.production.json `
  --dry-run `
  --out out/dpc-risk-dry-run.json
```

Apply:

```powershell
python -m registry_builder.dpc_risk_assessment_backfill `
  --config config/dpc_risk_assessment_backfill.production.json `
  --out out/dpc-risk-production.json
```

The reviewed production mapping currently creates **51** DPC risk claims. DPC must remain evidence/risk only; its backfill must not change canonical identity.

---

## 8. Wikidata — initial clean-room integration

### Purpose and boundary

Wikidata is deliberately **evidence-only for canonical identity**. QIDs identify Wikidata source records. Copied PRONOM/LOC/NARA identifiers remain unverified Wikidata assertions. Only assertions that resolve to existing authoritative canonical identities become governed `source_relationship_claims`.

Wikidata contributes no preservation-risk claims and cannot create or merge canonical formats.

Run Wikidata **after PRONOM/LOC/NARA identity evidence is established**.

### Source endpoint

Unlike PRONOM/LOC/NARA/DPC, Wikidata does not have one static source file URL for this integration. The acquisition adapter queries the Wikidata Query Service (WDQS) and writes a frozen CSV snapshot.

Default endpoint:

```text
https://query.wikidata.org/sparql
```

Population policy:

```text
2026-08-20-v3
```

### Stage 1 — acquire the frozen policy-v3 CSV

For a fresh online acquisition:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats-policy-v3.csv `
  --workdir work
```

The file name above is important because the current initial production backfill config expects:

```text
../wikidata-file-formats-policy-v3.csv
```

relative to the `config/` directory, which resolves to:

```text
qnl_format_registry_builder/wikidata-file-formats-policy-v3.csv
```

### If WDQS is unavailable from the registry machine

Run the same `wikidata_download` command on another machine that can reach WDQS, then copy the resulting CSV to:

```text
qnl_format_registry_builder/wikidata-file-formats-policy-v3.csv
```

or place it at:

```text
inputs/wikidata/wikidata-file-formats-policy-v3.csv
```

and in a copied relationship-backfill config change:

```json
{
  "input_csv": "../inputs/wikidata/wikidata-file-formats-policy-v3.csv"
}
```

`input_csv` is resolved relative to the backfill config file.

### Approved baseline snapshot

The currently approved production snapshot has:

```text
SHA-256: a6c1e598b567dd89557a67f186e99bf8486cddf40615384bbe998e450a1810df
Rows:    15479
```

If you are reproducing the exact approved baseline, use that exact CSV snapshot.

**Known clean-room reproducibility gap:** the approved 15,479-row CSV snapshot is not currently distributed as a repository file. A future live WDQS acquisition may legitimately differ from the approved baseline. Do not simply edit the production expected counts to force a changed live result through the first-load gate. Either obtain the approved snapshot artifact or perform a documented review of the changed population before approving a new baseline.

### Stage 2 — initial relationship backfill

For a database that has never had Wikidata integrated, use the initial relationship backfill—not `wikidata_refresh`.

Dry-run first:

```powershell
python -m registry_builder.wikidata_relationship_backfill `
  --config config/wikidata_relationship_backfill.production.json `
  --dry-run `
  --out out/wikidata-initial-dry-run.json
```

Apply only when the migration gate passes:

```powershell
python -m registry_builder.wikidata_relationship_backfill `
  --config config/wikidata_relationship_backfill.production.json `
  --out out/wikidata-initial-production.json
```

### Stage 3 — independent verification

```powershell
python -m registry_builder.wikidata_relationship_verify `
  --config config/wikidata_relationship_backfill.production.json `
  --out out/wikidata-verify.json
```

For the approved baseline the verified state is:

```text
canonical formats                              3372
Wikidata evidence-only source records         15479
current Wikidata relationship claims           2856
Wikidata QIDs with relationships               2519
canonical formats with Wikidata relationships  2793
promoted Wikidata strong identifier claims        0
Wikidata risk assessments                         0
```

Stop if the verifier status is not `ok`.

---

## 9. Wikidata — later refreshes

After the first approved Wikidata relationship backfill exists, future source refreshes use the controlled refresh workflow.

### Preflight only

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --out out/wikidata-refresh-preflight.json
```

Do not apply unless:

```text
status = ready
gate_passed = true
baseline_verification.status = ok
gate_errors = []
```

The configured drift gates check population change, relationship-edge change, semantic claim turnover, unresolved copied authority identifiers, and identity/risk invariants.

### Apply an approved refresh

```powershell
python -m registry_builder.wikidata_refresh `
  --config config/wikidata_refresh.production.json `
  --workdir work `
  --apply `
  --out out/wikidata-refresh-production.json
```

If post-write verification fails, inspect the persisted state before rerunning. The workflow is a coordinated guarded refresh operation, not a multi-document MongoDB rollback transaction.

---

## 10. Final persistent-store verification

At minimum, inspect the current persistent state:

```powershell
python -m registry_builder.storage_status `
  --config config/sources.qnl.json
```

The report should show completed current contributions for the source IDs that have been loaded, including:

```text
pronom_registry
loc_fdd_xml
nara_digital_preservation_framework
dpc_bit_list_2025
wikidata_file_formats
```

Wikidata also has its dedicated independent verifier as described above.

The current approved integrated registry has **3,372 canonical formats**. Do not use that count as a universal invariant for future source releases; source changes can legitimately change the canonical registry. Identity changes must nevertheless remain explainable and pass the relevant validation/reconciliation checks.

---

## 11. What is stored where

Source-native acquisition files are retained under `work/snapshots/` as content-addressed artifacts. MongoDB is not the binary source-file store.

MongoDB stores structured integration state, including:

```text
runs
source_snapshots
source_records
canonical_formats
identifier claims / identifier state
criterion_claims
risk_assessment_claims
source_relationship_claims
assessment/change provenance
```

The source roles are intentionally different:

| Source | Canonical identity | Criterion evidence | Risk claims | Governed relationships |
|---|---:|---:|---:|---:|
| PRONOM | Yes, authoritative PUID | possible mapped evidence | No | source linkage |
| LOC FDD | authoritative LOC ID / conservative reconciliation | Yes | No scalar LOC risk | crosswalk/bridge context |
| NARA | authoritative NARA ID / conservative reconciliation | source-native evidence | Yes | source linkage |
| DPC | No (`evidence_only`) | contextual evidence | Yes, reviewed mapping | No identity projection |
| Wikidata | No (`evidence_only`) | technical/context evidence only | No | Yes, authority-resolved only |

Being present in MongoDB does **not** make all sources equal authorities.

---

## 12. Failure rules for operators

Stop rather than improvise when any of the following occurs:

- a required source cannot be acquired and no documented local fallback is available;
- a source schema changes so the adapter no longer recognizes required fields;
- a reviewed mapping/backfill migration gate fails;
- canonical identity count changes unexpectedly after an evidence-only source;
- DPC or Wikidata attempts to create identity;
- Wikidata copied PUID/LOC/NARA identifiers become promoted canonical identifiers;
- Wikidata produces risk assessments;
- NARA/DPC risk claim counts or scopes change in a way that cannot be explained by a source/mapping change;
- the Wikidata independent verifier does not return `status: ok`;
- a future source release differs materially from the frozen/reviewed baseline.

Do not solve an operational failure by weakening authority rules or editing expected production counts without review.

---

## 13. TODO — make source operation more generic

The adapter architecture is already generic: the normal ingest command is:

```powershell
python -m registry_builder run --config <source-config> --workdir work --out <out-dir>
```

The remaining inconsistency is **post-ingest governed processing**. LOC criterion claims, NARA/DPC risk claims, and Wikidata relationship refresh currently use dedicated follow-on commands.

Future work should preserve the existing semantics while moving orchestration behind configuration. A possible design is a processor registry parallel to the adapter registry:

```json
{
  "sources": [
    {
      "id": "example_source",
      "type": "example_adapter"
    }
  ],
  "post_ingest": [
    {
      "type": "criterion_claims",
      "mapping": "...",
      "replace_source_claims": true
    },
    {
      "type": "risk_claims",
      "mapping": "...",
      "replace_source_claims": true,
      "materialize": true
    },
    {
      "type": "source_relationships",
      "preflight": true,
      "drift_gates": "..."
    }
  ]
}
```

Desired end state:

```text
one generic command per dataset
+ source-specific config
+ adapter
+ optional registered processors
+ validation/verifier declarations
```

The operator would still run datasets **one by one**, not one giant bootstrap command.

Specific TODOs:

1. Define a generic `post_ingest` / processor contract rather than hard-coding source names in the main pipeline.
2. Register criterion, risk and relationship processors in the same style as source adapters.
3. Standardize `preflight`, `apply`, source-level replacement and post-write verification semantics.
4. Standardize local fallback fields (`local_file`, `local_archive`, `local_files`, etc.) while retaining adapter-specific needs.
5. Allow one central/shared storage config so every source config does not repeat the MongoDB URI/database.
6. Add reviewed-snapshot pinning to generic processor execution where operator approval must apply to an exact SHA-256.
7. Add clean-room integration tests that start from an empty store and execute each source procedure in documented order.
8. Restore/distribute the approved LOC-PRONOM bridge artifact required by `sources.qnl.loc-crosswalk-bridge.json`.
9. Publish or otherwise distribute the approved Wikidata policy-v3 baseline CSV (or a reproducible release artifact) so exact baseline reconstruction does not depend on one operator's local cache.

These are usability/reproducibility improvements. They must not change the established authority, risk, scope or evidence semantics.

---

## 14. Adding a new dataset/source

A new dataset should use the existing source-adapter architecture rather than adding one-off ingestion code to the pipeline.

Detailed implementation guidance is in:

- `docs/ADDING_AND_RUNNING_DATA_SOURCES.md`
- `docs/ADAPTER_IMPLEMENTATION_GUIDE.md`
- `docs/HOW_TO_ADD_A_SOURCE.md` at repository level where applicable

The minimum workflow is:

### Step 1 — define the evidence purpose before coding

State whether the source contributes:

```text
canonical identity
source-native descriptive/technical evidence
criterion evidence
external risk assessments
institutional evidence
relationships/cross-references
```

Do not assume every source can create identity.

### Step 2 — define authority boundaries

For every identifier namespace in the dataset, decide whether the source owns that namespace or merely copies it.

Examples from the current production model:

```text
PRONOM owns PUID
LOC FDD owns LOC FDD ID
NARA owns NARA format ID
Wikidata owns QID
```

A source copying somebody else's identifier should normally preserve it as unverified evidence unless a reviewed bridge policy says otherwise.

### Step 3 — implement a `SourceAdapter`

Create:

```text
registry_builder/adapters/<source>.py
```

Implement acquisition and extraction using the common `SourceSnapshot` / `RawFormatRecord` model.

The adapter should support:

- online acquisition where the authoritative source permits it;
- immutable/content-addressed snapshot provenance;
- a documented local/offline fallback where practical;
- source-native fields needed for later evidence processing;
- an explicit `record_role`, especially `evidence_only` for non-identity sources.

### Step 4 — register the adapter

Register its `type_name` in:

```text
registry_builder/adapters/__init__.py
```

Then configuration selects the adapter using:

```json
{
  "id": "my_source",
  "type": "my_source_adapter",
  "enabled": true,
  "required": true
}
```

### Step 5 — add source-specific config, not source-specific pipeline code

Create an example/production source config under `config/` containing retrieval settings, authority rules and any pinned release/version information.

The normal ingest path should remain:

```powershell
python -m registry_builder run `
  --config config/sources.<new-source>.json `
  --workdir work `
  --out out/<new-source>
```

### Step 6 — add reviewed mappings/processors only where semantically justified

If the source contributes criteria, risk or relationships, keep those mappings/versioned claims explicit. Do not encode heuristic source semantics directly into canonical records simply to increase coverage.

### Step 7 — test the source boundary

Tests should cover at least:

```text
adapter registration
online/local acquisition behavior
extraction/projection
identifier authority/verification behavior
identity vs evidence-only behavior
snapshot provenance
normalization/reconciliation impact
mapping/backfill replacement lifecycle if used
offline/local fallback
no unintended canonical creation/merge for evidence-only sources
```

### Step 8 — document source files and operator fallback

Every production source document should state:

```text
authoritative source URL(s)
release/version/pin strategy
exact files required
normal command
verification command
manual-download path
config key used for local fallback
expected stop/failure conditions
```

A new operator should be able to run the source without rediscovering its semantics.
