"""Rubric file checks."""

from pathlib import Path

import pytest

from deckeval.rubric import RubricError, load_rubric

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_shipped_rubric_loads():
    rubric = load_rubric(ROOT / "rubric.yaml")
    assert len(rubric.criteria) == 5


def test_weights_must_sum_to_one(tmp_path: Path):
    path = _write(
        tmp_path / "bad.yaml",
        """
criteria:
  - name: Only one
    description: A single criterion.
    weight: "0.50"
    scoring_guide:
      "0-3": low
      "4-6": mid
      "7-10": high
""",
    )
    with pytest.raises(RubricError, match="sum to 1.0"):
        load_rubric(path)


def test_duplicate_names_are_rejected(tmp_path: Path):
    path = _write(
        tmp_path / "dup.yaml",
        """
criteria:
  - name: Same
    description: First.
    weight: "0.50"
    scoring_guide:
      "0-3": low
      "4-6": mid
      "7-10": high
  - name: Same
    description: Second.
    weight: "0.50"
    scoring_guide:
      "0-3": low
      "4-6": mid
      "7-10": high
""",
    )
    with pytest.raises(RubricError, match="Duplicate"):
        load_rubric(path)


def test_scoring_guide_keys_are_required(tmp_path: Path):
    path = _write(
        tmp_path / "guide.yaml",
        """
criteria:
  - name: Problem clarity
    description: A problem.
    weight: "1.0"
    scoring_guide:
      "0-3": low
      "7-10": high
""",
    )
    with pytest.raises(RubricError, match="Scoring guide"):
        load_rubric(path)
