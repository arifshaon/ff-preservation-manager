# Wikidata file-format acquisition

The `wikidata_sparql` source adapter is currently **acquisition-only**. It downloads file-format metadata from the Wikidata Query Service and stores a review CSV plus immutable source snapshots.

It does **not** normalize Wikidata rows into `RawFormatRecord`, reconcile QIDs/PUIDs, create criterion claims, alter canonical formats, or write Wikidata-derived data to MongoDB.

## Source population

The default acquisition uses an explicit, versioned population policy. It no longer uses the unrestricted transitive query `P31/P279* -> Q235557`, because analysis of the completed 85,269-QID acquisition showed that this traversal pulled in large unrelated branches such as Wikimedia modules, templates and map-data modules.

### Policy v1 validation

Policy v1 reduced the acquisition from 85,269 QIDs to 15,233 while preserving almost all useful technical evidence. A repeatable comparison against the broad snapshot reproduced the previously identified 595 useful non-direct records exactly:

- 391 were retained by v1;
- 204 were missed by v1;
- the missing-class census was then reviewed to define policy v2.

The v2 allowlist is therefore evidence-based rather than derived from another ontology traversal.

### Policy v2 population union

The current population is the union of:

1. direct instances of **file format** (`P31 = Q235557`);
2. direct instances of **file format family** (`P31 = Q26085352`);
3. direct instances of the reviewed specialist-class allowlist;
4. evidence-bearing instances of **XML-based format** (`P31 = Q20155966` plus authority or technical format evidence);
5. any item carrying a PRONOM file-format ID (`P2748`);
6. any item carrying a Library of Congress FDD ID (`P3266`);
7. any item carrying a NARA File Format Preservation Plan ID (`P11167`).

The authority-linked routes are independent of Wikidata classification. This retains useful cross-registry assertions even where a QID is incompletely or unusually classified.

The current reviewed specialist-class allowlist is:

- image file format (`Q1572121`);
- archive file format (`Q1351368`);
- document file format (`Q336705`);
- disk image format (`Q138827382`);
- raw image format (`Q654383`);
- raster-graphics file format (`Q105599390`);
- font file format (`Q55281818`);
- music file format (`Q1955133`);
- digital container format (`Q167772`);
- patch format (`Q115729440`);
- audio file format (`Q682626`);
- video file format (`Q18359031`);
- vector graphics file format (`Q105599400`);
- package format (`Q2026749`);
- executable file format (`Q17560478`);
- chemical file format (`Q5090461`);
- GIS project file (`Q133897645`).

These classes were selected after reviewing the 204 useful non-direct QIDs missed by policy v1. The sample contained concrete file-format records such as disk images, RAW camera formats, raster/vector graphics, fonts, audio/video formats, containers, patches, executable formats, chemical formats and GIS project formats.

Some retained QIDs have additional `P31` classifications such as standards, markup languages, package managers or compression concepts. Those additional classifications remain source-native context; they do not change the acquisition decision made by an approved file-format class.

### Conditional XML route

`XML-based format` (`Q20155966`) is deliberately **not** an unconditional allowlist class. It is broad enough that classification alone is insufficient.

An XML-based QID is acquired only when it has at least one of:

- PRONOM ID (`P2748`);
- LOC FDD ID (`P3266`);
- NARA format-plan ID (`P11167`);
- file extension (`P1195`);
- MIME type (`P1163`);
- file-format identification pattern (`P4152`).

The authority predicates are included in the XML route for policy clarity even though the independent authority routes would also acquire those QIDs.

### Classes deliberately not promoted

The v1 missing-class census also contained broader or non-format concepts such as markup language, video compression format, technical standard, ISO standard, specification edition, programming language, protocol, package manager and technology. These are not promoted to unconditional population classes.

They may still appear as source context on acquired QIDs or be revisited later if a separate contextual-entity model is introduced.

`P279` relationships are still harvested as source context. They simply do not determine acquisition membership transitively.

The current population-policy version is `2026-08-20-v2`. The policy version, reviewed class QIDs and conditional XML class QID are written into acquisition metadata and the session manifest and are included in the query-set hash. A policy change therefore cannot silently reuse a snapshot created under an older population rule.

