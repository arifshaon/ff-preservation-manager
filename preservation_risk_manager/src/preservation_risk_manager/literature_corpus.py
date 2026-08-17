"""Build Corpus B: a searchable literature index from dropped documents.

Corpus A is generated from the registry. Corpus B covers the criteria no
registry answers — trend, end-of-life signals, domain-specific scientific
formats — and its source material is ordinary documents: standards, iPRES and
IJDC papers, DPC reports, format specifications, vendor EOL notices.

The intended workflow is deliberately low-ceremony. A curator drops PDFs or OCR
text into an inbox directory and runs one command. Nothing needs to be
registered, named, or configured first; metadata is optional and inferred from
the filename when absent.

Two properties matter downstream and are enforced here.

Chunk IDs are derived from document content, not from position in a directory
listing. Criterion claims store ``chunk_ids`` so an assessment can be replayed
against the evidence it actually used; an ID that shifted when an unrelated file
was added to the inbox would break that replay. Re-running over unchanged files
reproduces byte-identical output, and a changed document yields new IDs, which
is the honest signal that claims citing the old text need review.

Extraction failure is reported, never silent. A scanned PDF with no text layer
extracts to nothing and would otherwise enter the corpus as an empty document
that can never be retrieved. Those are flagged as ``needs_ocr`` so the curator
knows to run OCR rather than wondering why a document never appears in results.

Retrieval is lexical (BM25), which keeps the package dependency-free and suits a
vocabulary of exact format and standard names. It does not do synonym or
semantic matching: a query for "obsolete" will not retrieve a passage that only
says "superseded". Embedding-based retrieval can be layered on later; the chunk
store is the stable artefact and does not change if it is.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable

from preservation_risk_manager.errors import PreservationRiskManagerError


TEXT_SUFFIXES = {".txt", ".text", ".md", ".markdown"}
PDF_SUFFIXES = {".pdf"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES
METADATA_SUFFIX = ".meta.json"

# Many OCR tools emit a form feed between pages. Honouring it keeps page numbers
# meaningful for text dropped alongside PDFs.
PAGE_BREAK = "\f"

# A PDF with no text layer extracts to roughly nothing; a short but real
# document (a one-paragraph vendor EOL notice) still clears this comfortably.
# The threshold sits low deliberately: wrongly telling a curator to OCR a
# readable document is worse than admitting a nearly blank one, which is
# visible in the manifest anyway.
DEFAULT_MIN_CHARS_PER_DOC = 50

BM25_K1 = 1.5
BM25_B = 0.75

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[./\-][a-z0-9]+)*")
_SPLIT_PATTERN = re.compile(r"[./\-]")
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")

INBOX_README = """# Literature inbox (Corpus B)

Drop documents in this folder, then run:

    python -m preservation_risk_manager build-literature-corpus \\
      --inbox {inbox} \\
      --out {out} \\
      --corpus-version YYYY-MM

## What to drop

- `.pdf`  — standards, specifications, papers, reports, vendor notices
- `.txt`, `.md` — OCR output or any plain text

Subfolders are fine; they are scanned recursively.

## Scanned PDFs

A PDF with no text layer cannot be indexed. Those are reported as `needs_ocr`
in `ingest_report.json`. Run OCR over them and drop the resulting text or
searchable PDF back into this folder.

## Optional metadata

Nothing is required — a document's title defaults to its filename. To record
more, add a sidecar file next to it named `<filename>.meta.json`:

    {{
      "title": "PDF/A-1 (ISO 19005-1)",
      "url": "https://www.iso.org/standard/38920.html",
      "publisher": "ISO",
      "year": 2005,
      "licence": "proprietary",
      "tags": ["standard", "pdf"]
    }}

Any subset of those keys is accepted, and unknown keys are preserved.

## Curate, do not crawl

