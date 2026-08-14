from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Any
from urllib.request import Request, urlopen


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slugify(text: str, max_len: int = 80) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len].strip("-") or "unnamed"


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_uri(uri: str, user_agent: str = "QNL-Format-Registry-Builder/0.1") -> tuple[bytes, dict[str, str]]:
    if uri.startswith("http://") or uri.startswith("https://"):
        req = Request(uri, headers={"User-Agent": user_agent})
        with urlopen(req, timeout=60) as resp:
            return resp.read(), {k.lower(): v for k, v in resp.headers.items()}
    path = Path(uri)
    return path.read_bytes(), {}


def write_json(path: str | Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: str | Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def split_multi(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        parts = value
    else:
        text = str(value).strip()
        if not text:
            return []
        parts = re.split(r"[;,|\n]+", text)
    out: list[str] = []
    for p in parts:
        s = str(p).strip()
        if s:
            out.append(s)
    return out


def normalize_extension(value: str) -> str:
    value = value.strip().lower()
    value = value.lstrip(".")
    value = re.sub(r"\s+", "", value)
    return value


def normalize_mime(value: str) -> str:
    return value.strip().lower()


def normalize_identifier(value: str) -> str:
    return value.strip()