Population discovery is separate from property harvesting. The discovered QIDs are deduplicated and frozen for one acquisition session.

Population queries are keyset-paginated by Wikidata entity URI. The default page size is 500.

## Default fields

The review CSV is one row per Wikidata QID and includes:

- QID, English label, description and aliases;
- instance-of and subclass-of relationships;
- PRONOM file format ID (`P2748`);
- Library of Congress FDD ID (`P3266`);
- NARA File Format Preservation Plan ID (`P11167`);
- file extension (`P1195`);
- MIME type (`P1163`);
- version (`P348`);
- identification pattern / magic number (`P4152`);
- developer (`P178`);
- publication date (`P577`);
- inception date (`P571`);
- part-of (`P361`);
- based-on (`P144`);
- replaces / replaced-by (`P1365` / `P1366`);
- described-by-source (`P1343`);
- official website (`P856`).

Multi-valued properties are pipe-delimited. Paired relationship QIDs and labels remain aligned.

## Staged VALUES batching

The adapter does **not** repeat population-selection logic for every property query.

Instead it:

1. discovers and freezes the QID population;
2. splits the QIDs into bounded batches (default 200);
3. uses `VALUES ?format { ... }` for each property query;
4. stores each completed batch as a source snapshot;
5. merges all batches locally into the final CSV.

This keeps individual WDQS responses small and bounded.

## Resume after interruption

An incomplete acquisition session is recorded at:

```text
work/snapshots/wikidata_file_formats/.wikidata_acquisition_session.json
```

Each completed property batch is cached separately. If the command is interrupted, rerunning the same command resumes the frozen population and reuses completed batches. It does not restart population discovery or already completed batches.

The query-set hash includes the population queries, policy version, reviewed specialist-class QIDs, conditional XML policy, batch query templates and output columns. If any of these change, an incomplete session created under the previous policy is not resumed.

After a successful final CSV snapshot is written, the session is marked complete. A later normal run starts a fresh acquisition and therefore can observe Wikidata changes.

Use `--restart` to abandon an incomplete session and start a fresh population immediately.

## Download

From `qnl_format_registry_builder`:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --workdir work
```

Useful controls:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --workdir work `
  --batch-size 200 `
  --population-page-size 500 `
  --transport-retries 5
```

To deliberately abandon an incomplete run:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --workdir work `
  --restart
```

The default endpoint is:

```text
https://query.wikidata.org/sparql
```

HTTP 429 and transient 5xx responses are retried with bounded backoff. The CLI also retries interrupted or partial HTTP transfers.

## Compare acquisition policies

The population-comparison command compares two acquisition CSVs by QID and identifies useful non-direct records lost by a policy change:

```powershell
python -m registry_builder.wikidata_population_compare `
  --old old-wikidata.csv `
  --new new-wikidata.csv `
  --out-dir wikidata-population-comparison `
  --prefix policy-comparison
```

A **useful non-direct** record is defined for this diagnostic as a QID that is not a direct `P31 = Q235557` instance but has at least one PRONOM/LOC/NARA identifier, file extension, MIME type or identification pattern.

The command writes:

- a JSON summary;
- added QIDs;
- removed QIDs;
- old useful non-direct QIDs retained by the new policy;
- old useful non-direct QIDs missing from the new policy;
- a direct `P31` class census for those missing records.

## Custom query

A reviewed custom SPARQL query can still be supplied:

```powershell
python -m registry_builder.wikidata_download `
  --query-file .\config\wikidata-file-formats.sparql `
  --out wikidata-file-formats.csv
```

Custom-query mode is executed as one request and must return at least `format` and `qid`.

## Offline replay

After a complete acquisition:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --workdir work `
  --offline
```

Offline mode uses the cached final snapshot and does not contact Wikidata.

## Deliberate current boundary

`WikidataSparqlAdapter.extract()` returns an empty list. Wikidata is being acquired for source study only. It does not yet participate in identity reconciliation, criterion mapping, risk scoring, or registry persistence.

The next stage is to run policy v2, compare it with both the broad 85,269-QID snapshot and the policy-v1 15,233-QID snapshot, and review any remaining useful non-direct records before enabling Wikidata-to-registry projection.
