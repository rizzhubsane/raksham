"""Weighted totals and competition ranks. The model never computes these."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, ROUND_HALF_UP

from deckeval.rubric import Criterion


def weighted_total(scores: Mapping[str, int], criteria: Sequence[Criterion]) -> float:
    """Return the weighted score on a 0–10 scale, rounded to one decimal.

    Each criterion score is an integer from 0 to 10. Weights sum to 1, so the
    weighted sum is already out of 10. Rounding uses half-up, not banker's rounding.
    """
    expected = [criterion.name for criterion in criteria]
    missing = [name for name in expected if name not in scores]
    extra = [name for name in scores if name not in set(expected)]
    if missing or extra:
        raise ValueError(f"Score names do not match the rubric: missing={missing} extra={extra}")

    total = Decimal("0")
    for criterion in criteria:
        score = scores[criterion.name]
        if isinstance(score, bool) or not isinstance(score, int):
            raise ValueError(f"Score for {criterion.name} must be an integer")
        if score < 0 or score > 10:
            raise ValueError(f"Score for {criterion.name} must be from 0 to 10")
        total += Decimal(score) * criterion.weight
    return float(total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def assign_ranks(totals: Sequence[float | None]) -> list[int | None]:
    """Competition rank where 1 is highest. Ties share a rank and the next rank skips."""
    ranks: list[int | None] = [None] * len(totals)
    order = sorted(
        (index for index, score in enumerate(totals) if score is not None),
        key=lambda index: (-round(float(totals[index]), 1), index),
    )
    previous: float | None = None
    current_rank = 0
    for position, index in enumerate(order, start=1):
        score = round(float(totals[index]), 1)
        if previous is None or score != previous:
            current_rank = position
            previous = score
        ranks[index] = current_rank
    return ranks
