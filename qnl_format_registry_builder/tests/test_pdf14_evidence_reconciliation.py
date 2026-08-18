from pathlib import Path

from registry_builder.criteria import load_criteria
from registry_builder.criterion_mapping import build_criterion_claims, load_mappings
from registry_builder.models import RawFormatRecord
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile


ROOT = Path(__file__).resolve().parents[1]


def test_pdf10_combines_approved_nara_and_loc_evidence_on_pronom_puid():
    records = [
        RawFormatRecord(
            source_id="pronom_registry",
            source_type="pronom_registry",
            source_record_id="fmt/14",
            name="Acrobat PDF 1.0 - Portable Document Format",
            extensions=["pdf"],
            mime_types=["application/pdf"],
            puids=["fmt/14"],
            version="1.0",
        ),
        RawFormatRecord(
            source_id="nara_digital_preservation_framework",
            source_type="nara_digital_preservation_framework",
            source_record_id="NF00362",
            name="Portable Document Format (PDF) version 1.0",
            extensions=["pdf"],
            mime_types=["application/pdf"],
            puids=["fmt/14"],
            loc_ids=["fdd000316"],
            nara_ids=["NF00362"],
            raw={
                "row": {
                    "1．2: Does the format have a published open specification?": 2,
                    "3．2: Is there an internal signature in an authoritative format registry that can be used to identify a file in this format?": 2,
                    "6．1: Are renderers available?": 2,
                    "8．3: Does the format natively allow the use of technical protection measures (e.g. digital rights management)?": -2,
                }
            },
        ),
        RawFormatRecord(
            source_id="loc_fdd_xml",
            source_type="loc_fdd_xml",
            source_record_id="fdd000316",
            name="PDF_1_3, PDF Versions 1.0-1.3",
            extensions=["pdf"],
            puids=["fmt/14", "fmt/15", "fmt/16", "fmt/17"],
            loc_ids=["fdd000316"],
            native_fields={
                "sustainability_factors": {
                    "disclosure": "Fully documented with a publicly available specification.",
                    "adoption": "Widely adopted and widely used.",
                    "external_dependencies": "None.",
                }
            },
        ),
        *[
            RawFormatRecord(
                source_id="pronom_registry",
                source_type="pronom_registry",
                source_record_id=f"fmt/{number}",
                name=f"Acrobat PDF {version}",
                extensions=["pdf"],
                puids=[f"fmt/{number}"],
                version=version,
            )
            for number, version in ((15, "1.1"), (16, "1.2"), (17, "1.3"))
        ],
    ]
    normalized = [normalize_record(record) for record in records]
    registry = reconcile(normalized)
    canonical = [item.to_dict() for item in registry]

    pdf10 = next(item for item in canonical if item["canonical_id"] == "puid-fmt-14")
    assert pdf10["identifiers"]["puid"] == ["fmt/14"]
    assert pdf10["identifiers"]["nara"] == ["NF00362"]
    assert any(ref.get("source_record_id") == "fdd000316" for ref in pdf10["source_records"])

    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    mappings = load_mappings(ROOT / "config" / "criterion_mappings")
    claims = build_criterion_claims(
        canonical,
        [record.to_dict() for record in normalized],
        mappings,
        criteria,
        include_drafts=False,
    )
    pdf_claims = [claim for claim in claims if claim["canonical_id"] == "puid-fmt-14"]

    by_criterion = {}
    for claim in pdf_claims:
        by_criterion.setdefault(claim["criterion_id"], []).append(claim)

    assert "sustainability.disclosure" in by_criterion
    assert "sustainability.adoption" in by_criterion
    assert "sustainability.external_dependencies" in by_criterion
    assert any(claim["source_id"] == "nara_digital_preservation_framework" for claim in by_criterion["sustainability.disclosure"])
    assert any(claim["source_id"] == "loc_fdd_xml" and claim["value"] == "high" for claim in by_criterion["sustainability.adoption"])
    assert any(claim["source_id"] == "loc_fdd_xml" and claim["value"] == "none" for claim in by_criterion["sustainability.external_dependencies"])
