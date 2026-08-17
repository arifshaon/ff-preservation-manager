from preservation_risk_manager.data_access import JsonRegistryStore, RegistryReader
from preservation_risk_manager.request_api import search_format_docs


def test_family_search_prefers_fmt_record_over_source_alias_with_same_puid():
    reader = RegistryReader(store=JsonRegistryStore({
        "canonical_formats": [
            {
                "canonical_id": "fmt-pdf",
                "preferred_name": "PDF",
                "puids": ["fmt/18"],
                "identifiers": {"puid": ["fmt/18"]},
                "current": True,
            },
            {
                "canonical_id": "puid-fmt-18",
                "preferred_name": "Portable Document Format 1.4",
                "puids": ["fmt/18"],
                "identifiers": {"puid": ["fmt/18"]},
                "current": True,
            },
            {
                "canonical_id": "fmt-pdfa",
                "preferred_name": "PDF/A",
                "puids": ["fmt/95"],
                "identifiers": {"puid": ["fmt/95"]},
                "current": True,
            },
        ]
    }))

    matches = search_format_docs(reader, "PDF")
    ids = [row["canonical_id"] for row in matches]

    assert "fmt-pdf" in ids
    assert "puid-fmt-18" not in ids
    assert "fmt-pdfa" in ids
