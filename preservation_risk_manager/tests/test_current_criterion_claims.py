from preservation_risk_manager.data_access import RegistryReader


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def query(self, collection, filt=None):
        if collection != "criterion_claims":
            return []
        filt = filt or {}
        return [
            row for row in self.rows
            if all(row.get(key) == value for key, value in filt.items())
        ]


def test_superseded_criterion_claims_are_not_scoring_evidence():
    reader = RegistryReader(store=FakeStore([
        {
            "canonical_id": "puid-fmt-14",
            "criterion_id": "sustainability.adoption",
            "value": "low",
            "source_id": "old-source",
            "mapping_rule_id": "adoption-v1",
            "current": False,
        },
        {
            "canonical_id": "puid-fmt-14",
            "criterion_id": "sustainability.adoption",
            "value": "high",
            "source_id": "loc_fdd_xml",
            "mapping_rule_id": "adoption-v1",
            "current": True,
        },
    ]))

    claims = reader.get_criterion_claims(canonical_id="puid-fmt-14")

    assert len(claims) == 1
    assert claims[0]["source_id"] == "loc_fdd_xml"
    assert claims[0]["value"] == "high"


def test_legacy_claim_without_current_flag_remains_current():
    reader = RegistryReader(store=FakeStore([
        {
            "canonical_id": "puid-fmt-14",
            "criterion_id": "sustainability.disclosure",
            "value": "public_specification",
            "source_id": "legacy",
        }
    ]))

    claims = reader.get_criterion_claims(canonical_id="puid-fmt-14")

    assert len(claims) == 1
    assert claims[0]["source_id"] == "legacy"
