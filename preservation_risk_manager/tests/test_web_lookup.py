from preservation_risk_manager.web_lookup_service import lookup_puids


class FakeReader:
    def __init__(self, rows):
        self.rows = rows

    def list_canonical_formats(self):
        return list(self.rows)


def _rows():
    return [
        {
            "canonical_id": "puid-fmt-18",
            "preferred_name": "Acrobat PDF 1.4",
            "version": "1.4",
            "puids": ["fmt/18"],
            "extensions": ["pdf"],
            "mime_types": ["application/pdf"],
        },
        {
            "canonical_id": "puid-fmt-19",
            "preferred_name": "Acrobat PDF 1.5",
            "version": "1.5",
            "puids": ["fmt/19"],
            "extensions": ["pdf"],
            "mime_types": ["application/pdf"],
        },
        {
            "canonical_id": "puid-fmt-276",
            "preferred_name": "Acrobat PDF 1.7",
            "version": "1.7",
            "puids": ["fmt/276"],
            "extensions": ["pdf"],
            "mime_types": ["application/pdf"],
            "loc_ids": ["fdd000277"],
        },
        {
            "canonical_id": "loc-fdd-no-puid",
            "preferred_name": "PDF contextual record without PUID",
            "loc_ids": ["fdd999999"],
        },
        {
            "canonical_id": "puid-fmt-353",
            "preferred_name": "Tagged Image File Format",
            "puids": ["fmt/353"],
            "extensions": ["tif", "tiff"],
            "mime_types": ["image/tiff"],
        },
    ]


def test_exact_puid_lookup_returns_that_format():
    result = lookup_puids(FakeReader(_rows()), "fmt/276", limit=10)

    assert result["match_count"] == 1
    assert result["returned_count"] == 1
    assert result["limit_applied"] is False
    assert result["matches"][0]["puid"] == "fmt/276"
    assert result["matches"][0]["label"] == "Acrobat PDF 1.7"
    assert result["matches"][0]["loc_ids"] == ["fdd000277"]


def test_name_lookup_returns_only_puid_backed_formats_and_applies_limit():
    result = lookup_puids(FakeReader(_rows()), "PDF", limit=2)

    assert result["match_count"] == 3
    assert result["returned_count"] == 2
    assert result["limit"] == 2
    assert result["limit_applied"] is True
    assert all(row["puid"] for row in result["matches"])
    assert "loc-fdd-no-puid" not in {row["canonical_id"] for row in result["matches"]}


def test_lookup_can_search_mime_and_extension():
    mime = lookup_puids(FakeReader(_rows()), "image/tiff", limit=10)
    extension = lookup_puids(FakeReader(_rows()), "tiff", limit=10)

    assert mime["matches"][0]["puid"] == "fmt/353"
    assert extension["matches"][0]["puid"] == "fmt/353"
