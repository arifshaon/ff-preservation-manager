# Wikidata file-format acquisition

The `wikidata_sparql` source adapter is currently **acquisition-only**.
It downloads file-format metadata from the Wikidata Query Service and stores the result as an immutable source snapshot plus a normal CSV file for review.

It does **not** currently normalize Wikidata rows into `RawFormatRecord`, reconcile QIDs/PUIDs, create criterion claims, alter canonical formats, or write Wikidata-derived data to MongoDB.

## Correct Wikidata properties

The file-format identifiers used by this adapter are:

- PRONOM file format ID: `P2748`
- Library of Congress Format Description Document ID: `P3266`
- NARA File Format Preservation Plan ID: `P11167`

Do not use `P2749` for file formats: that is the PRONOM **software** identifier property. Do not use `P3267` for LOC FDD: that property is unrelated to LOC FDD.

## Default population

The default acquisition starts from Wikidata items modelled as file formats:

```sparql
?format wdt:P31/wdt:P279* wd:Q235557 .
```

It also includes items carrying a PRONOM file-format identifier (`P2748`) so that PRONOM-linked format/family items are not lost merely because Wikidata classification is incomplete.

PRONOM, LOC and NARA identifiers are therefore **optional metadata**, not a requirement for an item to appear in the CSV.

## Default data retrieved

The merged CSV contains one row per Wikidata item. Multi-valued properties are pipe-delimited.

Identity and description:

- Wikidata entity URI
- QID
- English label
- English description
- English aliases

Classification:

- instance of (`P31`)
- subclass of (`P279`)

Cross-registry identifiers:

- PRONOM file format ID (`P2748`)
- LOC FDD ID (`P3266`)
- NARA File Format Preservation Plan ID (`P11167`)

Technical metadata:

- file extension (`P1195`)
- MIME/media type (`P1163`)
- version (`P348`)
- file format identification pattern / magic number (`P4152`)

Origin and chronology:

- developer (`P178`)
- publication date (`P577`)
- inception date (`P571`)

Relationships and documentation context:

- part of (`P361`)
- based on (`P144`)
- replaces (`P1365`)
- replaced by (`P1366`)
- described by source (`P1343`)
- official website (`P856`)

These fields are collected for source study only. Their semantics have not yet been mapped to canonical identity or preservation-risk criteria.

## Why the default acquisition is partitioned

The public Wikidata Query Service has a hard query execution limit and variable public-cluster load. One large query joining all multi-valued properties can create a very large intermediate result.

The adapter therefore runs several statement-oriented queries and merges them locally:

1. core population, QID, English label and description
2. English aliases
3. classification (`P31`, `P279`)
4. cross-registry identifiers (`P2748`, `P3266`, `P11167`)
5. technical literals and dates
6. item relationships and developer/source links

HTTP 429 and transient 5xx responses (500/502/503/504) are retried with bounded backoff. If a query still fails, the error identifies the individual query part.

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

## Custom query

A reviewed SPARQL query can still be supplied without changing adapter code:

```powershell
python -m registry_builder.wikidata_download `
  --query-file .\config\wikidata-file-formats.sparql `
  --out wikidata-file-formats.csv
```

A custom query is executed as one request and must return at least `format` and `qid` columns. The exact query is recorded in snapshot metadata and its SHA-256 is used in the cache key.

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
