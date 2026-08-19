# Wikidata file-format acquisition

The `wikidata_sparql` source adapter is currently **acquisition-only**.
It downloads file-format crosswalk metadata from the Wikidata Query Service and stores the result as an immutable source snapshot plus a normal CSV file for review.

It does **not** currently normalize Wikidata rows into `RawFormatRecord`, reconcile QIDs/PUIDs, create criterion claims, alter canonical formats, or write Wikidata-derived data to MongoDB.

## Default data retrieved

The default acquisition is anchored on PRONOM ID (`P2749`) and retrieves:

- Wikidata entity URI and QID
- PRONOM PUID (`P2749`)
- English label
- Library of Congress FDD ID (`P3267`)
- file extension (`P1195`)
- MIME type (`P1163`)
- developer/creator (`P178`), including QID and English label
- publication date (`P577`)
- inception date (`P571`), retained separately because Wikidata uses both date concepts

Multi-valued properties are pipe-delimited in the CSV, producing one row per QID/PUID.

## Why the default acquisition is partitioned

The public Wikidata Query Service has a hard query execution limit and variable public-cluster load. A single SPARQL query that joins all of the multi-valued properties above can create a large intermediate result before aggregation.

For that reason the adapter deliberately runs several small queries:

1. core QID/PUID/English label
2. LOC FDD IDs
3. extensions
4. MIME types
5. developers
6. publication dates
7. inception dates

The adapter then merges those results locally into the single review CSV. This is an acquisition implementation detail only: no Wikidata rows are ingested into the registry.

HTTP 429 and transient 5xx responses (500/502/503/504) are retried with bounded backoff. If a query still fails, the error identifies the individual query part that failed.

## Download

From `qnl_format_registry_builder`:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --workdir work
```

The command prints a JSON acquisition summary containing the CSV path, content-addressed snapshot path, SHA-256, query-set SHA-256 and row count.

The default endpoint is:

```text
https://query.wikidata.org/sparql
```

The default User-Agent identifies this repository. It can be overridden:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --user-agent "QNL-Format-Registry-Research/1.0 (contact@example.org)"
```

## Custom query

A reviewed SPARQL query can still be supplied without changing adapter code:

```powershell
python -m registry_builder.wikidata_download `
  --query-file .\config\wikidata-file-formats.sparql `
  --out wikidata-file-formats.csv
```

A custom query is executed as one request and must return at least `format`, `qid`, and `puid` columns. The exact query is recorded in snapshot metadata and its SHA-256 is used in the cache key.

## Offline replay

After a query set has been downloaded once, the same acquisition can be replayed from the content-addressed snapshot cache:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --workdir work `
  --offline
```

Offline mode does not contact Wikidata.

## Deliberate current boundary

`WikidataSparqlAdapter.extract()` returns an empty list. This is intentional. Before Wikidata participates in the registry, its source semantics and identifier authority need to be reviewed alongside PRONOM, NARA, LOC FDD, DPC Bit List and the other evidence sources. Acquisition is separated from interpretation so downloading a new Wikidata snapshot cannot silently alter registry identity or preservation-risk results.
