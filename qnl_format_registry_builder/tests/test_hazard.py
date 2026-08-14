from registry_builder.hazard import reconcile_hazard


def test_reconcile_corroborated():
    result = reconcile_hazard(2.0, 2.2, divergence_threshold=0.5)
    assert result["basis"] == "corroborated"
    assert result["confidence"] == "high"
    assert result["review_required"] is False


def test_reconcile_divergence_surfaces_review():
    result = reconcile_hazard(1.0, 3.0, divergence_threshold=0.5)
    assert result["basis"] == "qnl_override"
    assert result["divergence_flag"] is True
    assert result["review_required"] is True


def test_no_estimator_is_not_a_risk_band():
    result = reconcile_hazard(None, None)
    assert result["assessed"] is False
    assert result["band"] is None
    assert result["review_required"] is True
