"""Wikidata SPARQL adapter — cross-registry identity resolution.

Wikidata sits in the graph-linking tier of the architecture, not the evaluative
tier. It contributes *links* between identifiers that authorities already own —
PUID, LoC FDD ID, MIME, extension — plus community-maintained context such as
developer and supersession. It deliberately does **not** contribute
sustainability or risk claims: a crowd-maintained graph must not supply
preservation evidence on equal footing with a national archive.

Two consequences are enforced here rather than left to configuration.

Identifiers are emitted as ``verified=False``. Wikidata is not the authority for
any of the namespaces it references, so its assertions are candidate links for
reconciliation to weigh, never strong reconciliation keys. The registry's
``identifier_kinds`` already models ``wikidata`` as ``weak``.

Only items carrying a PRONOM file format ID are harvested. Wikidata holds ~85k
items that are instances or subclasses of "file format", the overwhelming
majority of which have no identifier any preservation authority recognises.
Anchoring on P2748 keeps the harvest to the ~2.3k items that can actually join
the registry, and makes every emitted record resolvable by construction.

Property identifiers are easy to get wrong and fail silently — P2749 is PRONOM
*software* ID, and P3266 (not P3267, which is Flickr user ID) is the LoC FDD
identifier. Both mistakes return well-formed but near-empty results, so the
correct values are pinned as named constants and asserted in tests.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from registry_builder.adapters.base import SourceAdapter
from registry_builder.models import Identifier, RawFormatRecord, SourceSnapshot

DEFAULT_WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"

# Verified against the live property registry. Getting these wrong yields a
# valid-looking result set with ~96% of the data missing.
P_PRONOM_FILE_FORMAT = "P2748"   # NOT P2749, which is PRONOM *software* ID
P_LOC_FDD = "P3266"              # NOT P3267, which is Flickr user ID
P_FILE_EXTENSION = "P1195"
P_MEDIA_TYPE = "P1163"
P_DEVELOPER = "P178"
P_PUBLICATION_DATE = "P577"
P_REPLACED_BY = "P1366"

MULTI_VALUE_SEPARATOR = "|"

FORMAT_QUERY = """
SELECT ?item ?itemLabel
       (GROUP_CONCAT(DISTINCT ?puid;   separator="{sep}") AS ?puids)
       (GROUP_CONCAT(DISTINCT ?fdd;    separator="{sep}") AS ?fdds)
       (GROUP_CONCAT(DISTINCT ?ext;    separator="{sep}") AS ?exts)
       (GROUP_CONCAT(DISTINCT ?mime;   separator="{sep}") AS ?mimes)
       (GROUP_CONCAT(DISTINCT ?devLbl; separator="{sep}") AS ?developers)
       (GROUP_CONCAT(DISTINCT ?repLbl; separator="{sep}") AS ?replacedBy)
       (SAMPLE(?pub) AS ?published)
