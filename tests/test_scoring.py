"""Weighted totals and competition ranks."""

from decimal import Decimal
from pathlib import Path

from deckeval.rubric import Criterion, ScoringGuide, load_rubric
from deckeval.scoring import assign_ranks, weighted_total

ROOT = Path(__file__).resolve().parents[1]


def _criterion(name: str, weight: str) -> Criterion:
    return Criterion(
        name=name,
        description="Placeholder",
        weight=Decimal(weight),
        scoring_guide=ScoringGuide(low="low", mid="mid", high="high"),
    )


def _sample_criteria() -> list[Criterion]:
    return [
        _criterion("Problem clarity", "0.20"),
        _criterion("Solution and innovation", "0.25"),
        _criterion("Market and impact", "0.20"),
        _criterion("Feasibility and execution plan", "0.20"),
        _criterion("Presentation quality", "0.15"),
    ]


def test_weighted_total_is_out_of_ten_and_rounded_half_up():
    criteria = _sample_criteria()
    scores = {
        "Problem clarity": 10,
        "Solution and innovation": 8,
        "Market and impact": 6,
        "Feasibility and execution plan": 4,
        "Presentation quality": 2,
    }
    # 2.0 + 2.0 + 1.2 + 0.8 + 0.3 = 6.3
    assert weighted_total(scores, criteria) == 6.3


def test_weighted_total_extremes_and_half_up():
    criteria = _sample_criteria()
    assert weighted_total({name: 10 for name in (c.name for c in criteria)}, criteria) == 10.0
    assert weighted_total({name: 0 for name in (c.name for c in criteria)}, criteria) == 0.0
    # 0.15 quantizes half-up to 0.2. Float round(0.15, 1) would not.
    pair = [_criterion("A", "0.15"), _criterion("B", "0.85")]
    assert weighted_total({"A": 1, "B": 0}, pair) == 0.2


def test_shipped_rubric_weights_match_the_brief():
    rubric = load_rubric(ROOT / "rubric.yaml")
    assert [criterion.name for criterion in rubric.criteria] == [
        "Problem clarity",
        "Solution and innovation",
        "Market and impact",
        "Feasibility and execution plan",
        "Presentation quality",
    ]
    assert [criterion.weight for criterion in rubric.criteria] == [
        Decimal("0.20"),
        Decimal("0.25"),
        Decimal("0.20"),
        Decimal("0.20"),
        Decimal("0.15"),
    ]
    assert weighted_total({name: 10 for name in rubric.names}, rubric.criteria) == 10.0


def test_ties_share_a_rank_and_the_next_rank_skips():
    assert assign_ranks([9.0, 8.5, 8.5, 7.0, None]) == [1, 2, 2, 4, None]
    assert assign_ranks([5.0, 5.0, 5.0]) == [1, 1, 1]
    assert assign_ranks([1.0, 10.0]) == [2, 1]
    assert assign_ranks([None, None]) == [None, None]
    assert assign_ranks([]) == []
