from pathlib import Path

from registry_builder.criteria import load_criteria
from registry_builder.criterion_mapping import build_criterion_claims, load_mapping


ROOT = Path(__file__).resolve().parents[1]


def test_approved_nara_mapping_produces_exact_dependency_claims_for_pdf_10():
    criteria = load_criteria(ROOT / "config" / "criteria" / "v1.json")
    mapping = load_mapping(
        ROOT / "config" / "criterion_mappings" / "nara_digital_preservation_framework.v1.approved.json"
    )
    canonical = [{
        "canonical_id": "puid-fmt-14",
        "preferred_name": "Acrobat PDF 1.0 - Portable Document Format",
        "identifiers": {"puid": ["fmt/14"], "nara": ["NF00362"]},
        "source_records": [{
            "source_id": "nara_digital_preservation_framework",
            "source_type": "nara_digital_preservation_framework",
            "source_record_id": "NF00362",
        }],
    }]
    source_records = [{
        "source_id": "nara_digital_preservation_framework",
        "source_type": "nara_digital_preservation_framework",
        "source_record_id": "NF00362",
        "raw": {
            "row": {
                "5．1: Does the format require a specific hardware environment, such as a specific graphics card, chipset, or memory requirements, to process or interact with it?": "2",
                "5．2: Does the format require specific playback hardware (e．g．, Blu-Ray, Audio CD, etc) to transfer the format to the NARA environment?": "2",
                "6．3: Does the format rely on plug-ins and/or scripts, etc． to render or execute files?": "2",
            }
        },
    }]

    claims = build_criterion_claims(canonical, source_records, [mapping], criteria)
    dependency_claims = [
        (claim["criterion_id"], claim["value"], claim["mapping_rule_id"])
        for claim in claims
        if claim["criterion_id"] in {
            "technical.hardware_dependency",
            "technical.plugin_script_dependency",
        }
    ]

    assert dependency_claims == [
        (
            "technical.hardware_dependency",
            "none",
            "nara.rubric.5_1.technical_hardware_dependency.v1",
        ),
        (
            "technical.hardware_dependency",
            "none",
            "nara.rubric.5_2.technical_hardware_dependency.v1",
        ),
        (
            "technical.plugin_script_dependency",
            "none",
            "nara.rubric.6_3.technical_plugin_script_dependency.v1",
        ),
    ]