WHERE {{
  ?item wdt:{puid} ?puid .
  OPTIONAL {{ ?item wdt:{fdd}  ?fdd . }}
  OPTIONAL {{ ?item wdt:{ext}  ?ext . }}
  OPTIONAL {{ ?item wdt:{mime} ?mime . }}
  OPTIONAL {{ ?item wdt:{pub}  ?pub . }}
  OPTIONAL {{ ?item wdt:{dev}  ?dev . ?dev rdfs:label ?devLbl . FILTER(LANG(?devLbl)="en") }}
  OPTIONAL {{ ?item wdt:{rep}  ?rep . ?rep rdfs:label ?repLbl . FILTER(LANG(?repLbl)="en") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
GROUP BY ?item ?itemLabel
"""


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    seen: list[str] = []
    for part in str(value).split(MULTI_VALUE_SEPARATOR):
        part = part.strip()
        if part and part not in seen:
            seen.append(part)
    return seen


def _binding(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, dict):
        return ""
    return str(value.get("value") or "").strip()


class WikidataSparqlAdapter(SourceAdapter):
    """Harvest cross-registry identity links from the Wikidata Query Service."""

    type_name = "wikidata_sparql"

    def _endpoint(self) -> str:
        return str(self.config.get("endpoint") or DEFAULT_WIKIDATA_ENDPOINT)

    def _query(self) -> str:
        custom = self.config.get("query")
        if custom:
            return str(custom)
        return FORMAT_QUERY.format(
            sep=MULTI_VALUE_SEPARATOR,
            puid=P_PRONOM_FILE_FORMAT,
            fdd=P_LOC_FDD,
            ext=P_FILE_EXTENSION,
            mime=P_MEDIA_TYPE,
            pub=P_PUBLICATION_DATE,
            dev=P_DEVELOPER,
            rep=P_REPLACED_BY,
        )

    def request_uri(self) -> str:
        """Return the fully-formed GET URI, which is also the snapshot cache key.

        Encoding the query into the URI means a changed query produces a
        different snapshot rather than silently overwriting the previous one.
        """
        return f"{self._endpoint()}?{urlencode({'query': self._query(), 'format': 'json'})}"

    def acquire(self) -> list[SourceSnapshot]:
        return [
            self.acquire_uri_snapshot(
                self.request_uri(),
                suffix=".json",
                note="Wikidata SPARQL result for file formats carrying a PRONOM file format ID",
                metadata={
                    "endpoint": self._endpoint(),
                    "anchor_property": P_PRONOM_FILE_FORMAT,
                    "retrieval_mode": "sparql",
                },
            )
        ]

    def extract(self, snapshots: list[SourceSnapshot]) -> list[RawFormatRecord]:
        payloads = [
            (snapshot, json.loads(Path(snapshot.local_path).read_text(encoding="utf-8")))
            for snapshot in snapshots
        ]
        # Wikidata labels are not unique: seven separate items are each called
        # "PowerProject". Records sharing a label group together during
        # reconciliation and then carry conflicting PUID claims, which blocks the
        # bridge onto their verified owners. Count labels first so those names
        # can be qualified.
        label_counts: Counter[str] = Counter()
        for _, payload in payloads:
            for row in (payload.get("results") or {}).get("bindings", []):
                label = _binding(row, "itemLabel")
                if label:
                    label_counts[label] += 1

        records: list[RawFormatRecord] = []
        for snapshot, payload in payloads:
            for row in (payload.get("results") or {}).get("bindings", []):
                records.extend(self._records(row, snapshot, label_counts))
        return records

    def _records(self, row: dict[str, Any], snapshot: SourceSnapshot,
                 label_counts: Counter[str] | None = None) -> list[RawFormatRecord]:
        """Emit one record per asserted PUID.

        A Wikidata item often describes a format concept more broadly than
        PRONOM versions it — "Blend file" asserts both fmt/902 and fmt/903.
        Emitting a single record for such an item leaves reconciliation unable to
        bridge it to any one PRONOM record without guessing, so it correctly
        declines and the item becomes a spurious canonical of its own.

        Splitting per PUID states what Wikidata actually means: this QID applies
        to each of those formats. Each record then bridges cleanly onto the
        PRONOM-anchored canonical, and the sibling PUIDs are retained so the
        breadth of the original claim stays visible.
        """
        qid = _binding(row, "item").rsplit("/", 1)[-1]
        puids = _split(_binding(row, "puids"))
        if not qid or not puids:
            # Without a QID there is nothing to cite, and without a PUID the row
            # cannot be reconciled against anything in the registry.
            return []
        ambiguous = bool(label_counts and label_counts.get(_binding(row, "itemLabel"), 0) > 1)
        return [self._record(row, snapshot, qid, puid, puids, ambiguous) for puid in puids]

    @staticmethod
    def _record_name(label: str, puid: str, sibling_puids: list[str], ambiguous_label: bool = False) -> str:
        """Disambiguate the name when one item is split across several PUIDs.

        Reconciliation groups unverified records by name before it tries to
        bridge a copied identifier onto its verified owner. Split records that
        share a label therefore land in one group carrying two conflicting PUID
        claims, which the bridge correctly refuses. Qualifying the name keeps the
        records in separate groups so each bridges to the format it names. The
        unqualified label is preserved in native_fields.
        """
        return f"{label} ({puid})" if len(sibling_puids) > 1 or ambiguous_label else label

    def _record(self, row: dict[str, Any], snapshot: SourceSnapshot,
                qid: str, puid: str, sibling_puids: list[str],
                ambiguous_label: bool = False) -> RawFormatRecord:
        fdds = _split(_binding(row, "fdds"))
        identifiers = [
            Identifier(kind="wikidata", value=qid, source=self.source_id,
                       verified=False, source_record_id=qid)
        ]
        # Wikidata does not own the PUID or LoC namespaces, so these are
        # candidate links: useful for reconciliation, never authoritative.
        identifiers.append(
            Identifier(kind="puid", value=puid, source=self.source_id, verified=False, source_record_id=qid)
        )
        identifiers += [
            Identifier(kind="loc", value=f, source=self.source_id, verified=False, source_record_id=qid)
            for f in fdds
        ]

        return RawFormatRecord(
            source_id=self.source_id,
            source_type=self.type_name,
            source_record_id=f"{qid}:{puid}" if len(sibling_puids) > 1 else qid,
            name=self._record_name(_binding(row, "itemLabel") or qid, puid, sibling_puids, ambiguous_label),
            extensions=_split(_binding(row, "exts")),
            mime_types=_split(_binding(row, "mimes")),
            puids=[puid],
            loc_ids=fdds,
            wikidata_ids=[qid],
            identifiers=identifiers,
            urls={"wikidata": f"https://www.wikidata.org/wiki/{qid}"},
            # Source-native vocabulary only. Criterion IDs stay out of adapters;
            # any interpretation of these belongs in a reviewed mapping.
            native_fields={
                "wikidata": {
                    "developers": _split(_binding(row, "developers")),
                    "replaced_by": _split(_binding(row, "replacedBy")),
                    "publication_date": _binding(row, "published") or None,
                    "asserted_puids": sibling_puids,
                    "label": _binding(row, "itemLabel") or None,
                }
            },
            evidence=[{
                "type": "wikidata_sparql",
                "endpoint": self._endpoint(),
                "source_archive": snapshot.uri,
                "snapshot_sha256": snapshot.sha256,
                "anchor_property": P_PRONOM_FILE_FORMAT,
            }],
            raw={"snapshot_sha256": snapshot.sha256, "binding": row},
        )
