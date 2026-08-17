from preservation_risk_manager.integration_cli import _ai_format_context


class FakeReader:
    def __init__(self, source_records):
        self.source_records = source_records

    def query(self, collection, filt=None):
        if collection != "source_records":
            return []
        filt = filt or {}
        return [
            row
            for row in self.source_records
            if all(row.get(key) == value for key, value in filt.items())
        ]


def test_ai_format_context_recovers_source_declared_version_and_signature():
    format_doc = {
        "canonical_id": "puid-fmt-505",
        "preferred_name": "Adobe Flash",
        "identifiers": {"puid": ["fmt/505"]},
        "source_records": [
            {"source_id": "pronom_registry", "source_record_id": "fmt/505"}
        ],
    }
    reader = FakeReader([
        {
            "source_id": "pronom_registry",
            "source_record_id": "fmt/505",
            "raw": {
                "record": {
                    "version": "8",
                    "internalSignatures": [
                        {"name": "SWF 8"},
                        {"name": "SWF 8 - zlib compressed"},
                    ],
                }
            },
        }
    ])

    enriched = _ai_format_context(reader, format_doc)

    assert enriched["version"] == "8"
    assert enriched["internal_signature_names"] == [
        "SWF 8",
        "SWF 8 - zlib compressed",
    ]
