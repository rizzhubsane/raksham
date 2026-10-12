"""JSON schema validation for model output."""

import json
from pathlib import Path

import pytest

from deckeval.rubric import load_rubric
from deckeval.schema import SchemaValidationError, parse_evaluation

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "Problem clarity",
    "Solution and innovation",
    "Market and impact",
    "Feasibility and execution plan",
    "Presentation quality",
)


def _payload(names=NAMES, score=7, justification="Slide 2 states the claim clearly.", summary="A complete draft."):
    return {
        "criteria": [
            {"name": name, "score": score, "justification": justification} for name in names
        ],
        "summary": summary,
    }


def test_valid_json_is_reordered_to_the_rubric():
    body = _payload()
    body["criteria"] = list(reversed(body["criteria"]))
    judgment = parse_evaluation(json.dumps(body), NAMES)
    assert [item.name for item in judgment.criteria] == list(NAMES)
    assert all(item.score == 7 for item in judgment.criteria)
    assert judgment.summary == "A complete draft."


def test_markdown_fence_and_integer_float_are_accepted():
    body = _payload(score=8.0)
    fenced = "```json\n" + json.dumps(body) + "\n```"
    judgment = parse_evaluation(fenced, NAMES)
    assert judgment.criteria[0].score == 8


def test_shipped_rubric_names_validate():
    rubric = load_rubric(ROOT / "rubric.yaml")
    judgment = parse_evaluation(json.dumps(_payload(rubric.names)), rubric.names)
    assert len(judgment.criteria) == len(rubric.criteria)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda body: body["criteria"][0].update(score=11),
        lambda body: body["criteria"][0].update(score=7.5),
        lambda body: body["criteria"][0].update(score=True),
        lambda body: body["criteria"][0].update(justification="Looks polished."),
        lambda body: body["criteria"].pop(),
        lambda body: body.update(total=9.5),
        lambda body: body["criteria"].append(dict(body["criteria"][0])),
    ],
)
def test_invalid_model_output_is_rejected(mutate):
    body = _payload()
    mutate(body)
    with pytest.raises(SchemaValidationError):
        parse_evaluation(json.dumps(body), NAMES)


def test_invalid_json_has_a_short_public_message():
    with pytest.raises(SchemaValidationError) as caught:
        parse_evaluation("not json", NAMES)
    assert str(caught.value) == "invalid JSON"
    assert "invalid JSON" in caught.value.model_message
