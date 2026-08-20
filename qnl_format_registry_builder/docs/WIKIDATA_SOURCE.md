# Wikidata file-format acquisition

The `wikidata_sparql` source adapter is currently **acquisition-only**. It downloads file-format metadata from the Wikidata Query Service and stores a review CSV plus immutable source snapshots.

It does **not** normalize Wikidata rows into `RawFormatRecord`, reconcile QIDs/PUIDs, create criterion claims, alter canonical formats, or write Wikidata-derived data to MongoDB.

## Why population policy is explicit

The default acquisition no longer uses unrestricted transitive `P31/P279* -> Q235557` discovery. The completed broad acquisition contained 85,269 QIDs and pulled in large unrelated ontology branches such as Wikimedia modules, templates and map-data modules.

The replacement policy is explicit, versioned, evidence-based and deliberately conservative. `P279` is still harvested as source context, but never determines population membership transitively.

## Validation history

### Policy v1

Policy v1 reduced the population from 85,269 QIDs to 15,233. The repeatable comparison command reproduced the previously identified 595 useful non-direct records exactly:

- 391 / 595 retained;
- 204 / 595 missing.

The missing-class census was reviewed to define policy v2.

### Policy v2

Policy v2 expanded the reviewed specialist-class allowlist and added an evidence-gated XML route.

The resulting acquisition contained 15,421 QIDs:

- 539 / 595 useful non-direct records retained;
- 56 / 595 still missing;
- 90.6% retention of the old useful non-direct diagnostic set;
- only 188 QIDs added compared with v1;
- no v1 QIDs removed.

The remaining 56 records were reviewed individually. Most were preservation-relevant versions or variants whose Wikidata `P31` points to a specific parent format/family/product rather than a reusable format class. Examples included Word Binary versions, SWF versions, PDF/VT variants, STATISTICA file types, Softdisk Family Tree file types, Parchive versions, Python bytecode and WebP Extended.

That review defines policy v3.

## Policy v3 population union

The current population is the union of:

1. direct instances of **file format** (`P31 = Q235557`);
2. direct instances of **file format family** (`P31 = Q26085352`);
3. direct instances of reviewed specialist file-format classes;
4. evidence-bearing instances of **XML-based format**;
5. evidence-bearing instances of a reviewed set of specific format-parent concepts;
6. evidence-bearing instances of reviewed contextual format classes such as video compression format;
7. evidence-bearing instances of **open file format**, excluding known protocol/standard co-classifications;
8. any item carrying a PRONOM file-format ID (`P2748`);
9. any item carrying a Library of Congress FDD ID (`P3266`);
10. any item carrying a NARA File Format Preservation Plan ID (`P11167`).

The authority-linked routes remain independent of Wikidata classification.

## Reviewed specialist file-format classes

These direct `P31` classes are treated as format classes for acquisition:

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
- GIS project file (`Q133897645`);
- e-book file format (`Q81986407`);
- exe-extension-associated executable file format (`Q17560541`).

A record can carry additional `P31` values. Those remain source-native context and do not erase the approved format-class evidence.

## Evidence-gated routes

The conditional routes require at least one of:

- PRONOM ID (`P2748`);
- LOC FDD ID (`P3266`);
- NARA format-plan ID (`P11167`);
- file extension (`P1195`);
- MIME type (`P1163`);
- file-format identification pattern (`P4152`).

### XML-based format

`XML-based format` (`Q20155966`) remains conditional rather than an unconditional allowlist class.

### Reviewed format parents

Some version/variant records are modeled as direct instances of a particular parent concept. These parents are acquisition selectors only; they are **not** promoted to reusable file-format classes:

- Renoise Song (`Q2597575`);
- Parchive (`Q497118`);
- Microsoft Word Binary File Format (`Q28858032`);
- Excel Binary File Format (`Q3502441`);
- Small Web Format family (`Q594447`);
- PDF/VT (`Q125650`);
- Softdisk Family Tree (`Q34739013`);
- STATISTICA (`Q34746188`);
- git packfile index (`Q53756508`);
- Python bytecode (`Q28009469`);
- WebP Extended (`Q45989477`).

