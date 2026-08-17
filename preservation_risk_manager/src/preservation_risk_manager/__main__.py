from __future__ import annotations

import sys

from preservation_risk_manager.cli import main as legacy_main
from preservation_risk_manager.integration_cli import main as integration_main


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] in {"ask", "query-json"}:
        raise SystemExit(integration_main(argv))
    raise SystemExit(legacy_main(argv))
