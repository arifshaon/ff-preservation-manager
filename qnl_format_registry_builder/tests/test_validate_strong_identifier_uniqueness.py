from registry_builder.models import CanonicalFormat
from registry_builder.validate import validate_registry


def test_duplicate_puid_across_canonical_records_is_validation_error():
    left = CanonicalFormat(canonical_id="puid-fmt-14", preferred_name="PDF 1.0")
    right = CanonicalFormat(canonical_id="loc-fdd000316", preferred_name="PDF versions 1.0-1.3")
    left.add_identifier("puid", "fmt/14", source="pronom", verified=True)
    right.add_identifier("puid", "fmt/14", source="loc", verified=False)

    errors, _warnings = validate_registry([left, right])

    assert any("strong identifier puid:fmt/14 appears in multiple canonical records" in error for error in errors)
