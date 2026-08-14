# Next steps

This roadmap lists remaining work. Completed work should not stay here as future work.

## Current completed baseline

The following are implemented and tested:

- source-adapter architecture;
- NARA Digital Preservation Framework adapter;
- PRONOM registry adapter support;
- institutional policy XLSX adapter;
- LOC FDD XML and PRONOM/DROID XML adapters;
- generic identifier namespaces and configurable identifier rules;
- verified-only strong identifier reconciliation;
- source-by-source incremental augmentation using latest successful source evidence;
- memory, file, and MongoDB storage backends;
- Mongo-safe serialization;
- baseline/change detection;
- hazard-band, native-rating, identifier, divergence, record-added, and record-removed change events;
- optional exports and coverage reports;
- preservation method profiles;
- pytest test suite and GitHub Actions CI.

## 1. PRONOM full-run enablement and QA

The PRONOM adapter exists, but the next operational step is to make full PRONOM runs routine and validated.

Tasks:

- run targeted PUID tests first, for example `fmt/18` and `fmt/95`;
- run full recursive GitHub JSON mode;
- verify that PRONOM PUIDs enrich existing NARA records rather than creating duplicates;
- verify that PUIDs from PRONOM are marked as verified authority identifiers;
- document expected runtime, record counts, and rate-limit behavior;
- add guidance for `GITHUB_TOKEN` when needed.

Success check:

```text
NARA run creates real external hazard evidence.
PRONOM run against the same store adds verified PUID evidence to matching canonical records.
No obvious duplicate PDF/TIFF/JPEG/WAV/MP4 families are created.
```

## 2. Wikidata or other enrichment-source enablement

Wikidata is already part of the identifier-rule model as a weak identifier source, but a full enrichment workflow is not yet operationally documented.

Tasks:

- decide whether Wikidata should be a first-class adapter, a linked-data enrichment step, or a later optional connector;
- define which fields are useful and safe to import;
- ensure Wikidata identifiers do not become strong reconciliation keys unless explicitly configured;
- document how conflicting names, aliases, and external IDs should be treated.

## 3. Trend evidence connectors

Trend should remain `Insufficient Evidence` until connectors exist for specification vitality, implementation vitality, authority warnings, holdings exposure, or other reliable trend signals.

Potential trend inputs:

- NARA native-rating movement between releases;
- PRONOM signature/status changes;
- LOC sustainability updates;
- tool support changes;
- local holdings growth or decline;
- local incident history;
- community or vendor deprecation notices.

Principle:

```text
Do not infer trend just because a format is high risk.
Trend needs its own evidence.
```

## 4. Institutional decision and action workflow

The next user-facing capability is not another source adapter. It is the workflow that lets an institution turn registry evidence into local decisions and preservation actions.

Possible workflows:

1. filter formats by name, identifier, hazard band, missing evidence, or review state;
2. export selected records to spreadsheet;
3. let the institution record risk analysis and decisions in its own terminology;
4. import the completed review as an updated institutional overlay;
5. generate or update preservation actions from the decisions.

A later interface could provide the same review flow without spreadsheet export/import.

AI-assisted analysis may be useful for summarizing evidence and drafting recommendations, but the final institutional decision should remain explicit and auditable.

## 5. Preservation action manager

`assessment_changes` is already a review queue. The next operational layer is persistent action tracking.

Candidate collection/module:

```text
preservation_actions
```

Candidate fields:

```text
action_id
canonical_id / format_id
source_change_id
action_type
recommended_action
decision
status
priority
assigned_to
due_date
created_at
closed_at
notes
```

Candidate statuses:

```text
open
under_review
accepted
deferred
implemented
closed
```

## 6. Exporter implementation cleanup

The architecture treats exports as optional, and database-only runs are supported. The remaining implementation cleanup is to move the current JSON, JSONL, CSV, SQLite, and Markdown export-writing logic out of `pipeline.py` into exporter modules.

This is hygiene, not a blocker for registry population.

## 7. MongoDB integration testing

The test suite currently avoids requiring a live MongoDB service for ordinary local testing. Add optional MongoDB integration tests when CI or local test infrastructure can reliably provide MongoDB.

Suggested pattern:

```text
MONGODB_URI=mongodb://localhost:27017 pytest -m mongodb
```

These tests should prove the same source-by-source augmentation behavior through real MongoDB that file storage already proves.

## 8. Additional retrieval modes only when needed

Possible future modes:

- NARA linked-data/API retrieval if/when available and stable;
- PRONOM individual XML retrieval by appending `.xml` to format page URLs;
- PRONOM DROID signature auto-discovery;
- LOC FDD API or website retrieval;
- DPC Bit List adapter.

Add these inside source-level adapters where possible rather than creating new source concepts for each file representation.
