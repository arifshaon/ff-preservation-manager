from __future__ import annotations

import json
import math

import pytest

from preservation_risk_manager.cli import main
from preservation_risk_manager.composite_risk import (
    SEVEN_CRITERIA,
    CompositeRiskConfig,
    CompositeRiskError,
    compute_composite_risk,
    load_composite_risk_config,
    nara_baseline,
    spec_age_years,
    sustainability_score,
)


def _claim(criterion, value):
    return {"criterion_id": criterion, "value": value}


def _format(band=None, canonical_id="fmt-x"):
    doc = {"canonical_id": canonical_id, "preferred_name": "X", "current": True}
    if band is not None:
        doc["hazard_assessment"] = {
            "assessed": True,
            "band": band,
            "external_rating_native_scale": "nara_file_format_risk_matrix",
        }
    return doc


# --- formula --------------------------------------------------------------


def test_blueprint_formula_reproduced_exactly():
    """R = min(100, 100*[g1*R_NARA + g2*(1-S_LoC) + a*ln(1+A_spec)*(1.5-E_tool)])."""
    claims = [
        _claim("sustainability.disclosure", "undocumented"),        # 0.0
        _claim("sustainability.adoption", "low"),                   # 0.2
        _claim("source.currency", 10 * 365.25),                     # 10 years
    ]
    result = compute_composite_risk(_format("High"), claims, e_tool=0.0)
    s_loc = 0.1  # equal weights over the two evidenced criteria
    expected = min(100.0, 100.0 * (
        0.45 * 0.9 + 0.55 * (1 - s_loc) + 0.08 * math.log(1 + 10.0) * 1.5
    ))
    assert result["composite_score"] == round(expected, 2)
    assert result["inputs"]["sustainability"]["s_loc"] == s_loc
    assert result["risk_tier"] == "High"


def test_nara_band_mapping_low_moderate_high():
    for band, value in (("Low", 0.2), ("Moderate", 0.5), ("High", 0.9)):
        assert nara_baseline(_format(band))["r_nara"] == value


def test_score_is_capped_at_100():
    claims = [
        _claim("sustainability.disclosure", "undocumented"),
        _claim("sustainability.tpm_encryption", "known_constraint"),
        _claim("source.currency", 40 * 365.25),
    ]
    result = compute_composite_risk(_format("High"), claims, e_tool=0.0)
    assert result["composite_score"] == 100.0


def test_missing_age_and_tooling_terms_degrade_gracefully():
    claims = [
        _claim("sustainability.disclosure", "public_specification"),
        _claim("sustainability.adoption", "very_high"),
    ]
    result = compute_composite_risk(_format("Low"), claims)
    assert result["terms"]["temporal_term"] == 0.0
    assert "specification_age" in result["missing_inputs"]
    assert result["inputs"]["tooling"]["source"] == "default_neutral_no_fpr_source"
    assert result["risk_tier"] == "Low"


# --- sustainability aggregation -------------------------------------------


def test_conflicting_claims_take_the_most_conservative_score():
    claims = [
        _claim("sustainability.disclosure", "public_specification"),  # 1.0
        _claim("sustainability.disclosure", "undocumented"),          # 0.0
    ]
    result = sustainability_score(claims, CompositeRiskConfig())
    assert result["per_criterion"]["sustainability.disclosure"]["score"] == 0.0


def test_unmapped_values_leave_criterion_unevidenced_and_audited():
    claims = [_claim("sustainability.disclosure", "unknown")]
    result = sustainability_score(claims, CompositeRiskConfig())
    assert result["s_loc"] is None
    assert "sustainability.disclosure" in result["unevidenced_criteria"]
    audit = result["per_criterion"]["sustainability.disclosure"]
    assert audit["unmapped_values"] == ["unknown"]


def test_weights_renormalize_over_evidenced_criteria():
    config = CompositeRiskConfig(weights={
        "sustainability.disclosure": 0.9,
        "sustainability.adoption": 0.1,
    })
    claims = [
        _claim("sustainability.disclosure", "public_specification"),  # 1.0
        _claim("sustainability.adoption", "low"),                     # 0.2
    ]
    result = sustainability_score(claims, config)
    assert result["s_loc"] == round((0.9 * 1.0 + 0.1 * 0.2) / 1.0, 4)


