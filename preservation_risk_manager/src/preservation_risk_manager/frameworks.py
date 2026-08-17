from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from preservation_risk_manager.errors import FrameworkError


@dataclass(frozen=True)
class AnswerOption:
    id: str
    points: float
    label: str | None = None
    abstention: bool = False
    definition: str | None = None
    guidance: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnswerOption":
        if "id" not in data:
            raise FrameworkError("Answer option is missing required field: id")
        if "points" not in data:
            raise FrameworkError(f"Answer option {data.get('id')} is missing required field: points")
        try:
            points = float(data["points"])
        except (TypeError, ValueError) as exc:
            raise FrameworkError(f"Answer option {data.get('id')} has non-numeric points") from exc
        return cls(
            id=str(data["id"]),
            points=points,
            label=data.get("label"),
            abstention=bool(data.get("abstention", False)),
            definition=data.get("definition"),
            guidance=data.get("guidance"),
        )


@dataclass(frozen=True)
class Question:
    id: str
    label: str
    answers: tuple[AnswerOption, ...]
    critical: bool = False
    weight: float = 1.0
    evidence_fields: tuple[str, ...] = ()
    domain_id: str | None = None
    domain_label: str | None = None
    definition: str | None = None
    guidance: str | None = None
    applicability: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Question":
        if "id" not in data:
            raise FrameworkError("Question is missing required field: id")
        question_id = str(data["id"])
        answers = tuple(AnswerOption.from_dict(answer) for answer in data.get("answers", []))
        if not answers:
            raise FrameworkError(f"Question {question_id} must define at least one answer")
        answer_ids = [answer.id for answer in answers]
        if len(answer_ids) != len(set(answer_ids)):
            raise FrameworkError(f"Question {question_id} has duplicate answer IDs")
        try:
            weight = float(data.get("weight", 1.0))
        except (TypeError, ValueError) as exc:
            raise FrameworkError(f"Question {question_id} has non-numeric weight") from exc
        if weight <= 0:
            raise FrameworkError(f"Question {question_id} weight must be greater than zero")
        return cls(
            id=question_id,
            label=str(data.get("label") or question_id),
            answers=answers,
            critical=bool(data.get("critical", False)),
            weight=weight,
            evidence_fields=tuple(str(field) for field in data.get("evidence_fields", [])),
            domain_id=str(data.get("domain_id")) if data.get("domain_id") is not None else None,
            domain_label=str(data.get("domain_label")) if data.get("domain_label") is not None else None,
            definition=data.get("definition"),
            guidance=data.get("guidance"),
            applicability=tuple(str(value) for value in data.get("applicability", [])),
            aliases=tuple(str(value) for value in data.get("aliases", [])),
        )

    def answer_by_id(self, answer_id: str) -> AnswerOption:
        for answer in self.answers:
            if answer.id == answer_id:
                return answer
        raise FrameworkError(f"Question {self.id} does not allow answer ID: {answer_id}")

    def unknown_answer(self, preferred_id: str = "unknown") -> AnswerOption | None:
        for answer in self.answers:
            if answer.id == preferred_id:
                return answer
        for answer in self.answers:
            if answer.abstention:
                return answer
        return None

    def max_non_abstention_points(self) -> float:
        non_abstention = [answer.points for answer in self.answers if not answer.abstention]
        if not non_abstention:
            return 0.0
        return max(non_abstention) * self.weight


@dataclass(frozen=True)
class ScoreBand:
    band: str
    min_score: float
    max_score: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoreBand":
        try:
            return cls(
                band=str(data["band"]),
                min_score=float(data["min_score"]),
                max_score=float(data["max_score"]),
            )
        except KeyError as exc:
            raise FrameworkError(f"Score band is missing required field: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise FrameworkError("Score band min_score/max_score must be numeric") from exc

    def contains(self, score: float) -> bool:
        return self.min_score <= score <= self.max_score


@dataclass(frozen=True)
class RiskScale:
    direction: str
    bands: tuple[ScoreBand, ...]
    min_completeness_for_band: float
    banding_enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, framework_id: str) -> "RiskScale":
        if not isinstance(data, dict):
            raise FrameworkError(f"Framework {framework_id} must define a scale object")
        direction = str(data.get("direction") or "").strip()
        if direction not in {"higher_is_risk", "lower_is_risk"}:
            raise FrameworkError(
                f"Framework {framework_id} scale.direction must be 'higher_is_risk' or 'lower_is_risk'"
            )
        bands_data = data.get("bands")
        if not isinstance(bands_data, list) or not bands_data:
            raise FrameworkError(f"Framework {framework_id} scale.bands must define at least one score band")
        bands = tuple(ScoreBand.from_dict(band) for band in bands_data)
        _validate_score_bands(bands)
        try:
            min_completeness = float(data["min_completeness_for_band"])
        except KeyError as exc:
            raise FrameworkError(
                f"Framework {framework_id} scale is missing required field: min_completeness_for_band"
            ) from exc
        except (TypeError, ValueError) as exc:
            raise FrameworkError(
                f"Framework {framework_id} scale.min_completeness_for_band must be numeric"
            ) from exc
        if not 0 <= min_completeness <= 1:
            raise FrameworkError(
                f"Framework {framework_id} scale.min_completeness_for_band must be between 0 and 1"
            )
        return cls(
            direction=direction,
            bands=bands,
            min_completeness_for_band=min_completeness,
            banding_enabled=bool(data.get("banding_enabled", True)),
        )


