from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from registry_builder.models import RawFormatRecord, SourceSnapshot, snapshot_currency, utc_now_iso
from registry_builder.utils import ensure_dir, read_uri, sha256_bytes

logger = logging.getLogger(__name__)

# Exceptions that mean "the source is unreachable right now", as opposed to a
# bug: HTTP 404/503, DNS failure, connection reset, timeout. These trigger the
# local/cache fallbacks instead of aborting the run.
NETWORK_ERRORS = (HTTPError, URLError, TimeoutError, ConnectionError)

# Metadata keys that are lifted onto first-class SourceSnapshot fields. They are
# also kept inside metadata so the snapshot index persists them and cache replay
# can recover them.
_PROVENANCE_KEYS = ("acquisition_mode", "source_published_at", "edition")

# Files an input inbox may contain that are not source material.
_INBOX_IGNORED_NAMES = {"readme.md", "readme.txt", "manifest.json"}


def _http_date_to_iso(value: str | None) -> str | None:
    if not value:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return None


def describe_network_error(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        return f"http_{exc.code}"
    return f"{type(exc).__name__}: {exc}"


class SourceAdapter(ABC):
    type_name: str = "base"
    # Whether this adapter reads administrator-dropped files from
    # input/<source_id>/. True automatically for adapters using the base
    # acquire(); adapters that override acquire() must opt in explicitly after
    # wiring the inbox through, otherwise init-source-inbox would create a
    # folder whose contents are silently ignored.
    supports_input_dir: bool | None = None
    # One or two sentences for the generated inbox README saying what to drop.
    inbox_hint: str = "Drop this source's data files here."

    @classmethod
    def reads_input_dir(cls) -> bool:
        if cls.supports_input_dir is not None:
            return bool(cls.supports_input_dir)
        return cls.acquire is SourceAdapter.acquire

    def __init__(self, source_config: dict[str, Any], workdir: Path):
        self.config = source_config
        self.workdir = workdir
        self.source_id = source_config["id"]

    @property
    def offline(self) -> bool:
        return bool(self.config.get("offline", False))

    def snapshot_dir(self) -> Path:
        return ensure_dir(self.workdir / "snapshots" / self.source_id)

    def _snapshot_index_path(self) -> Path:
        return self.snapshot_dir() / ".snapshot_index.json"

    def _load_snapshot_index(self) -> dict[str, dict[str, Any]]:
        path = self._snapshot_index_path()
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_snapshot_index(self, index: dict[str, dict[str, Any]]) -> None:
        path = self._snapshot_index_path()
        path.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _cached_snapshot(
        self,
        *,
        uri: str,
        suffix: str,
        note: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SourceSnapshot | None:
        index = self._load_snapshot_index()
        entry = index.get(uri)
        if not entry:
            return None
        local_path = Path(entry.get("local_path", ""))
        if not local_path.exists():
            return None
        cached_metadata = dict(entry.get("metadata") or {})
        if metadata:
            cached_metadata.update(metadata)
        return SourceSnapshot(
            source_id=self.source_id,
            source_type=self.type_name,
            uri=uri,
            acquired_at=entry.get("acquired_at") or utc_now_iso(),
            sha256=entry.get("sha256", ""),
            local_path=str(local_path),
            content_type=entry.get("content_type") or content_type,
            note="; ".join(x for x in [note, "cache=hit", "offline=true" if self.offline else "reused=true"] if x),
            changed=False,
            from_cache=True,
            metadata=cached_metadata,
            acquisition_mode="cache",
            source_published_at=cached_metadata.get("source_published_at"),
            edition=cached_metadata.get("edition"),
        )

    def _store_snapshot_bytes(
        self,
        *,
        index_key: str,
        uri: str,
        data: bytes,
        suffix: str,
        note: str | None,
        content_type: str | None,
        metadata: dict[str, Any],
    ) -> SourceSnapshot:
        digest = sha256_bytes(data)
        index = self._load_snapshot_index()
        previous = index.get(index_key)
        changed = previous is None or previous.get("sha256") != digest
        suffix = suffix if suffix.startswith(".") else f".{suffix}"
        local_path = self.snapshot_dir() / f"{digest}{suffix}"
        if not local_path.exists() or sha256_bytes(local_path.read_bytes()) != digest:
            local_path.write_bytes(data)

        acquired_at = utc_now_iso()
        index[index_key] = {
            "uri": uri,
            "sha256": digest,
            "local_path": str(local_path),
            "content_type": content_type,
            "acquired_at": acquired_at,
            "source_type": self.type_name,
            "metadata": metadata,
        }
        self._write_snapshot_index(index)
        return SourceSnapshot(
            source_id=self.source_id,
            source_type=self.type_name,
            uri=uri,
            acquired_at=acquired_at,
            sha256=digest,
            local_path=str(local_path),
            content_type=content_type,
            note="; ".join(x for x in [note, "changed=true" if changed else "changed=false"] if x),
            changed=changed,
            from_cache=False,
            metadata=metadata,
            acquisition_mode=metadata.get("acquisition_mode"),
            source_published_at=metadata.get("source_published_at"),
            edition=metadata.get("edition"),
        )

    def acquire_file_snapshot(
        self,
        file_path: str | Path,
        *,
        suffix: str | None = None,
        note: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SourceSnapshot:
        """Acquire an administrator-supplied local source file.

        This is distinct from offline cache replay. Offline mode reads previously
        cached snapshots without touching the original source. Local-file mode
        treats the supplied file itself as the source material, snapshots it into
        the content-addressed cache, and reports whether that local file changed
        since the previous run.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Local source file not found for {self.source_id}: {path}")
        data = path.read_bytes()
        metadata = dict(metadata or {})
        metadata.setdefault("source_location", "local_file")
        metadata.setdefault("local_source_path", str(path))
        metadata.setdefault("acquisition_mode", "local")
        suffix = suffix or path.suffix or ".dat"
        index_key = f"file://{path.resolve()}"
        return self._store_snapshot_bytes(
            index_key=index_key,
            uri=str(path),
            data=data,
            suffix=suffix,
            note="; ".join(x for x in [note, "source_location=local_file"] if x),
            content_type=None,
            metadata=metadata,
        )

    def acquire_uri_snapshot(
        self,
        uri: str,
        *,
        suffix: str,
        note: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SourceSnapshot:
        """Acquire one URI as a content-addressed source snapshot.

        Online mode still checks the upstream source, but it no longer rewrites an
        unchanged cached snapshot. Offline mode uses the source snapshot index and
        fails loudly if the requested URI has not been cached before.
        """
        metadata = dict(metadata or {})
        if self.offline:
            cached = self._cached_snapshot(uri=uri, suffix=suffix, note=note, metadata=metadata)
            if cached:
                return cached
            raise FileNotFoundError(
                f"Offline mode requested but no cached snapshot index entry exists for {self.source_id}: {uri}"
            )

        data, headers = read_uri(uri)
        metadata.setdefault("acquisition_mode", "network")
        last_modified = _http_date_to_iso(headers.get("last-modified"))
        if last_modified and not metadata.get("source_published_at"):
            metadata["source_published_at"] = last_modified
            metadata["source_published_at_basis"] = "http_last_modified"
        return self._store_snapshot_bytes(
            index_key=uri,
            uri=uri,
            data=data,
            suffix=suffix,
            note=note,
            content_type=headers.get("content-type"),
            metadata=metadata,
        )

    def acquire_uri_snapshots(
        self,
        uris: list[str],
        *,
        suffix: str,
        note: str | None = None,
        metadata_by_uri: dict[str, dict[str, Any]] | None = None,
    ) -> list[SourceSnapshot]:
        metadata_by_uri = metadata_by_uri or {}
        return [
            self.acquire_uri_snapshot(
                uri,
                suffix=suffix,
                note=note,
                metadata=metadata_by_uri.get(uri),
            )
            for uri in uris
        ]

    # ------------------------------------------------------------------
    # Acquisition policy
    #
    # The default acquire() implements one convention for every source:
    #
    #   1. If administrator-dropped files exist in input/<source_id>/, use them
    #      and do NOT touch the network — a staged file is explicit intent.
    #   2. force_check_url: true opts back into a network fetch; if the network
    #      fails (404, 503, DNS, timeout) the run falls back to the local files
    #      and records why.
    #   3. With no local files, fetch from the network; on failure, replay the
    #      cached snapshots from the previous run and record why.
    #
    # Adapters migrated to this contract implement network_acquire() (what to
    # fetch) and optionally describe_local_file() (what a dropped filename
    # means). Legacy adapters keep overriding acquire() and are unaffected.
    # ------------------------------------------------------------------

    @property
    def acquisition_policy(self) -> str:
        """auto | local_only | network_only | cache_only (offline implies cache_only)."""
        policy = str(self.config.get("acquisition_policy") or "auto").strip().lower()
        if policy not in {"auto", "local_only", "network_only", "cache_only"}:
            raise ValueError(
                f"acquisition_policy for {self.source_id} must be auto/local_only/network_only/cache_only, got: {policy}"
            )
        if self.offline and policy in {"auto", "network_only"}:
            return "cache_only"
        return policy

    @property
    def force_check_url(self) -> bool:
        return bool(self.config.get("force_check_url", False))

    def input_dir(self) -> Path:
        """The designated drop folder for this source: <input_root>/<source_id>/."""
        explicit = self.config.get("input_dir")
        if explicit:
            return Path(explicit)
        return Path(self.config.get("input_root") or "input") / self.source_id

    def local_input_files(self) -> list[Path]:
        directory = self.input_dir()
        if not directory.is_dir():
            return []
        files = [
            path
            for path in sorted(directory.rglob("*"))
            if path.is_file()
            and not path.name.startswith(".")
            and path.name.lower() not in _INBOX_IGNORED_NAMES
            and not path.name.endswith(".meta.json")
        ]
        return files

    def _input_manifest(self) -> dict[str, Any]:
        """Optional manifest.json next to dropped files.

        {"published_at": ..., "edition": ..., "files": {"<name>": {...}}}
        Per-file sidecars <name>.meta.json take precedence over the manifest.
        """
        path = self.input_dir() / "manifest.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def describe_local_file(self, path: Path) -> dict[str, Any]:
        """Return provenance for a dropped file: kind/edition/source_published_at.

        The default consults the folder manifest and the file's sidecar. Adapters
        whose filenames are self-describing (e.g. NARA's dated CSVs) override
        this to infer without a manifest.
        """
        manifest = self._input_manifest()
        layers: list[dict[str, Any]] = [
            {key: manifest[key] for key in ("source_published_at", "edition", "published_at") if manifest.get(key)},
            dict((manifest.get("files") or {}).get(path.name) or {}),
        ]
        sidecar = path.with_name(path.name + ".meta.json")
        if sidecar.exists():
            layers.append(json.loads(sidecar.read_text(encoding="utf-8")))
        described: dict[str, Any] = {}
        # Later layers are more specific and win: sidecar > per-file > folder.
        # published_at inside any layer overrides an inherited
        # source_published_at from an earlier one, so normalise per layer.
        for layer in layers:
            layer = dict(layer)
            if "published_at" in layer:
                layer["source_published_at"] = layer.pop("published_at")
            described.update(layer)
        return described

    def network_acquire(self) -> list[SourceSnapshot]:
        raise NotImplementedError(
            f"{type(self).__name__} does not implement network_acquire(); "
            "it either overrides acquire() directly or only supports local input files"
        )

    def local_acquire(self, files: list[Path] | None = None, *, network_error: str | None = None) -> list[SourceSnapshot]:
        files = self.local_input_files() if files is None else files
        if not files:
            raise FileNotFoundError(
                f"No local input files for {self.source_id}; expected files under {self.input_dir()}"
            )
        snapshots: list[SourceSnapshot] = []
        for path in files:
            described = self.describe_local_file(path)
            metadata: dict[str, Any] = {
                "acquisition_mode": "local",
                "input_dir": str(self.input_dir()),
                **{k: v for k, v in described.items() if v is not None},
            }
            if network_error:
                metadata["network_error"] = network_error
                metadata["network_fallback"] = True
            snapshots.append(
                self.acquire_file_snapshot(
                    path,
                    note="; ".join(x for x in ["source_location=input_dir", f"network_error={network_error}" if network_error else None] if x),
                    metadata=metadata,
                )
            )
        return snapshots

    def _replay_cached_snapshots(self, *, network_error: str | None = None) -> list[SourceSnapshot]:
        """Replay every indexed snapshot for this source without touching the network."""
        snapshots: list[SourceSnapshot] = []
        extra = {"network_error": network_error, "network_fallback": True} if network_error else None
        for uri, entry in sorted(self._load_snapshot_index().items()):
            cached = self._cached_snapshot(uri=uri, suffix=Path(entry.get("local_path", "")).suffix or ".dat", metadata=extra)
            if cached:
                snapshots.append(cached)
        return snapshots

    def acquire(self) -> list[SourceSnapshot]:
        policy = self.acquisition_policy
        local_files = self.local_input_files()

        if policy == "local_only":
            snapshots = self.local_acquire(local_files)
        elif policy == "cache_only":
            snapshots = self._replay_cached_snapshots()
            if not snapshots:
                raise FileNotFoundError(
                    f"acquisition_policy cache_only (or offline) for {self.source_id} but no cached snapshots exist"
                )
        elif policy == "network_only":
            snapshots = self.network_acquire()
        elif local_files and not self.force_check_url:
            logger.info("%s: using %d local input file(s) from %s; network not contacted", self.source_id, len(local_files), self.input_dir())
            snapshots = self.local_acquire(local_files)
        else:
            try:
                snapshots = self.network_acquire()
            except NETWORK_ERRORS as exc:
                reason = describe_network_error(exc)
                if local_files:
                    logger.warning("%s: network fetch failed (%s); falling back to local input files", self.source_id, reason)
                    snapshots = self.local_acquire(local_files, network_error=reason)
                else:
                    cached = self._replay_cached_snapshots(network_error=reason)
                    if not cached:
                        raise
                    logger.warning("%s: network fetch failed (%s); replaying %d cached snapshot(s)", self.source_id, reason, len(cached))
                    snapshots = cached

        self._log_currency(snapshots)
        return snapshots

    def currency_report(self, snapshots: list[SourceSnapshot]) -> list[dict[str, Any]]:
        return [snapshot_currency(snapshot) for snapshot in snapshots]

    def _log_currency(self, snapshots: list[SourceSnapshot]) -> None:
        for entry in self.currency_report(snapshots):
            published = (
                f"published {entry['source_published_at']} ({entry['published_age_days']} day(s) old)"
                if entry.get("source_published_at")
                else "publication date unknown"
            )
            logger.info(
                "%s: data via %s; %s; acquired %s (%s day(s) ago)",
                self.source_id,
                entry.get("acquisition_mode") or "unknown mode",
                published,
                entry.get("acquired_at"),
                entry.get("acquired_age_days"),
            )

    @abstractmethod
    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        """Parse snapshots and return raw source records in the internal interchange model."""
