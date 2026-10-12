"""Validate model JSON against the rubric. Invalid output is not scored."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_SLIDE_RE = re.compile(r"\bslides?\s*\d+\b", re.IGNORECASE)


class SchemaValidationError(ValueError):
    """The model response is not usable JSON for this rubric."""

    def __init__(self, public_message: str, model_message: str | None = None) -> None:
        super().__init__(public_message)
        self.model_message = model_message or public_message


@dataclass(frozen=True)
class CriterionJudgment:
    name: str
    score: int
    justification: str


@dataclass(frozen=True)
class Judgment:
    criteria: tuple[CriterionJudgment, ...]
    summary: str


def parse_evaluation(payload: str, criteria_names: Sequence[str]) -> Judgment:
    """Parse and validate a model response. Raises SchemaValidationError."""
    try:
        data = _load_json(payload)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError("invalid JSON", f"invalid JSON: {exc.msg}") from exc
    model = evaluation_model(tuple(criteria_names))
    try:
        parsed = model.model_validate(data)
    except ValidationError as exc:
        message = _format_validation_error(exc)
        raise SchemaValidationError(message) from exc
    return Judgment(
        criteria=tuple(
            CriterionJudgment(
                name=item.name,
                score=item.score,
                justification=item.justification.strip(),
            )
            for item in parsed.criteria
        ),
        summary=parsed.summary.strip(),
    )


def _load_json(payload: str) -> object:
    text = payload.strip()
    if text.startswith("```"):
        text = _FENCE_RE.sub("", text).strip()
    return json.loads(text)


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"])
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)[:1500]


@lru_cache(maxsize=8)
def evaluation_model(criteria_names: tuple[str, ...]) -> type[BaseModel]:
    """Build a pydantic model that accepts exactly these criterion names."""
    expected = criteria_names

    class CriterionScore(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str
        score: int = Field(ge=0, le=10)
        justification: str = Field(min_length=1, max_length=400)

        @field_validator("score", mode="before")
        @classmethod
        def coerce_score(cls, value: object) -> object:
            if isinstance(value, bool):
                raise ValueError("score must be an integer from 0 to 10")
            if isinstance(value, str):
                try:
                    value = float(value.strip())
                except ValueError:
                    return value
            if isinstance(value, float):
                if not value.is_integer():
                    raise ValueError("score must be an integer from 0 to 10")
                return int(value)
            return value

        @field_validator("justification")
        @classmethod
        def cite_slide(cls, value: str) -> str:
            text = value.strip()
            if _SLIDE_RE.search(text) is None:
                raise ValueError("justification must cite a slide number, for example 'Slide 2'")
            return text

    class DeckEvaluation(BaseModel):
        model_config = ConfigDict(extra="forbid")
        criteria: list[CriterionScore] = Field(min_length=1)
        summary: str = Field(min_length=1, max_length=600)

        @model_validator(mode="after")
        def check_criteria(self) -> "DeckEvaluation":
            found = [item.name for item in self.criteria]
            if len(found) != len(set(found)):
                raise ValueError(f"duplicate criterion names: {found}")
            missing = [name for name in expected if name not in found]
            extra = [name for name in found if name not in expected]
            if missing or extra:
                raise ValueError(f"missing={missing} extra={extra}")
            by_name = {item.name: item for item in self.criteria}
            self.criteria = [by_name[name] for name in expected]
            return self

    return DeckEvaluation
