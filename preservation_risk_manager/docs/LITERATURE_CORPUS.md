# Literature corpus (Corpus B)

Corpus A is generated from the registry. **Corpus B** covers the criteria no registry
answers — trend, end-of-life signals, and the scientific formats with no authority record —
and its source material is ordinary documents you already have or can download.

The workflow is deliberately low-ceremony: drop files in a folder, run one command.

## Three commands

```bash
# 1. create the drop folder (once)
python -m preservation_risk_manager init-literature-inbox --path literature/

# 2. drop PDFs / OCR text into literature/inbox/, then build
python -m preservation_risk_manager build-literature-corpus \
  --inbox literature/inbox \
  --out corpus/ \
  --corpus-version 2026-09

# 3. search it
python -m preservation_risk_manager search-literature \
  --corpus corpus/2026-09 \
  --query "JPEG 2000 renderer availability"
```

`init-literature-inbox` writes a `README.md` next to the folder explaining what to drop, so
a colleague can use it without reading this document.

## What you can drop

| Type | Needs | Notes |
| --- | --- | --- |
| `.pdf` | the `corpus` extra | `pip install -e ".[corpus]"` |
| `.txt`, `.md` | nothing | OCR output, plain text |

Subfolders are scanned recursively. Anything else is reported as `unsupported_type` rather
than silently ignored.

PDF support is an optional extra because the package otherwise has **zero runtime
dependencies**. If you drop a PDF without it installed, the error says exactly what to run.
Dropping OCR text instead needs nothing.

## Optional metadata

Nothing is required — a document's title defaults to its filename. To record more, add a
sidecar next to the file named `<filename>.meta.json`:

```json
{
  "title": "DPC Bit List 2025",
  "url": "https://www.dpconline.org/...",
  "publisher": "Digital Preservation Coalition",
  "year": 2025,
  "licence": "CC-BY",
  "tags": ["trend", "at-risk"]
}
```

Any subset is accepted and unknown keys are preserved into the manifest.

## Output

```
corpus/2026-09/
  chunks.jsonl        one record per chunk: chunk_id, doc_id, page, text, title, source_path
  index.json          BM25 inverted index
  manifest.json       per-document counts, hashes, metadata, settings
  ingest_report.json  everything that needs a human: needs_ocr, skipped, duplicates
```

## Chunking

Chunks are word windows with overlap (`--chunk-words`, default 220; `--chunk-overlap`,
default 40) and **never span a page boundary**, so every chunk carries a single citable page
number — which is what a criterion claim needs to point at.

A form feed (`\f`) in text input is treated as a page break, which is what most OCR tools
emit, so page numbers stay meaningful for text dropped alongside PDFs.

## Stable chunk IDs

Criterion claims store `chunk_ids` so an assessment can be replayed against the evidence it
actually used. IDs are therefore derived from **document content**, not from position in a
directory listing:

```
<filename-slug>-<content-hash-12>:<ordinal-4>
bit-list-ocr-d2862c51053e:0001
```

Consequences, all intentional:

- Re-running over an unchanged inbox produces **byte-identical** output.
- Adding a document does **not** renumber existing chunks.
- Editing a document **does** change its IDs. That is the signal that claims citing the old
  text need review, rather than silently re-pointing them at different words.

## What needs a human

`ingest_report.json` is the file to read after a build.

| Status | Meaning |
| --- | --- |
| `needs_ocr` | A PDF with no text layer. Run OCR and drop the result back in. |
| `unsupported_type` | Not a PDF or text file. |
| `extraction_failed` | Corrupt or unreadable file; the rest of the build still completes. |
| `empty_document` | A text file with no content. |
| `duplicate` | Identical content to a document already indexed. |

The OCR check applies to **PDFs only**. Text you drop is already extracted, so a short `.txt`
is indexed as-is — telling a curator to OCR their own OCR output would be nonsense. The
threshold (`--min-chars-per-doc`, default 50) sits low deliberately: wrongly flagging a
readable one-paragraph vendor notice is worse than admitting a nearly blank scan, which is
visible in the manifest anyway.

## Retrieval is lexical, not semantic

Search is BM25 over the chunk store. Tokenization preserves domain identifiers — `TIFF 6.0`,
`fmt/18`, and `ISO-19005` survive as single terms, and their parts are indexed too, so a
query for `fmt` still finds a chunk that only writes `fmt/18`.

**It does not do synonym or concept matching.** A query for "obsolete" will not retrieve a
passage that only says "superseded". This suits a vocabulary of exact format and standard
names, and it keeps the package dependency-free.

If you later want embedding-based retrieval, `chunks.jsonl` is the stable artefact and does
not change — only `index.json` would be replaced.

## Scope

Aim for **200–500 curated documents**: iPRES proceedings, DPC reports and the Bit List, IJDC
papers, format specifications, standards-body publications, vendor EOL notices, and domain
documentation for the scientific formats the registry does not cover.

Bulk-dumping a crawl makes retrieval worse, not better — every irrelevant chunk is another
chance to outrank the passage you needed.

Build this **after** Corpus A: the gap list from `evidence_gaps.py` tells you which documents
are actually worth acquiring, which is a much cheaper way to choose 300 documents than
guessing.

## Related

- [`TRAINING_CORPUS.md`](TRAINING_CORPUS.md) — Corpus A, generated from the registry
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