This corpus is meant to be 200–500 documents chosen because they answer
questions the registry cannot. Bulk-dumping a web crawl makes retrieval worse,
not better.
"""


class LiteratureCorpusError(PreservationRiskManagerError):
    """Raised when a literature corpus cannot be built."""


@dataclass(frozen=True)
class ChunkSettings:
    """Controls chunking, indexing, and ingest reporting."""

    corpus_version: str
    chunk_words: int = 220
    chunk_overlap: int = 40
    min_chars_per_doc: int = DEFAULT_MIN_CHARS_PER_DOC

    def __post_init__(self) -> None:
        if self.chunk_words <= 0:
            raise LiteratureCorpusError("chunk_words must be greater than zero.")
        if self.chunk_overlap < 0:
            raise LiteratureCorpusError("chunk_overlap must not be negative.")
        if self.chunk_overlap >= self.chunk_words:
            raise LiteratureCorpusError("chunk_overlap must be smaller than chunk_words.")
        if not str(self.corpus_version).strip():
            raise LiteratureCorpusError("corpus_version is required.")


@dataclass
class Document:
    doc_id: str
    source_path: str
    title: str
    content_hash: str
    pages: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_pdf: bool = False

    @property
    def char_count(self) -> int:
        return sum(len(page) for page in self.pages)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    page: int
    ordinal: int
    text: str

    def to_record(self, corpus_version: str, title: str, source_path: str) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "page": self.page,
            "ordinal": self.ordinal,
            "text": self.text,
            "title": title,
            "source_path": source_path,
            "corpus_version": corpus_version,
        }


# --- text handling --------------------------------------------------------


def _normalise_text(value: str) -> str:
    """Collapse OCR whitespace artefacts without destroying token boundaries."""
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("­", "")  # soft hyphen, common in PDF extraction
    text = re.sub(r"-\n(?=[a-z])", "", text)  # de-hyphenate across line breaks
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(value: str) -> list[str]:
    """Tokenize for indexing, preserving version-like and identifier-like terms.

    ``TIFF 6.0`` and ``fmt/18`` are single meaningful terms in this domain, so
    internal dots, slashes, and hyphens are kept. The parts are also emitted so
    a query for ``fmt`` still retrieves a chunk that only writes ``fmt/18``.
    """
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer((value or "").lower()):
        token = match.group(0)
        tokens.append(token)
        if _SPLIT_PATTERN.search(token):
            tokens.extend(part for part in _SPLIT_PATTERN.split(token) if part)
    return tokens


def _slug(value: str, *, limit: int = 48) -> str:
    slug = _SLUG_PATTERN.sub("-", str(value or "").lower()).strip("-")
    return (slug[:limit].rstrip("-")) or "document"


# --- extraction -----------------------------------------------------------


def _read_pdf_pages(path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise LiteratureCorpusError(
            "Reading PDFs requires the optional 'corpus' extra. "
            "Install it with: pip install -e \".[corpus]\" "
            "(or drop OCR text as .txt instead, which needs no extra)."
        ) from exc
    reader = PdfReader(str(path))
    return [_normalise_text(page.extract_text() or "") for page in reader.pages]


def _read_text_pages(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return [_normalise_text(page) for page in raw.split(PAGE_BREAK)]


def _load_sidecar(path: Path) -> dict[str, Any]:
    sidecar = path.with_name(path.name + METADATA_SUFFIX)
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LiteratureCorpusError(f"Invalid metadata sidecar {sidecar}: {exc}") from exc
    if not isinstance(data, dict):
        raise LiteratureCorpusError(f"Metadata sidecar {sidecar} must contain a JSON object.")
    return data


def iter_inbox_files(inbox: Path) -> list[Path]:
    """Return supported files in a stable order, ignoring sidecars and hidden files."""
    if not inbox.is_dir():
        raise LiteratureCorpusError(
            f"Inbox directory not found: {inbox}. "
            "Create it with: python -m preservation_risk_manager init-literature-inbox --path <dir>"
        )
    files: list[Path] = []
    for path in sorted(inbox.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.name.endswith(METADATA_SUFFIX) or path.name == "README.md":
            continue
        files.append(path)
    return files


def extract_document(path: Path, inbox: Path) -> tuple[Document | None, dict[str, Any] | None]:
    """Extract one file, or return the reason it could not be ingested."""
    relative = str(path.relative_to(inbox))
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return None, {
            "source_path": relative,
            "status": "unsupported_type",
            "detail": f"'{suffix or path.name}' is not a supported document type.",
        }
    try:
        pages = _read_pdf_pages(path) if suffix in PDF_SUFFIXES else _read_text_pages(path)
    except LiteratureCorpusError:
        raise
    except Exception as exc:
        return None, {
            "source_path": relative,
            "status": "extraction_failed",
            "detail": f"{type(exc).__name__}: {exc}",
        }

    metadata = _load_sidecar(path)
    joined = "\n".join(pages)
    # The ID is content-derived so that re-running over an unchanged inbox
    # reproduces the same chunk IDs, and an edited document produces new ones.
    content_hash = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    doc_id = f"{_slug(path.stem)}-{content_hash[:12]}"
    title = str(metadata.get("title") or path.stem.replace("_", " ").strip())
    return (
        Document(
            doc_id=doc_id,
            source_path=relative,
            title=title,
            content_hash=content_hash,
            pages=pages,
            metadata=metadata,
            is_pdf=suffix in PDF_SUFFIXES,
        ),
        None,
    )


# --- chunking -------------------------------------------------------------


def chunk_document(document: Document, settings: ChunkSettings) -> list[Chunk]:
    """Split a document into overlapping, page-attributed chunks.

    Chunks never span a page boundary so every chunk keeps a single citable page
    number, which is what a criterion claim needs to point at.
    """
    chunks: list[Chunk] = []
    ordinal = 0
    step = settings.chunk_words - settings.chunk_overlap
    for page_number, page_text in enumerate(document.pages, start=1):
        words = page_text.split()
        if not words:
            continue
        start = 0
        while start < len(words):
            window = words[start : start + settings.chunk_words]
            text = " ".join(window).strip()
            if text:
                chunks.append(
                    Chunk(
                        chunk_id=f"{document.doc_id}:{ordinal:04d}",
                        doc_id=document.doc_id,
                        page=page_number,
                        ordinal=ordinal,
                        text=text,
                    )
                )
                ordinal += 1
            if start + settings.chunk_words >= len(words):
                break
            start += step
    return chunks


# --- index ----------------------------------------------------------------


def build_index(chunks: list[Chunk]) -> dict[str, Any]:
    """Build a BM25 inverted index over the chunk store."""
    postings: dict[str, list[list[int]]] = {}
    lengths: list[int] = []
    for position, chunk in enumerate(chunks):
        tokens = tokenize(chunk.text)
        lengths.append(len(tokens))
        for term, frequency in sorted(Counter(tokens).items()):
            postings.setdefault(term, []).append([position, frequency])
    total = len(chunks)
    return {
        "algorithm": "bm25",
        "k1": BM25_K1,
        "b": BM25_B,
        "chunk_count": total,
        "average_length": (sum(lengths) / total) if total else 0.0,
        "lengths": lengths,
        "chunk_ids": [chunk.chunk_id for chunk in chunks],
        "postings": postings,
    }


def search_index(
    index: dict[str, Any],
    query: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return the highest scoring chunk positions for a query."""
    terms = tokenize(query)
    if not terms:
        return []
    postings = index.get("postings") or {}
    lengths = index.get("lengths") or []
    total = int(index.get("chunk_count") or 0)
    average = float(index.get("average_length") or 0.0) or 1.0
    k1 = float(index.get("k1") or BM25_K1)
    b = float(index.get("b") or BM25_B)

    scores: dict[int, float] = {}
    matched: dict[int, set[str]] = {}
    for term in sorted(set(terms)):
        entries = postings.get(term)
        if not entries:
            continue
        document_frequency = len(entries)
        idf = math.log(1 + (total - document_frequency + 0.5) / (document_frequency + 0.5))
        for position, frequency in entries:
            length = lengths[position] if position < len(lengths) else average
            denominator = frequency + k1 * (1 - b + b * (length / average))
            scores[position] = scores.get(position, 0.0) + idf * (frequency * (k1 + 1)) / denominator
            matched.setdefault(position, set()).add(term)

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"position": position, "score": round(score, 6), "matched_terms": sorted(matched[position])}
        for position, score in ranked[:limit]
    ]