This distinction is deliberate: a product or specific parent concept can be useful for discovering its preservation-relevant child versions without asserting that the parent itself is a general file-format class.

### Context classes

`video compression format` (`Q7927899`) is acquired conditionally as preservation context. These records are expected to receive a later role such as `codec_or_encoding`, not automatic canonical file-format status.

### Open file format

`open file format` (`Q1056408`) is evidence-gated and excludes records also classified as:

- domain application protocol (`Q16937237`);
- de facto standard (`Q385853`).

This keeps useful format-like records while avoiding known ambiguous protocol/standard cases.

## Deliberate exclusions from the final 56 review

Policy v3 does not aim mechanically for 595 / 595 recovery. The remaining review included concepts that should stay outside the file-format acquisition boundary, such as protocol/language/pathological-file examples.

Examples deliberately not promoted by class include:

- oEmbed where classified as a domain application protocol;
- Biological Expression Language where classified as a domain-specific/programming language;
- 42.zip as a zip-bomb/computer-file example;
- HTTP Cache where modeled as a de facto standard;
- broad programming-language, protocol, standard and generic computer-file classes.

The target is a defensible acquisition boundary, not perfect reproduction of everything the old transitive crawl happened to find.

## Policy identity and reproducibility

The current population-policy version is `2026-08-20-v3`.

The query-set hash includes:

- all population-query templates;
- policy version;
- reviewed specialist-class QIDs;
- conditional XML class;
- reviewed format-parent QIDs;
- contextual class QIDs;
- open-format class and exclusions;
- batch query templates;
- output columns.

The same policy metadata is written into the population snapshot, acquisition session manifest and final acquisition metadata. A policy change therefore cannot silently reuse a snapshot created under an older rule.

Population discovery is separate from property harvesting. Discovered QIDs are deduplicated and frozen for one acquisition session.

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
2. splits QIDs into bounded batches (default 200);
3. uses `VALUES ?format { ... }` for each property query;
4. stores each completed batch as a source snapshot;
5. merges all batches locally into the final CSV.

This keeps individual WDQS responses small and bounded.

## Resume after interruption

An incomplete acquisition session is recorded at:

```text
work/snapshots/wikidata_file_formats/.wikidata_acquisition_session.json
```

Each completed property batch is cached separately. Rerunning the same command resumes the frozen population and reuses completed batches. It does not repeat population discovery or completed batches.

Use `--restart` to deliberately abandon an incomplete session and discover a fresh population.

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

The default endpoint is:

```text
https://query.wikidata.org/sparql
```

HTTP 429 and transient 5xx responses are retried with bounded backoff. The CLI also retries interrupted or partial HTTP transfers.

## Compare acquisition policies

The comparison command compares two acquisition CSVs by QID and identifies useful non-direct records lost by a policy change:

```powershell
python -m registry_builder.wikidata_population_compare `
  --old old-wikidata.csv `
  --new new-wikidata.csv `
  --out-dir wikidata-population-comparison `
  --prefix policy-comparison
```

For this diagnostic, a **useful non-direct** record is a QID that is not a direct `P31 = Q235557` instance but has at least one PRONOM/LOC/NARA identifier, extension, MIME type or identification pattern.

The command writes:

- JSON summary;
- added QIDs;
- removed QIDs;
- old useful non-direct QIDs retained by the new policy;
- old useful non-direct QIDs missing from the new policy;
- direct `P31` class census for those missing records.

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

`WikidataSparqlAdapter.extract()` still returns an empty list. Wikidata is acquired for source study only and does not yet participate in identity reconciliation, criterion mapping, risk scoring or registry persistence.

The next step is to run policy v3, compare it with the original 85,269-QID broad snapshot and policy v2, confirm the intended remaining exclusions, and then move to source projection/reconciliation rather than continuing to broaden discovery.