# --- governance -----------------------------------------------------------


def test_tier_suppressed_without_nara_baseline():
    claims = [
        _claim("sustainability.disclosure", "undocumented"),
        _claim("sustainability.adoption", "low"),
    ]
    result = compute_composite_risk(_format(), claims)
    assert result["composite_score"] is not None
    assert result["risk_tier"] is None
    assert "nara_baseline_missing" in result["tier_suppressed_reasons"]


def test_tier_suppressed_below_coverage_floor():
    claims = [_claim("sustainability.disclosure", "undocumented")]
    result = compute_composite_risk(_format("Moderate"), claims)
    assert result["risk_tier"] is None
    assert any("coverage_below_minimum" in r for r in result["tier_suppressed_reasons"])


def test_no_signal_at_all_is_not_computable():
    result = compute_composite_risk(_format(), [_claim("source.currency", 100)])
    assert result["status"] == "not_computable"
    assert "composite_score" not in result


def test_nara_band_found_on_related_sibling_record_conservatively():
    primary = _format(canonical_id="puid-fmt-1")
    siblings = [
        _format("Low", canonical_id="loc-fdd000001"),
        _format("High", canonical_id="nara-nf00001"),
    ]
    result = nara_baseline(primary, siblings)
    assert result["band"] == "High"
    assert result["from_canonical_id"] == "nara-nf00001"


def test_spec_age_uses_most_recent_currency_claim():
    claims = [_claim("source.currency", 3000), _claim("source.currency", 365.25)]
    assert spec_age_years(claims)["a_spec_years"] == 1.0


# --- configuration --------------------------------------------------------


def test_config_rejects_invalid_bounds_and_weights():
    with pytest.raises(CompositeRiskError):
        CompositeRiskConfig(low_max=70, high_min=65)
    with pytest.raises(CompositeRiskError):
        CompositeRiskConfig(weights={"not.a.criterion": 1.0})
    with pytest.raises(CompositeRiskError):
        compute_composite_risk(_format("Low"), [], e_tool=1.5)


def test_config_loads_overrides_from_json(tmp_path):
    path = tmp_path / "risk.json"
    path.write_text(json.dumps({
        "gamma1": 0.5, "gamma2": 0.5, "high_min": 70,
        "weights": {"sustainability.disclosure": 0.5},
    }))
    config = load_composite_risk_config(path)
    assert config.gamma1 == 0.5
    assert config.high_min == 70
    assert config.weight_for("sustainability.disclosure") == 0.5
    # Unlisted criteria keep the equal-share default weight.
    assert config.weight_for("sustainability.adoption") == pytest.approx(1 / 7)


# --- CLI ------------------------------------------------------------------


def test_cli_composite_risk_end_to_end(tmp_path, capsys):
    registry = {
        "canonical_formats": [{
            **_format("Moderate", canonical_id="fmt-demo"),
            "preferred_name": "Demo Format",
        }],
        "criterion_claims": [
            {"canonical_id": "fmt-demo", "criterion_id": "sustainability.disclosure",
             "value": "undocumented", "source_id": "s", "source_record_id": "1", "current": True},
            {"canonical_id": "fmt-demo", "criterion_id": "sustainability.adoption",
             "value": "low", "source_id": "s", "source_record_id": "2", "current": True},
            {"canonical_id": "fmt-demo", "criterion_id": "source.currency",
             "value": 3652.5, "source_id": "s", "source_record_id": "3", "current": True},
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry))
    exit_code = main(["composite-risk", "--registry-json", str(path), "--format", "fmt-demo"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assessment = payload["composite_risk"]
    assert assessment["risk_tier"] in {"Moderate", "High"}
    assert assessment["inputs"]["nara"]["band"] == "Moderate"
    assert "authority_note" in assessment


def test_cli_reports_unresolved_format(tmp_path, capsys):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"canonical_formats": []}))
    exit_code = main(["composite-risk", "--registry-json", str(path), "--format", "nope"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "not_found"
