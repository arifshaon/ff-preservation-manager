from pathlib import Path

from registry_builder.criteria import load_criteria
from registry_builder.criterion_mapping import build_criterion_claims, load_mapping
from registry_builder.models import RawFormatRecord
from registry_builder.normalize import normalize_record
from registry_builder.reconcile import reconcile


ROOT = Path(__file__).resolve().parents[1]
MAPPING_DIR = ROOT / "config" / "criterion_mappings"


def test_pdf10_uses_exact_nara_evidence_and_keeps_loc_range_as_relationship_only():
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
                    "5．1: Does the format require a specific hardware environment, such as a specific graphics card, chipset, or memory requirements, to process or interact with it?": 2,
                    "5．2: Does the format require specific playback hardware (e．g．, Blu-Ray, Audio CD, etc) to transfer the format to the NARA environment?": 2,
                    "6．1: Are renderers available?": 2,
                    "6．3: Does the format rely on plug-ins and/or scripts, etc． to render or execute files?": 2,
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
                    "adoption": "PDF 1.3 has been very widely used.",
                    "external_dependencies": "See PDF_family.",
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
    loc_ref = next(ref for ref in pdf10["source_records"] if ref.get("source_record_id") == "fdd000316")
    assert loc_ref["relationship"] == "explicit_puid_cross_reference"
    assert loc_ref["evidence_scope"] == "multi_puid_source_record"

    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    mappings = [
        load_mapping(MAPPING_DIR / "pronom_registry.v1.approved.json"),
        load_mapping(MAPPING_DIR / "nara_digital_preservation_framework.v1.approved.json"),
        load_mapping(MAPPING_DIR / "loc_fdd_xml.v1.approved.json"),
    ]
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

    # Exact NARA observations remain usable for the exact PUID.
    assert any(
        claim["source_id"] == "nara_digital_preservation_framework"
        and claim["value"] == "public_specification"
        for claim in by_criterion["sustainability.disclosure"]
    )
    assert [claim["value"] for claim in by_criterion["technical.hardware_dependency"]] == ["none", "none"]
    assert [claim["value"] for claim in by_criterion["technical.plugin_script_dependency"]] == ["none"]

    # The LOC range record remains linked for provenance/AI, but its criterion
    # prose must not automatically become deterministic evidence for PDF 1.0.
    assert not any(claim["source_id"] == "loc_fdd_xml" for claim in pdf_claims)
    assert "sustainability.adoption" not in by_criterion
    assert "sustainability.external_dependencies" not in by_criterion
