# Wikidata file-format acquisition

The `wikidata_sparql` source adapter is currently **acquisition-only**. It downloads file-format metadata from the Wikidata Query Service and stores a review CSV plus immutable source snapshots.

It does **not** normalize Wikidata rows into `RawFormatRecord`, reconcile QIDs/PUIDs, create criterion claims, alter canonical formats, or write Wikidata-derived data to MongoDB.

## Source population

The default acquisition combines two Wikidata populations:

1. items classified as file formats through `P31/P279* -> Q235557`;
2. items carrying a PRONOM **file format** ID (`P2748`), retained because Wikidata classification can be incomplete.

Population discovery is separate from property harvesting. The discovered QIDs are frozen for one acquisition session.

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

The adapter does **not** repeat the broad file-format population traversal for every property query.

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
