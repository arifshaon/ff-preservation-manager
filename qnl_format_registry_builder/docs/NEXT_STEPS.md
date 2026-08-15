# Next steps

This roadmap lists remaining work. Completed work should not stay here as future work.

## Current completed baseline

The following are implemented and tested or now enabled in the default sample configuration:

- source-adapter architecture;
- NARA Digital Preservation Framework adapter enabled as the required baseline hazard source;
- PRONOM registry adapter enabled as optional verified-PUID enrichment;
- LOC FDD XML adapter enabled as optional FDD XML ZIP sustainability/evidence enrichment;
- institutional policy XLSX adapter;
- PRONOM/DROID XML adapter;
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

## 1. Multi-source run QA: NARA + PRONOM + LOC

The default sample config now enables NARA, PRONOM, and LOC. The next operational step is to validate the combined registry output and document expected counts/runtime.

Tasks:

- run the default config end-to-end;
- verify that PRONOM PUIDs enrich existing NARA records rather than creating duplicates;
- verify that LOC FDD IDs enrich existing NARA/PRONOM records where identifiers overlap;
- verify that PUIDs from PRONOM are marked as verified authority identifiers;
- verify that LOC FDD IDs from LOC XML are marked as verified LOC identifiers;
- document expected runtime, record counts, and upstream rate-limit behavior;
- add guidance for `GITHUB_TOKEN` when needed;
- check common families such as PDF, TIFF, JPEG, WAV, MP4, XML, and ZIP for obvious duplicate canonical records.

Success check:

```text
NARA contributes external hazard evidence.
PRONOM contributes verified PUID identity evidence.
LOC contributes FDD identifiers and sustainability evidence.
Canonical records are enriched, not duplicated, where strong identifiers overlap.
```

## 2. Preservation risk analysis deterministic core

The next user-facing capability is preservation risk analysis built on the populated evidence registry.

The design spine is:

```text
Evidence -> Analysis -> Decision -> Action
```

First implementation slice:

- configurable risk framework loader;
- deterministic scoring engine;
- shared predicate evaluator;
- evidence pack builder with assessable/contextual split;
- evidence-field resolver;
- canonical evidence hash normalisation;
- per-question evidence hashes;
- NARA arithmetic regression test using imported NARA answers;
- eligibility report for leakage-safe LLM calibration;
- documentation committed with the implementation.

Do not add the LLM layer until the deterministic scoring and evidence hashing behaviour is tested.

## 3. Institutional decision and action workflow

After the deterministic risk-analysis core exists, add the workflow that lets an institution turn registry evidence into local decisions and preservation actions.

Possible workflows:

1. filter formats by name, identifier, hazard band, missing evidence, or review state;
2. export selected records to spreadsheet with `evidence_hash`;
3. let the institution record analysis and decisions in its own terminology;
4. import the completed review with conflict detection;
5. generate or update preservation actions from approved decisions.

A later interface can provide the same review flow without spreadsheet export/import.

## 4. AI-assisted analysis behind the deterministic schema

AI-assisted analysis may be useful for answering framework questions, summarizing evidence, and drafting recommendations.

Guardrails:

- the LLM answers only closed framework questions;
- the framework computes points, ratings, bands, completeness, review triggers, and divergences;
- calibration excludes NARA per-question answers and final ratings from the evidence pack;
- every conversational analysis resolves to a stored `analysis_run` with explicit parameters.

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
source_analysis_result_id
decision_id
action_type
recommended_action
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

## 6. Wikidata or other enrichment-source enablement

Wikidata is already part of the identifier-rule model as a weak identifier source, but a full enrichment workflow is not yet operationally documented.

Tasks:

- decide whether Wikidata should be a first-class adapter, a linked-data enrichment step, or a later optional connector;
- define which fields are useful and safe to import;
- ensure Wikidata identifiers do not become strong reconciliation keys unless explicitly configured;
- document how conflicting names, aliases, and external IDs should be treated.

## 7. Trend evidence connectors

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

## 8. Exporter implementation cleanup

The architecture treats exports as optional, and database-only runs are supported. The remaining implementation cleanup is to move the current JSON, JSONL, CSV, SQLite, and Markdown export-writing logic out of `pipeline.py` into exporter modules.

This is hygiene, not a blocker for registry population.

## 9. MongoDB integration testing

The test suite currently avoids requiring a live MongoDB service for ordinary local testing. Add optional MongoDB integration tests when CI or local test infrastructure can reliably provide MongoDB.

Suggested pattern:

```text
MONGODB_URI=mongodb://localhost:27017 pytest -m mongodb
```

These tests should prove the same source-by-source augmentation behavior through real MongoDB that file storage already proves.

## 10. Additional retrieval modes only when needed

Possible future modes:

- NARA linked-data/API retrieval if/when available and stable;
- PRONOM individual XML retrieval by appending `.xml` to format page URLs;
- PRONOM DROID signature auto-discovery;
- LOC FDD API or website retrieval beyond the XML ZIP;
- DPC Bit List adapter.

Add these inside source-level adapters where possible rather than creating new source concepts for each file representation.
