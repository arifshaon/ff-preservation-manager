from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.request_api import search_family_docs, search_format_docs


def _reader() -> RegistryReader:
    return RegistryReader(store=JsonRegistryStore({
        "canonical_formats": [
            {
                "canonical_id": "fmt-pdf",
                "preferred_name": "PDF",
                "current": True,
            },
            {
                "canonical_id": "puid-fmt-14",
                "preferred_name": "Acrobat PDF 1.0 - Portable Document Format",
                "current": True,
            },
            {
                "canonical_id": "loc-fdd000522",
                "preferred_name": "TerraGo Geospatial PDF",
                "current": True,
            },
            {
                "canonical_id": "puid-fmt-559",
                "preferred_name": "Adobe Illustrator Artwork 10.0",
                "extensions": ["ai", "pdf"],
                "current": True,
            },
            {
                "canonical_id": "puid-fmt-1058",
                "preferred_name": "SNAP Processed Data File",
                "identifiers": {"extension": ["pdf"]},
                "current": True,
            },
            {
                "canonical_id": "fmt-explicit-member",
                "preferred_name": "Accessibility Archive Container",
                "family": "PDF",
                "current": True,
            },
        ]
    }))


def test_family_search_uses_names_or_explicit_family_not_incidental_extensions():
    rows = search_family_docs(_reader(), "PDF")
    ids = {_row["canonical_id"] for _row in rows}

    assert "fmt-pdf" in ids
    assert "puid-fmt-14" in ids
    assert "loc-fdd000522" in ids
    assert "fmt-explicit-member" in ids
    assert "puid-fmt-559" not in ids
    assert "puid-fmt-1058" not in ids


def test_general_search_still_finds_incidental_pdf_references_for_discovery():
    rows = search_format_docs(_reader(), "PDF")
    ids = {_row["canonical_id"] for _row in rows}

    assert "puid-fmt-559" in ids
    assert "puid-fmt-1058" in ids
