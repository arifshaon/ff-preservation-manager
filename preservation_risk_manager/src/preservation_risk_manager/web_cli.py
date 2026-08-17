from __future__ import annotations

import argparse
from pathlib import Path
import threading
import webbrowser

from preservation_risk_manager.web_service import WebRuntimeConfig


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m preservation_risk_manager web",
        description="Run the local QNL Preservation Risk Manager web interface.",
    )
    parser.add_argument("--framework", required=True, help="Path to the preservation-risk framework JSON.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--storage-config", help="Path to registry-builder storage configuration (for example MongoDB).")
    source.add_argument("--registry-json", help="Path to a registry JSON export.")
    parser.add_argument("--ai-config", help="Path to AI provider configuration. Required for human AI features or batch fill-gaps.")
    parser.add_argument("--jobs-dir", default="web-jobs", help="Directory for job metadata and downloadable reports. Default: web-jobs")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port. Default: 8080")
    parser.add_argument("--workers", type=int, default=2, help="Background job worker threads. Default: 2")
    parser.add_argument("--batch-max-formats", type=int, default=5000, help="Maximum distinct IDs accepted in one batch. Default: 5000")
    parser.add_argument("--default-institution", help="Default institution ID used when Institution scope is selected.")
    parser.add_argument("--max-ai-evidence-items", type=int, default=20, help="Maximum evidence items supplied per AI framework question. Default: 20")
    parser.add_argument("--open-browser", action="store_true", help="Open the local UI in the default browser after startup.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.port <= 0 or args.port > 65535:
        raise SystemExit("--port must be between 1 and 65535")
    if args.workers <= 0:
        raise SystemExit("--workers must be greater than zero")
    if args.batch_max_formats <= 0:
        raise SystemExit("--batch-max-formats must be greater than zero")
    if args.max_ai_evidence_items <= 0:
        raise SystemExit("--max-ai-evidence-items must be greater than zero")

    config = WebRuntimeConfig(
        framework=str(Path(args.framework).expanduser()),
        storage_config=str(Path(args.storage_config).expanduser()) if args.storage_config else None,
        registry_json=str(Path(args.registry_json).expanduser()) if args.registry_json else None,
        ai_config=str(Path(args.ai_config).expanduser()) if args.ai_config else None,
        jobs_dir=str(Path(args.jobs_dir).expanduser()),
        default_institution_id=args.default_institution,
        max_workers=args.workers,
        batch_max_formats=args.batch_max_formats,
        max_ai_evidence_items=args.max_ai_evidence_items,
    )
    config.validate()

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Web dependencies are not installed. Run: python -m pip install -e \".[web]\""
        ) from exc

    from preservation_risk_manager.web_app import create_app

    app = create_app(config)
    url = f"http://{'127.0.0.1' if args.host in {'0.0.0.0', '::'} else args.host}:{args.port}/"
    print(f"QNL Preservation Risk Manager web UI: {url}", flush=True)
    print(f"Job/report directory: {Path(config.jobs_dir).resolve()}", flush=True)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("WARNING: this development UI has no built-in authentication; use an authenticated reverse proxy before network exposure.", flush=True)
    if args.open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0
