from preservation_risk_manager.cli import build_parser


def test_analyze_format_ai_defaults_to_fill_gaps():
    args = build_parser().parse_args([
        "analyze-format-ai",
        "--framework", "framework.json",
        "--storage-config", "storage.json",
        "--format", "fmt-pdf",
        "--ai-config", "ai.json",
    ])

    assert args.ai_mode == "fill-gaps"


def test_analyze_format_ai_accepts_review_all():
    args = build_parser().parse_args([
        "analyze-format-ai",
        "--framework", "framework.json",
        "--storage-config", "storage.json",
        "--format", "fmt-pdf",
        "--ai-config", "ai.json",
        "--ai-mode", "review-all",
    ])

    assert args.ai_mode == "review-all"
