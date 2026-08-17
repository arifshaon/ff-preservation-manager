from __future__ import annotations

import json

import pytest

from preservation_risk_manager.cli import main
from preservation_risk_manager.literature_corpus import (
    ChunkSettings,
    Document,
    LiteratureCorpusError,
    build_index,
    build_literature_corpus,
    chunk_document,
    init_inbox,
    iter_inbox_files,
    search_corpus,
    search_index,
    tokenize,
)


def _settings(**overrides):
    base = {"corpus_version": "2026-09", "chunk_words": 12, "chunk_overlap": 3}
    base.update(overrides)
    return ChunkSettings(**base)


def _inbox(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    return inbox


def _drop(inbox, name, text, meta=None):
    path = inbox / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if meta is not None:
        path.with_name(path.name + ".meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return path


# --- tokenizing -----------------------------------------------------------


def test_tokenizer_preserves_domain_identifiers():
    assert "6.0" in tokenize("TIFF 6.0")
    assert "fmt/18" in tokenize("PUID fmt/18")
    assert "iso-19005" in tokenize("ISO-19005 applies")


def test_tokenizer_also_emits_identifier_parts():
    """A query for 'fmt' must still find a chunk that only writes 'fmt/18'."""
    tokens = tokenize("fmt/18")
    assert {"fmt", "18"} <= set(tokens)


# --- inbox ----------------------------------------------------------------


def test_init_inbox_creates_drop_folder_and_readme(tmp_path):
    result = init_inbox(tmp_path / "literature")
    assert (tmp_path / "literature" / "inbox").is_dir()
    readme = (tmp_path / "literature" / "README.md").read_text()
    assert "Drop documents in this folder" in readme
    assert result["status"] == "ok"


def test_inbox_scan_is_recursive_and_ignores_sidecars(tmp_path):
    inbox = _inbox(tmp_path)
    _drop(inbox, "a.txt", "alpha", meta={"title": "A"})
    _drop(inbox, "nested/b.txt", "beta")
    (inbox / ".hidden.txt").write_text("x", encoding="utf-8")
    (inbox / "README.md").write_text("x", encoding="utf-8")
    names = [path.name for path in iter_inbox_files(inbox)]
    assert names == ["a.txt", "b.txt"]


def test_missing_inbox_explains_how_to_create_it(tmp_path):
    with pytest.raises(LiteratureCorpusError, match="init-literature-inbox"):
        iter_inbox_files(tmp_path / "nope")


# --- chunking -------------------------------------------------------------


def test_chunks_never_span_a_page_boundary():
    document = Document(
        doc_id="doc-1", source_path="d.txt", title="D", content_hash="h",
        pages=["alpha beta gamma", "delta epsilon"],
    )
    chunks = chunk_document(document, _settings())
    assert [chunk.page for chunk in chunks] == [1, 2]
    assert chunks[0].text == "alpha beta gamma"
    assert chunks[1].text == "delta epsilon"


def test_long_pages_split_with_overlap():
    words = " ".join(f"w{index}" for index in range(30))
    document = Document(
        doc_id="doc-2", source_path="d.txt", title="D", content_hash="h", pages=[words]
    )
    chunks = chunk_document(document, _settings(chunk_words=10, chunk_overlap=3))
    assert len(chunks) > 1
    first = chunks[0].text.split()
    second = chunks[1].text.split()
    assert first[-3:] == second[:3]
    assert all(chunk.page == 1 for chunk in chunks)


def test_chunk_settings_reject_overlap_at_or_above_chunk_size():
    with pytest.raises(LiteratureCorpusError):
        ChunkSettings(corpus_version="v", chunk_words=10, chunk_overlap=10)


def test_chunk_settings_require_a_version():
    with pytest.raises(LiteratureCorpusError):
        ChunkSettings(corpus_version="  ")


# --- ingest behaviour -----------------------------------------------------


def test_ocr_text_is_indexed_regardless_of_length(tmp_path):
    """OCR output is already extracted; telling a curator to OCR it is wrong."""
    inbox = _inbox(tmp_path)
    _drop(inbox, "short.txt", "WordPerfect is practically extinct.")
    result = build_literature_corpus(inbox, tmp_path / "out", _settings())
    assert result["counts"]["documents_indexed"] == 1
    assert result["counts"]["needs_ocr"] == 0


def test_empty_text_file_is_reported_not_indexed(tmp_path):
    inbox = _inbox(tmp_path)
    _drop(inbox, "empty.txt", "   \n  ")
    result = build_literature_corpus(inbox, tmp_path / "out", _settings())
    assert result["counts"]["documents_indexed"] == 0
    assert result["needs_attention"]["skipped"][0]["status"] == "empty_document"


def test_unsupported_types_are_reported_with_a_reason(tmp_path):
    inbox = _inbox(tmp_path)
    _drop(inbox, "notes.csv", "a,b,c")
    result = build_literature_corpus(inbox, tmp_path / "out", _settings())
    skipped = result["needs_attention"]["skipped"][0]
    assert skipped["status"] == "unsupported_type"
    assert ".csv" in skipped["detail"]


def test_identical_documents_are_deduplicated(tmp_path):
    inbox = _inbox(tmp_path)
    _drop(inbox, "one.txt", "the same preservation text")
    _drop(inbox, "copy/two.txt", "the same preservation text")
    result = build_literature_corpus(inbox, tmp_path / "out", _settings())
    assert result["counts"]["documents_indexed"] == 1
    assert result["counts"]["duplicates"] == 1


def test_form_feed_is_treated_as_a_page_break(tmp_path):
    inbox = _inbox(tmp_path)
    _drop(inbox, "ocr.txt", "page one text\fpage two text")
    build_literature_corpus(inbox, tmp_path / "out", _settings())
    rows = [json.loads(line) for line in (tmp_path / "out" / "2026-09" / "chunks.jsonl").read_text().splitlines()]
    assert sorted(row["page"] for row in rows) == [1, 2]


def test_sidecar_metadata_is_applied_and_preserved(tmp_path):
    inbox = _inbox(tmp_path)
    _drop(inbox, "bit-list.txt", "WordPerfect is at risk.",
          meta={"title": "DPC Bit List 2025", "publisher": "DPC", "tags": ["trend"]})
    build_literature_corpus(inbox, tmp_path / "out", _settings())
    manifest = json.loads((tmp_path / "out" / "2026-09" / "manifest.json").read_text())
    document = manifest["documents"][0]
    assert document["title"] == "DPC Bit List 2025"
    assert document["metadata"]["tags"] == ["trend"]


def test_invalid_sidecar_is_rejected_clearly(tmp_path):
    inbox = _inbox(tmp_path)
    path = _drop(inbox, "doc.txt", "text")
    path.with_name(path.name + ".meta.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(LiteratureCorpusError, match="Invalid metadata sidecar"):
        build_literature_corpus(inbox, tmp_path / "out", _settings())


# --- identifiers and reproducibility --------------------------------------


def test_chunk_ids_are_unique_and_content_derived(tmp_path):
    inbox = _inbox(tmp_path)
    _drop(inbox, "a.txt", "alpha text here\fbeta text here")
    build_literature_corpus(inbox, tmp_path / "out", _settings())
    rows = [json.loads(line) for line in (tmp_path / "out" / "2026-09" / "chunks.jsonl").read_text().splitlines()]
    ids = [row["chunk_id"] for row in rows]
    assert len(set(ids)) == len(ids)


def test_rebuild_is_byte_identical(tmp_path):
    """Claims cite chunk_ids, so an unchanged inbox must not renumber them."""
    inbox = _inbox(tmp_path)
    _drop(inbox, "a.txt", "alpha preservation text")
    _drop(inbox, "b.txt", "beta preservation text")
    build_literature_corpus(inbox, tmp_path / "out", _settings())
    first = (tmp_path / "out" / "2026-09" / "chunks.jsonl").read_text()
    build_literature_corpus(inbox, tmp_path / "out", _settings())
    assert (tmp_path / "out" / "2026-09" / "chunks.jsonl").read_text() == first


def test_adding_a_document_does_not_renumber_existing_chunk_ids(tmp_path):
    inbox = _inbox(tmp_path)
    _drop(inbox, "b.txt", "beta preservation text")
    build_literature_corpus(inbox, tmp_path / "out", _settings())
    before = {
        json.loads(line)["chunk_id"]
        for line in (tmp_path / "out" / "2026-09" / "chunks.jsonl").read_text().splitlines()
    }
    _drop(inbox, "a.txt", "alpha sorts before beta")
    build_literature_corpus(inbox, tmp_path / "out", _settings())
    after = {
        json.loads(line)["chunk_id"]
        for line in (tmp_path / "out" / "2026-09" / "chunks.jsonl").read_text().splitlines()
    }
    assert before <= after


def test_editing_a_document_changes_its_ids(tmp_path):
    """New IDs are the signal that claims citing the old text need review."""
    inbox = _inbox(tmp_path)
    _drop(inbox, "a.txt", "original preservation text")
    build_literature_corpus(inbox, tmp_path / "out", _settings())
    before = (tmp_path / "out" / "2026-09" / "chunks.jsonl").read_text()
    _drop(inbox, "a.txt", "revised preservation text")
    build_literature_corpus(inbox, tmp_path / "out", _settings())
    after = (tmp_path / "out" / "2026-09" / "chunks.jsonl").read_text()
    assert json.loads(before)["chunk_id"] != json.loads(after)["chunk_id"]


# --- retrieval ------------------------------------------------------------


def test_search_ranks_the_relevant_chunk_first(tmp_path):
    inbox = _inbox(tmp_path)
    _drop(inbox, "a.txt", "JPEG 2000 renderer availability is limited.\fTIFF 6.0 is widely supported.")
    build_literature_corpus(inbox, tmp_path / "out", _settings(chunk_words=50))
    result = search_corpus(tmp_path / "out" / "2026-09", "TIFF 6.0 support", limit=2)
    assert result["results"]
    assert "TIFF" in result["results"][0]["snippet"]
    assert result["results"][0]["page"] == 2


def test_search_results_carry_citable_provenance(tmp_path):
    inbox = _inbox(tmp_path)
    _drop(inbox, "spec.txt", "JPEG 2000 wavelet compression.", meta={"title": "JP2 Spec"})
    build_literature_corpus(inbox, tmp_path / "out", _settings())
    hit = search_corpus(tmp_path / "out" / "2026-09", "wavelet")["results"][0]
    assert set(hit) >= {"chunk_id", "doc_id", "title", "page", "source_path", "score", "snippet"}
    assert hit["title"] == "JP2 Spec"


def test_search_with_no_match_returns_no_results(tmp_path):
    inbox = _inbox(tmp_path)
    _drop(inbox, "a.txt", "JPEG 2000 wavelet compression.")
    build_literature_corpus(inbox, tmp_path / "out", _settings())
    assert search_corpus(tmp_path / "out" / "2026-09", "kubernetes")["result_count"] == 0


def test_empty_query_returns_nothing():
    assert search_index(build_index([]), "   ") == []


def test_search_on_a_missing_corpus_explains_how_to_build_one(tmp_path):
    with pytest.raises(LiteratureCorpusError, match="build-literature-corpus"):
        search_corpus(tmp_path / "absent", "anything")


# --- PDF path -------------------------------------------------------------


def _minimal_pdf(pages: list[str]) -> bytes:
    """Build a tiny valid PDF with a real text layer, or none when pages is empty.

    Written by hand so the PDF path is covered without adding a PDF *writer*
    dependency to the test suite.
    """
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [{}] /Count {} >>".format(
            " ".join(f"{4 + 2 * index} 0 R" for index in range(len(pages))), len(pages)
        ),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, text in enumerate(pages):
        objects.append(
            "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R >> >> "
            f"/MediaBox [0 0 612 792] /Contents {5 + 2 * index} 0 R >>"
        )
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")

    output = "%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n{body}\nendobj\n"
    xref_at = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n"
    output += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    return output.encode("latin-1")


def test_pdf_pages_are_extracted_and_page_numbered(tmp_path):
    pytest.importorskip("pypdf", reason="PDF ingest requires the optional 'corpus' extra")
    inbox = _inbox(tmp_path)
    (inbox / "spec.pdf").write_bytes(
        _minimal_pdf([
            "JPEG 2000 Part 1 defines wavelet compression and the JP2 file format",
            "TIFF 6.0 is widely supported by preservation tooling across archives",
        ])
    )
    result = build_literature_corpus(inbox, tmp_path / "out", _settings(chunk_words=50))
    assert result["counts"]["documents_indexed"] == 1
    hit = search_corpus(tmp_path / "out" / "2026-09", "TIFF 6.0")["results"][0]
    assert hit["page"] == 2


def test_scanned_pdf_without_a_text_layer_is_flagged_for_ocr(tmp_path):
    pytest.importorskip("pypdf", reason="PDF ingest requires the optional 'corpus' extra")
    inbox = _inbox(tmp_path)
    (inbox / "scan.pdf").write_bytes(_minimal_pdf([""]))
    result = build_literature_corpus(inbox, tmp_path / "out", _settings())
    assert result["counts"]["documents_indexed"] == 0
    flagged = result["needs_attention"]["needs_ocr"][0]
    assert flagged["status"] == "needs_ocr"
    assert "run OCR" in flagged["detail"]


def test_corrupt_pdf_is_reported_not_fatal(tmp_path):
    pytest.importorskip("pypdf", reason="PDF ingest requires the optional 'corpus' extra")
    inbox = _inbox(tmp_path)
    (inbox / "broken.pdf").write_bytes(b"%PDF-1.4\nnot really a pdf\n")
    _drop(inbox, "good.txt", "WordPerfect is practically extinct.")
    result = build_literature_corpus(inbox, tmp_path / "out", _settings())
    # The healthy document still lands; the broken one is reported.
    assert result["counts"]["documents_indexed"] == 1
    assert any(item["status"] == "extraction_failed" for item in result["needs_attention"]["skipped"])


# --- CLI ------------------------------------------------------------------


def test_cli_round_trip_init_build_and_search(tmp_path, capsys):
    main(["init-literature-inbox", "--path", str(tmp_path / "lit")])
    capsys.readouterr()
    inbox = tmp_path / "lit" / "inbox"
    _drop(inbox, "dpc.txt", "WordPerfect is practically extinct owing to renderer scarcity.")

    assert main([
        "build-literature-corpus",
        "--inbox", str(inbox),
        "--out", str(tmp_path / "corpus"),
        "--corpus-version", "2026-09",
    ]) == 0
    built = json.loads(capsys.readouterr().out)
    assert built["counts"]["documents_indexed"] == 1

    assert main([
        "search-literature",
        "--corpus", str(tmp_path / "corpus" / "2026-09"),
        "--query", "wordperfect renderer",
    ]) == 0
    found = json.loads(capsys.readouterr().out)
    assert found["results"][0]["chunk_id"].startswith("dpc-")


def test_cli_reports_a_missing_inbox_without_a_traceback(tmp_path, capsys):
    exit_code = main([
        "build-literature-corpus",
        "--inbox", str(tmp_path / "absent"),
        "--out", str(tmp_path / "corpus"),
        "--corpus-version", "2026-09",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "literature_corpus_error"
    assert "init-literature-inbox" in payload["error"]
