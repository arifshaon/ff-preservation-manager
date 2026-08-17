# Registry Builder next steps

This roadmap lists **remaining builder work**. Completed preservation-risk functionality now lives in the sibling `preservation_risk_manager` and should not remain here as future work.

For the current repository architecture, see:

- [`../../docs/REPOSITORY_ARCHITECTURE.md`](../../docs/REPOSITORY_ARCHITECTURE.md)
- [`../../preservation_risk_manager/README.md`](../../preservation_risk_manager/README.md)

## Current completed baseline

The registry builder now provides, with tests/CI:

- source-adapter architecture;
- NARA Digital Preservation Framework adapter;
- PRONOM registry/DROID evidence adapters;
- LOC FDD XML evidence adapter;
- institutional policy workbook adapter;
- QNL institutional format evidence adapter;
- generic identifier namespaces and configurable identifier rules;
- authority-aware verified strong-identifier reconciliation;
- source-by-source incremental augmentation using active/latest source evidence;
- memory, file/JSON, and MongoDB storage backends;
- common `RegistryStore` interface and trusted external backend plugins;
- content-addressed source snapshots and offline replay;
- canonical format/source record/identifier/institutional evidence persistence;
- declarative criterion vocabulary/mappings;
- criterion-claim validation, audit, backfill, and supersession workflows;
- change detection and assessment-change records;
- optional exports and coverage reports;
- preservation method profiles;
- pytest suite and GitHub Actions CI.

The sibling risk manager now provides the previously planned deterministic and AI-assisted analysis layer:

- configurable/versioned risk frameworks;
- deterministic answer derivation/scoring;
- human natural-language questions;
- canonical system JSON requests;
- targeted domain/question assessment;
- evidence-gap diagnosis;
- evidence-remediation planning;
- provider-neutral AI interface;
- `fill-gaps` and independent `review-all` modes;
- human-readable rendering;
- draft 8-domain / 22-question preservation-risk framework.

Those capabilities are documented under [`../../preservation_risk_manager/docs/`](../../preservation_risk_manager/docs/).

## 1. Multi-source operational QA and benchmark runs

Continue validating combined NARA + PRONOM + LOC + QNL evidence runs against persistent storage.

Tasks:

- periodically run the configured sources end-to-end;
- record expected runtime and source-specific operational behavior for the pinned/current releases;
- check common families such as PDF, TIFF, JPEG, WAV, MP4, XML, ZIP and major office/AV families for duplicate or weakly related canonical records;
- verify verified PUID/FDD/NARA identifiers continue to enrich rather than incorrectly split/merge records;
- inspect source failure/fallback behavior;
- validate criterion-claim coverage after upstream source changes;
- document any source rate-limit/authentication prerequisites such as GitHub token use where required.

Success criterion:

```text
active source contributions can be refreshed independently,
provenance remains traceable,
strong identifier relationships remain conservative,
and current canonical/evidence views are reproducible.
```

## 2. Improve explicit format-family relationships

Current family discovery can use explicit family metadata when available and falls back conservatively to human-readable names/aliases.

Remaining work:

- define a stable family/entity model (`family_id`, `member_of`, parent/version relationship or equivalent);
- distinguish family, version, profile, subtype, container and encoding relationships;
- populate relationships from reliable source identifiers/evidence;
- avoid propagating family-level evidence to versions/profiles unless the mapping explicitly allows it;
- add QA reports for orphan/ambiguous family members.

This work is particularly important for batch risk questions such as "which PDF-family formats are at risk?".

## 3. Expand criterion evidence coverage for the 22-question framework

The new broad risk framework introduces evidence fields that are not yet populated for many formats.

Priority work is to improve the registry evidence layer rather than fill unknowns with assumptions.

Candidate criterion areas include:

- specification governance and stability;
- platform/software dependencies;
- external assets;
- open-source tooling;
- third-party software support;
- formal registry/identification support;
- byte transparency;
- compression and migration-loss risk;
- IP constraints / DRM / encryption;
- embedded metadata;
- accessibility capabilities;
- content-specific essential characteristics;
- local management capability;
- tested migration pathways;
- storage/network overhead.

Use the risk-manager actions:

```text
list_evidence_gaps
plan_evidence_remediation
```

