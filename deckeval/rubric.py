"""Load and validate the scoring rubric from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

GUIDE_KEYS: tuple[str, ...] = ("0-3", "4-6", "7-10")
_CRITERION_KEYS = {"name", "description", "weight", "scoring_guide"}
_WEIGHT_TOLERANCE = Decimal("0.000001")


class RubricError(ValueError):
    """The rubric file is missing or does not match the required shape."""


@dataclass(frozen=True)
class ScoringGuide:
    low: str
    mid: str
    high: str


@dataclass(frozen=True)
class Criterion:
    name: str
    description: str
    weight: Decimal
    scoring_guide: ScoringGuide


@dataclass(frozen=True)
class Rubric:
    criteria: tuple[Criterion, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(criterion.name for criterion in self.criteria)


def load_rubric(path: Path) -> Rubric:
    """Load a rubric and reject it unless weights sum to 1."""
    if not path.is_file():
        raise RubricError(f"Rubric file not found: {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RubricError(f"Rubric YAML is invalid: {exc}") from exc
    if not isinstance(loaded, dict) or set(loaded) != {"criteria"}:
        raise RubricError("Rubric must be a mapping with a single 'criteria' key")
    raw_criteria = loaded["criteria"]
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise RubricError("Rubric criteria must be a non-empty list")

    criteria: list[Criterion] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_criteria, start=1):
        criterion = _parse_criterion(raw, index)
        if criterion.name in seen:
            raise RubricError(f"Duplicate criterion name: {criterion.name}")
        seen.add(criterion.name)
        criteria.append(criterion)

    total_weight = sum((criterion.weight for criterion in criteria), Decimal("0"))
    if abs(total_weight - Decimal("1")) > _WEIGHT_TOLERANCE:
        raise RubricError(f"Rubric weights must sum to 1.0, got {total_weight}")
    return Rubric(criteria=tuple(criteria))


def _parse_criterion(raw: object, index: int) -> Criterion:
    if not isinstance(raw, dict):
        raise RubricError(f"Criterion {index} must be a mapping")
    unknown = set(raw) - _CRITERION_KEYS
    missing = _CRITERION_KEYS - set(raw)
    if unknown or missing:
        raise RubricError(
            f"Criterion {index} has missing or unknown keys: "
            f"missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    name = _require_text(raw["name"], f"Criterion {index} name")
    description = _require_text(raw["description"], f"Criterion {index} description")
    weight = _parse_weight(raw["weight"], name)
    guide = _parse_guide(raw["scoring_guide"], name)
    return Criterion(name=name, description=description, weight=weight, scoring_guide=guide)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RubricError(f"{label} must be a non-empty string")
    return value.strip()


def _parse_weight(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise RubricError(f"Weight for {name} must be a number")
    try:
        weight = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise RubricError(f"Weight for {name} is not a number") from exc
    if weight <= 0 or weight > 1:
        raise RubricError(f"Weight for {name} must be between 0 and 1 exclusive of 0")
    return weight


def _parse_guide(value: object, name: str) -> ScoringGuide:
    if not isinstance(value, dict) or set(value) != set(GUIDE_KEYS):
        raise RubricError(
            f"Scoring guide for {name} must contain exactly the keys {', '.join(GUIDE_KEYS)}"
        )
    bands = [_require_text(value[key], f"Scoring guide {key} for {name}") for key in GUIDE_KEYS]
    return ScoringGuide(low=bands[0], mid=bands[1], high=bands[2])
