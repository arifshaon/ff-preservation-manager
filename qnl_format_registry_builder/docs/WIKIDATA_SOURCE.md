# Wikidata file-format acquisition

The `wikidata_sparql` source adapter is currently **acquisition-only**.
It downloads file-format crosswalk metadata from the Wikidata Query Service and stores the result as an immutable source snapshot plus a normal CSV file for review.

It does **not** currently normalize Wikidata rows into `RawFormatRecord`, reconcile QIDs/PUIDs, create criterion claims, alter canonical formats, or write Wikidata-derived data to MongoDB.

## Default data retrieved

The built-in SPARQL query is anchored on PRONOM ID (`P2749`) and retrieves:

- Wikidata entity URI and QID
- PRONOM PUID (`P2749`)
- English label
- Library of Congress FDD ID (`P3267`)
- file extension (`P1195`)
- MIME type (`P1163`)
- developer/creator (`P178`), including QID and English label
- publication date (`P577`)
- inception date (`P571`), retained separately because Wikidata uses both date concepts

Multi-valued properties are pipe-delimited in the CSV so the default export is one row per QID/PUID rather than a Cartesian product of extensions, MIME types and developers.

## Download

From `qnl_format_registry_builder`:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --workdir work
```

The command prints a JSON acquisition summary containing the CSV path, content-addressed snapshot path, SHA-256, query SHA-256 and row count.

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

A reviewed SPARQL query can be supplied without changing adapter code:

```powershell
python -m registry_builder.wikidata_download `
  --query-file .\config\wikidata-file-formats.sparql `
  --out wikidata-file-formats.csv
```

The exact query is recorded in snapshot metadata and its SHA-256 is used in the cache key.

## Offline replay

After a query has been downloaded once, the same query can be replayed from the content-addressed snapshot cache:

```powershell
python -m registry_builder.wikidata_download `
  --out wikidata-file-formats.csv `
  --workdir work `
  --offline
```

Offline mode does not contact Wikidata.

## Deliberate current boundary

`WikidataSparqlAdapter.extract()` returns an empty list. This is intentional. Before Wikidata participates in the registry, its source semantics and identifier authority need to be reviewed alongside PRONOM, NARA, LOC FDD, DPC Bit List and the other evidence sources. Acquisition is separated from interpretation so downloading a new Wikidata snapshot cannot silently alter registry identity or preservation-risk results.
