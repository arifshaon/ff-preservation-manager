from __future__ import annotations

from preservation_risk_manager.data_access import RegistryReader
from preservation_risk_manager.format_resolver import FormatResolver, resolve_format


FORMATS = [
    {
        "canonical_id": "fmt/18",
        "name": "Portable Document Format",
        "short_name": "PDF",
        "puids": ["fmt/18"],
        "mime_types": ["application/pdf"],
        "extensions": ["pdf"],
        "identifiers": [{"type": "loc", "value": "fdd000030"}],
    },
    {
        "canonical_id": "fmt/354",
        "name": "PDF/A-1",
        "aliases": ["PDF/A"],
        "puids": ["fmt/354"],
        "mime_types": ["application/pdf"],
        "extensions": ["pdf"],
    },
    {
        "canonical_id": "fmt/netcdf",
        "name": "Network Common Data Form",
        "short_name": "netCDF",
        "extensions": ["nc", ".cdf"],
        "identifiers": [{"type": "wikidata", "value": "Q1362585"}],
    },
]


class FakeStore:
    def query(self, collection, filt=None):
        if collection != "canonical_formats":
            return []
        if not filt:
            return FORMATS
        return [row for row in FORMATS if all(row.get(key) == value for key, value in filt.items())]


def test_resolves_exact_canonical_id_before_other_fields():
    result = resolve_format("fmt/18", FORMATS)

    assert result.resolved
    assert result.match_type == "canonical_id"
    assert result.format_doc["canonical_id"] == "fmt/18"


def test_resolves_authority_identifier_from_typed_fields_and_identifier_list():
    puid = resolve_format("fmt/354", FORMATS)
    loc = resolve_format("fdd000030", FORMATS)
    wikidata = resolve_format("Q1362585", FORMATS)

    assert puid.resolved and puid.format_doc["canonical_id"] == "fmt/354"
    assert loc.resolved and loc.format_doc["canonical_id"] == "fmt/18"
    assert wikidata.resolved and wikidata.format_doc["canonical_id"] == "fmt/netcdf"


def test_resolves_unique_mime_extension_and_name_values():
    mime = resolve_format("application/pdf", [FORMATS[0]])
    extension = resolve_format(".nc", FORMATS)
    name = resolve_format("netcdf", FORMATS)

    assert mime.resolved and mime.match_type == "mime_type"
    assert extension.resolved and extension.match_type == "extension"
    assert name.resolved and name.match_type == "name"


def test_reports_ambiguous_extension_instead_of_guessing_pdf_variant():
    result = resolve_format(".pdf", FORMATS)

    assert result.ambiguous
    assert result.match_type == "extension"
    assert [match["canonical_id"] for match in result.matches] == ["fmt/18", "fmt/354"]


def test_reports_not_found_for_unknown_format_token():
    result = resolve_format("made-up-format", FORMATS)

    assert result.not_found
    assert result.format_doc is None
    assert result.matches == ()


def test_format_resolver_uses_registry_reader_canonical_formats():
    resolver = FormatResolver(RegistryReader(store=FakeStore()))

    result = resolver.resolve("fdd000030")

    assert result.resolved
    assert result.format_doc["canonical_id"] == "fmt/18"