@dataclass(frozen=True)
class RiskFramework:
    framework_id: str
    version: str
    questions: tuple[Question, ...]
    scale: RiskScale
    label: str | None = None
    unknown_answer_id: str = "unknown"
    description: str | None = None
    calibration_status: str = "calibrated"
    source_basis: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RiskFramework":
        framework_id = str(data.get("framework_id") or data.get("id") or "")
        if not framework_id:
            raise FrameworkError("Framework is missing required field: framework_id")
        version = str(data.get("version") or "0.1.0")
        questions = tuple(Question.from_dict(question) for question in data.get("questions", []))
        if not questions:
            raise FrameworkError(f"Framework {framework_id} must define at least one question")
        question_ids = [question.id for question in questions]
        if len(question_ids) != len(set(question_ids)):
            raise FrameworkError(f"Framework {framework_id} has duplicate question IDs")
        if "scale" not in data:
            raise FrameworkError(f"Framework {framework_id} must define scale")
        scale = RiskScale.from_dict(data["scale"], framework_id=framework_id)
        return cls(
            framework_id=framework_id,
            version=version,
            label=data.get("label"),
            questions=questions,
            scale=scale,
            unknown_answer_id=str(data.get("unknown_answer_id") or "unknown"),
            description=data.get("description"),
            calibration_status=str(data.get("calibration_status") or "calibrated"),
            source_basis=tuple(str(value) for value in data.get("source_basis", [])),
        )

    @property
    def score_bands(self) -> tuple[ScoreBand, ...]:
        return self.scale.bands

    @property
    def scale_direction(self) -> str:
        return self.scale.direction

    @property
    def min_completeness_for_band(self) -> float:
        return self.scale.min_completeness_for_band

    @property
    def banding_enabled(self) -> bool:
        return self.scale.banding_enabled

    def question_by_id(self, question_id: str) -> Question:
        for question in self.questions:
            if question.id == question_id:
                return question
        raise FrameworkError(f"Framework {self.framework_id} has no question ID: {question_id}")

    def questions_for_domain(self, domain_id: str) -> tuple[Question, ...]:
        needle = str(domain_id).strip().lower()
        return tuple(
            question for question in self.questions
            if str(question.domain_id or "").strip().lower() == needle
        )

    def band_for_score(self, score: float) -> str:
        for band in self.scale.bands:
            if band.contains(score):
                return band.band
        raise FrameworkError(f"Score {score} does not fit any band in framework {self.framework_id}")

    @property
    def max_score(self) -> float:
        return sum(question.max_non_abstention_points() for question in self.questions)


def _validate_score_bands(score_bands: tuple[ScoreBand, ...]) -> None:
    ordered = sorted(score_bands, key=lambda band: band.min_score)
    previous: ScoreBand | None = None
    seen: set[str] = set()
    for band in ordered:
        if band.band in seen:
            raise FrameworkError(f"Duplicate score band: {band.band}")
        seen.add(band.band)
        if band.min_score > band.max_score:
            raise FrameworkError(f"Score band {band.band} has min_score above max_score")
        if previous and band.min_score <= previous.max_score:
            raise FrameworkError(f"Score band {band.band} overlaps with {previous.band}")
        previous = band


def load_framework(path: str | Path) -> RiskFramework:
    """Load a risk framework from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FrameworkError("Framework JSON must contain an object")
    return RiskFramework.from_dict(data)
