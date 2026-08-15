import json

from registry_builder.__main__ import main
from registry_builder.models import CanonicalFormat


def test_collision_report_cli_outputs_review_json(tmp_path, monkeypatch, capsys):
    fmt = CanonicalFormat(canonical_id="puid-fmt-18", preferred_name="Portable Document Format")
    fmt.add_identifier("puid", "fmt/18", source="pronom_droid_xml", verified=True)
    fmt.add_identifier(
        "puid",
        "fmt/18",
        source="institution_policy_xlsx",
        verified=False,
        confidence="heuristic",
        confidence_reason="Only one side carries an explicit version discriminator.",
    )
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps([fmt.to_dict()]), encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["registry-builder", "collision-report", "--registry", str(registry_path)])

    main()

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "review"
    assert output["summary"]["heuristic_identifier_bridges"] == 1
    assert output["heuristic_identifier_bridges"][0]["canonical_id"] == "puid-fmt-18"
