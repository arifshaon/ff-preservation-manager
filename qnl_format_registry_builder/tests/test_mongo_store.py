from registry_builder.storage.mongo import _mongo_safe


def test_mongo_safe_sanitizes_nested_keys_with_dots_and_dollars():
    record = {
        "raw": {
            "docs.fileformat.com": "https://example.org",
            "$schema": "value",
            "nested": [{"a.b": 1}],
        }
    }

    safe = _mongo_safe(record)

    assert "docs．fileformat．com" in safe["raw"]
    assert "＄schema" in safe["raw"]
    assert "a．b" in safe["raw"]["nested"][0]
