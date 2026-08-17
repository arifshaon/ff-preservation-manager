from preservation_risk_manager.request_api import _format_identity


def test_format_identity_reads_canonical_identifier_buckets():
    identity = _format_identity({
        "canonical_id": "puid-fmt-505",
        "preferred_name": "Adobe Flash",
        "identifiers": {
            "puid": ["fmt/505"],
            "loc": ["fdd000248"],
            "extension": ["swf"],
            "mime": ["application/x-shockwave-flash"],
        },
    })

    assert identity["puids"] == ["fmt/505"]
    assert identity["loc_ids"] == ["fdd000248"]
    assert identity["extensions"] == ["swf"]
    assert identity["mime_types"] == ["application/x-shockwave-flash"]