to distinguish new source evidence from missing mappings or framework-alignment work.

## 4. Review and promote criterion mappings

Continue treating source-to-criterion mappings as reviewed, versioned configuration.

Tasks:

- use `criterion-evidence-audit` to identify source-native fields with useful coverage;
- add mapping rules only where semantics are defensible;
- validate with `mapping validate`;
- project draft mappings before approval;
- backfill stored evidence after mapping changes;
- use `--replace-source-claims` where old current claims must be superseded;
- retain source field/value and mapping provenance for audit.

Do not promote mappings merely to improve completeness percentages.

## 5. Evidence date/currency model

Current claim acquisition/observation timestamps do not always identify the period described by the underlying source statement.

Add clearer distinction between:

```text
retrieved_at / observed_at
source publication/update date
evidence valid-from / valid-to or described timeframe
```

This is required before robust trend/currentness analysis such as "which formats have become riskier over the last year?".

## 6. Trend evidence connectors

Trend should remain evidence-driven.

Potential inputs:

- NARA rating changes across releases;
- PRONOM status/signature changes;
- LOC sustainability updates;
- software/tool support changes;
- vendor/community deprecation notices;
- local holdings/exposure trends;
- local incidents and migration test outcomes.

Principle:

```text
Do not infer trend from a static risk level.
Trend requires time-stamped evidence of change.
```

## 7. Institutional evidence workflows

Expand controlled local evidence ingestion beyond seed examples.

Areas include:

- QNL identification/validation/rendering capability;
- supported preservation tools and versions;
- staff/specialist dependencies;
- tested migration pathways and validation results;
- storage/network cost or capacity observations;
- local incidents/failures;
- holdings exposure and growth.

Keep local evidence separate from institutional policy overlays and from global format facts.

## 8. Preservation action/history persistence

The risk manager currently produces evidence-gap/remediation and policy-proposal outputs, but persistent lifecycle/action management is still a future layer.

Potential persisted entities:

```text
analysis_runs
preservation_actions
decision_records
migration_tests
review_approvals
```

Any implementation should preserve:

- source/evidence hashes;
- framework/version;
- assessment parameters/scope;
- human approval state;
- action status/history;
- links back to triggering evidence/change events.

Do not allow AI-generated recommendations to become approved policy/actions automatically.

## 9. API/service layer above the common interfaces

A future HTTP/service layer can expose:

- canonical machine requests from `preservation_risk_manager.request_api`;
- controlled registry reads through `RegistryReader`;
- controlled registry update workflows through builder adapters/services.

It should **not** expose raw MongoDB mutation as the application API.

Shared interface: [`../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md`](../../docs/DATA_MODEL_AND_STORAGE_INTERFACE.md).

## 10. MongoDB integration testing

The ordinary unit suite does not require a live MongoDB instance.

Add optional real-service integration tests when CI/local infrastructure can provide MongoDB reliably.

Suggested pattern:

```text
MONGODB_URI=mongodb://localhost:27017 pytest -m mongodb
```

Tests should prove the same source replacement/augmentation and risk-manager read behavior against MongoDB that in-memory/file tests prove against their backends.

## 11. Exporter implementation cleanup

Exports remain optional. Database-only operation is supported.

Remaining hygiene:

- continue moving JSON/JSONL/CSV/SQLite/Markdown writing logic out of pipeline orchestration where appropriate;
- keep export formats downstream of the common logical registry model;
- avoid making any export file the authoritative write path.

## 12. Additional sources only when evidence value is clear

Potential sources/connectors include:

- additional NARA retrieval modes if stable/needed;
- PRONOM individual XML/signature updates;
- LOC web/API enrichment beyond current FDD XML;
- DPC Bit List or preservation action registries;
- software-support/tool registries;
- standards/governance metadata;
- carefully scoped linked-data/Wikidata enrichment.

New sources should answer a defined evidence need and use source-level adapters rather than creating a new source concept for every transport format.

## 13. Documentation upkeep

Whenever a capability moves from planned to implemented:

1. update this roadmap;
2. update the relevant installation/run guide;
3. update data/interface docs if contracts changed;
4. update human/system query docs if actions changed;
5. keep historical implementation plans under `docs/history/` rather than presenting them as current guidance.
