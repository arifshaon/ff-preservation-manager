from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


class CriteriaError(ValueError):
    """Raised when a criterion vocabulary or criterion value is invalid."""


@dataclass(frozen=True)
class CriterionDefinition:
    id: str
    kind: str
    values: tuple[str, ...] = ()
    null_value: str | None = None
    unit: str | None = None

    @classmethod
    def from_dict(cls, criterion_id: str, data: dict[str, Any]) -> "CriterionDefinition":
        kind = str(data.get("kind") or "").strip()
        if kind not in {"ordinal", "nominal", "temporal"}:
            raise CriteriaError(f"Criterion {criterion_id} has unsupported kind: {kind!r}")
        values = tuple(str(value) for value in data.get("values", []))
        null_value = data.get("null_value")
        null_text = str(null_value) if null_value is not None else None
        if kind in {"ordinal", "nominal"} and not values:
            raise CriteriaError(f"Criterion {criterion_id} must define values")
        if len(values) != len(set(values)):
            raise CriteriaError(f"Criterion {criterion_id} has duplicate values")
        if null_text and null_text in values:
            raise CriteriaError(f"Criterion {criterion_id} null_value must not be on the scale")
        if kind == "temporal" and not data.get("unit"):
            raise CriteriaError(f"Temporal criterion {criterion_id} must define unit")
        return cls(
            id=criterion_id,
            kind=kind,
            values=values,
            null_value=null_text,
            unit=str(data.get("unit")) if data.get("unit") is not None else None,
        )

    def allows(self, value: Any) -> bool:
        text = str(value)
        if self.null_value is not None and text == self.null_value:
            return True
        if self.kind == "temporal":
            try:
                float(text)
                return True
            except ValueError:
                return False
        return text in self.values

    def ordinal_distance(self, left: Any, right: Any) -> int | None:
        if self.kind != "ordinal":
            return None
        left_text = str(left)
        right_text = str(right)
        if self.null_value in {left_text, right_text}:
            return None
        if left_text not in self.values or right_text not in self.values:
            raise CriteriaError(f"Cannot compare values outside {self.id} scale: {left!r}, {right!r}")
        return abs(self.values.index(left_text) - self.values.index(right_text))


class CriteriaVocabulary:
    """Neutral criterion vocabulary used by registry-builder mappings."""

    def __init__(self, data: dict[str, Any]) -> None:
        version = str(data.get("criteria_version") or "").strip()
        if not version:
            raise CriteriaError("Criterion vocabulary is missing criteria_version")
        raw_criteria = data.get("criteria") or {}
        if not isinstance(raw_criteria, dict) or not raw_criteria:
            raise CriteriaError("Criterion vocabulary must define criteria")
        self.criteria_version = version
        self.criteria = {
            str(criterion_id): CriterionDefinition.from_dict(str(criterion_id), dict(definition))
            for criterion_id, definition in raw_criteria.items()
        }
        self.reconciliation = dict(data.get("reconciliation") or {})

    def criterion(self, criterion_id: str) -> CriterionDefinition:
        try:
            return self.criteria[criterion_id]
        except KeyError as exc:
            raise CriteriaError(f"Unknown criterion_id: {criterion_id}") from exc

    def validate_value(self, criterion_id: str, value: Any) -> None:
        criterion = self.criterion(criterion_id)
        if not criterion.allows(value):
            raise CriteriaError(f"Value {value!r} is not allowed for criterion {criterion_id}")

    def ordinal_distance(self, criterion_id: str, left: Any, right: Any) -> int | None:
        return self.criterion(criterion_id).ordinal_distance(left, right)

    def to_dict(self) -> dict[str, Any]:
        return {
            "criteria_version": self.criteria_version,
            "criteria": {
                criterion_id: {
                    "kind": criterion.kind,
                    "values": list(criterion.values),
                    "null_value": criterion.null_value,
                    "unit": criterion.unit,
                }
                for criterion_id, criterion in self.criteria.items()
            },
            "reconciliation": self.reconciliation,
        }


def load_criteria(path: str | Path) -> CriteriaVocabulary:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CriteriaError("Criterion vocabulary JSON must contain an object")
    return CriteriaVocabulary(data)


def derive_confidence(*, directness: str, source_independence: str | None = None) -> str:
    """Derive claim confidence from mapping directness and independence.

    Confidence is intentionally not stored in mapping configs. It is derived so
    explicit/inferred and independent/source-derived claims cannot drift into
    contradictory combinations.
    """
    directness = str(directness or "").strip().lower()
    independence = str(source_independence or "").strip().lower()
    if directness == "explicit" and independence in {"independent", ""}:
        return "high"
    if directness == "explicit":
        return "medium"
    if directness == "derived" and independence == "independent":
        return "medium"
    if directness in {"derived", "inferred", "heuristic"}:
        return "weak"
    return "weak"
