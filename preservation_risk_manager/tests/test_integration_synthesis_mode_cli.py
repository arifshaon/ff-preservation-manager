from __future__ import annotations

import preservation_risk_manager.integration_cli as integration_cli


def test_query_json_accepts_synthesis_only_ai_mode():
    args = integration_cli._build_parser().parse_args([
        "query-json",
        "--framework", "framework.json",
        "--registry-json", "registry.json",
        "--request", "request.json",
        "--ai-config", "ai.json",
        "--ai-mode", "synthesize",
    ])

    assert args.ai_mode == "synthesize"
    assert args.ai_config == "ai.json"
    assert args.max_ai_evidence_items == 20