def _snippet(text: str, terms: Iterable[str], *, width: int = 240) -> str:
    lowered = text.lower()
    best = -1
    for term in terms:
        found = lowered.find(term)
        if found != -1 and (best == -1 or found < best):
            best = found
    if best == -1:
        return text[:width].strip()
    start = max(0, best - width // 3)
    snippet = text[start : start + width].strip()
    return ("…" if start > 0 else "") + snippet + ("…" if start + width < len(text) else "")


# --- build ----------------------------------------------------------------


def init_inbox(root: Path, *, out_hint: str = "corpus/") -> dict[str, Any]:
    """Create the drop folder and its README."""
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    readme = root / "README.md"
    readme.write_text(INBOX_README.format(inbox=inbox, out=out_hint), encoding="utf-8")
    return {
        "status": "ok",
        "inbox": str(inbox),
        "readme": str(readme),
        "next": (
            "Drop PDFs or OCR text into the inbox, then run "
            "'python -m preservation_risk_manager build-literature-corpus'."
        ),
    }


def build_literature_corpus(
    inbox: Path,
    out_root: Path,
    settings: ChunkSettings,
) -> dict[str, Any]:
    """Ingest an inbox into a versioned, searchable chunk store."""
    files = iter_inbox_files(inbox)
    documents: list[Document] = []
    skipped: list[dict[str, Any]] = []
    needs_ocr: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    seen_hashes: dict[str, str] = {}

    for path in files:
        document, problem = extract_document(path, inbox)
        if problem is not None:
            skipped.append(problem)
            continue
        assert document is not None
        # The OCR heuristic applies to PDFs only. Text dropped in the inbox is
        # already extracted — telling a curator to OCR their own OCR output
        # because it happens to be short would be actively misleading. A text
        # file is only rejected when it carries no content at all.
        if document.is_pdf and document.char_count < settings.min_chars_per_doc:
            needs_ocr.append({
                "source_path": document.source_path,
                "status": "needs_ocr",
                "characters_extracted": document.char_count,
                "detail": (
                    "Little or no text layer found. If this is a scanned document, run OCR "
                    "and drop the resulting text or searchable PDF back into the inbox."
                ),
            })
            continue
        if not document.is_pdf and not document.char_count:
            skipped.append({
                "source_path": document.source_path,
                "status": "empty_document",
                "detail": "The file contains no text.",
            })
            continue
        if document.content_hash in seen_hashes:
            duplicates.append({
                "source_path": document.source_path,
                "status": "duplicate",
                "duplicate_of": seen_hashes[document.content_hash],
            })
            continue
        seen_hashes[document.content_hash] = document.source_path
        documents.append(document)

    documents.sort(key=lambda item: item.doc_id)
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, settings))

    index = build_index(chunks)
    titles = {document.doc_id: document.title for document in documents}
    paths = {document.doc_id: document.source_path for document in documents}

    out_dir = out_root / settings.corpus_version
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "chunks.jsonl").open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            record = chunk.to_record(settings.corpus_version, titles[chunk.doc_id], paths[chunk.doc_id])
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    (out_dir / "index.json").write_text(json.dumps(index, sort_keys=True), encoding="utf-8")

    manifest = {
        "corpus_version": settings.corpus_version,
        "inbox": str(inbox),
        "settings": {
            "chunk_words": settings.chunk_words,
            "chunk_overlap": settings.chunk_overlap,
            "min_chars_per_doc": settings.min_chars_per_doc,
        },
        "counts": {
            "files_seen": len(files),
            "documents_indexed": len(documents),
            "chunks": len(chunks),
            "skipped": len(skipped),
            "needs_ocr": len(needs_ocr),
            "duplicates": len(duplicates),
        },
        "documents": [
            {
                "doc_id": document.doc_id,
                "title": document.title,
                "source_path": document.source_path,
                "content_hash": document.content_hash,
                "pages": len(document.pages),
                "characters": document.char_count,
                "chunks": sum(1 for chunk in chunks if chunk.doc_id == document.doc_id),
                "metadata": document.metadata,
            }
            for document in documents
        ],
        "retrieval": {"algorithm": "bm25", "lexical_only": True},
    }
    report = {
        "needs_ocr": needs_ocr,
        "skipped": skipped,
        "duplicates": duplicates,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "ingest_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    attention = len(needs_ocr) + len(skipped)
    return {
        "status": "ok" if not attention else "ok_with_warnings",
        "corpus_version": settings.corpus_version,
        "output_dir": str(out_dir),
        "files": {
            "chunks": str(out_dir / "chunks.jsonl"),
            "index": str(out_dir / "index.json"),
            "manifest": str(out_dir / "manifest.json"),
            "ingest_report": str(out_dir / "ingest_report.json"),
        },
        "counts": manifest["counts"],
        "needs_attention": {"needs_ocr": needs_ocr, "skipped": skipped, "duplicates": duplicates},
    }


def load_corpus(corpus_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load a built corpus's chunk records and index."""
    chunks_path = corpus_dir / "chunks.jsonl"
    index_path = corpus_dir / "index.json"
    if not chunks_path.is_file() or not index_path.is_file():
        raise LiteratureCorpusError(
            f"No literature corpus found in {corpus_dir}. "
            "Build one with: python -m preservation_risk_manager build-literature-corpus"
        )
    records = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    index = json.loads(index_path.read_text(encoding="utf-8"))
    return records, index


def search_corpus(corpus_dir: Path, query: str, *, limit: int = 10) -> dict[str, Any]:
    """Search a built corpus and return citable chunk hits."""
    records, index = load_corpus(corpus_dir)
    hits = search_index(index, query, limit=limit)
    results = []
    for hit in hits:
        record = records[hit["position"]]
        results.append({
            "chunk_id": record["chunk_id"],
            "doc_id": record["doc_id"],
            "title": record["title"],
            "page": record["page"],
            "source_path": record["source_path"],
            "score": hit["score"],
            "matched_terms": hit["matched_terms"],
            "snippet": _snippet(record["text"], hit["matched_terms"]),
        })
    return {
        "status": "ok",
        "query": query,
        "corpus_version": index.get("corpus_version") or corpus_dir.name,
        "result_count": len(results),
        "results": results,
    }
