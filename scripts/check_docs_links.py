from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "work",
    "output",
    "out",
    "monitoring-reports",
    "web-jobs",
}
EXTERNAL_PREFIXES = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
    "data:",
)


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.md")
        if not any(part in SKIP_DIRS for part in path.parts)
    )


def local_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if not target or target.startswith("#") or target.lower().startswith(EXTERNAL_PREFIXES):
        return None

    # Markdown permits an optional title after the URL. This repository uses
    # simple paths; handle the common '<path>' form and otherwise take the URL
    # token before an optional quoted title.
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    elif " \"" in target:
        target = target.split(" \"", 1)[0]
    elif " '" in target:
        target = target.split(" '", 1)[0]

    target = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not target:
        return None
    return unquote(target)


def check(root: Path) -> list[str]:
    errors: list[str] = []
    for document in markdown_files(root):
        text = document.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in LINK_RE.finditer(line):
                target = local_target(match.group(1))
                if target is None:
                    continue
                candidate = (document.parent / target).resolve(strict=False)
                try:
                    candidate.relative_to(root)
                except ValueError:
                    errors.append(
                        f"{document.relative_to(root)}:{line_number}: link escapes repository: {target}"
                    )
                    continue
                if not candidate.exists():
                    errors.append(
                        f"{document.relative_to(root)}:{line_number}: missing target: {target}"
                    )
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = check(root)
    if errors:
        print(f"Documentation link check failed: {len(errors)} broken local link(s).", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    count = len(markdown_files(root))
    print(f"Documentation link check passed for {count} Markdown files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
