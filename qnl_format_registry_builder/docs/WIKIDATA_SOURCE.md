# Wikidata file-format acquisition

The `wikidata_sparql` source adapter is currently **acquisition-only**. It downloads file-format metadata from the Wikidata Query Service and stores a review CSV plus immutable source snapshots.

It does **not** normalize Wikidata rows into `RawFormatRecord`, reconcile QIDs/PUIDs, create criterion claims, alter canonical formats, or write Wikidata-derived data to MongoDB.

## Source population

The default acquisition uses an explicit, versioned population policy. It no longer uses the unrestricted transitive query `P31/P279* -> Q235557`, because analysis of the completed 85,269-QID acquisition showed that this traversal pulled in large unrelated branches such as Wikimedia modules, templates and map-data modules.

The population is now the union of:

1. direct instances of **file format** (`P31 = Q235557`);
2. direct instances of **file format family** (`P31 = Q26085352`);
3. direct instances of a small, reviewed specialist-class allowlist;
4. any item carrying a PRONOM file-format ID (`P2748`);
5. any item carrying a Library of Congress FDD ID (`P3266`);
6. any item carrying a NARA File Format Preservation Plan ID (`P11167`).

The authority-linked routes are independent of Wikidata classification. This retains useful cross-registry assertions even where a QID is incompletely or unusually classified.

The initial reviewed specialist-class allowlist is intentionally conservative:

- image file format (`Q1572121`);
- archive file format (`Q1351368`);
- document file format (`Q336705`).

The list should be expanded only from reviewed evidence, such as the class census of useful non-direct format records. It is not replaced with another transitive subclass traversal.

`P279` relationships are still harvested as source context. They simply no longer determine acquisition membership transitively.

The current population-policy version is `2026-08-20-v1`. The policy version and reviewed class QIDs are written into acquisition metadata and the session manifest, and they are included in the query-set hash. A policy change therefore cannot silently reuse a snapshot created under an older population rule.

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

The query-set hash includes the population queries, policy version, reviewed specialist-class QIDs, batch query templates and output columns. If any of these change, an incomplete session created under the previous policy is not resumed.

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

The next stage is to run the corrected acquisition, compare its population and class distribution with the previous 85,269-QID snapshot, and then review the retained non-direct classes before enabling any Wikidata-to-registry projection.
