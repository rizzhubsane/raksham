"""Bedrock retries without calling AWS."""

import json

import pytest
from botocore.exceptions import ClientError

from deckeval.judge import EvaluationFailed, evaluate_deck
from deckeval.rubric import load_rubric
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _Deck:
    def __init__(self) -> None:
        self.slides = ()
        self.images = ()
        self.text_only = True


class _Client:
    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _response(text: str) -> dict:
    return {"output": {"message": {"content": [{"text": text}]}}}


def _valid(names) -> str:
    body = {
        "criteria": [
            {"name": name, "score": 7, "justification": "Slide 1 states the claim."}
            for name in names
        ],
        "summary": "A usable draft.",
    }
    return json.dumps(body)


def test_invalid_json_is_retried_and_temperature_is_zero():
    rubric = load_rubric(ROOT / "rubric.yaml")
    client = _Client([_response("nope"), _response(_valid(rubric.names))])
    judgment = evaluate_deck(client, "test-model", rubric, _Deck(), sleeper=lambda _delay: None)
    assert judgment.criteria[0].score == 7
    assert len(client.calls) == 2
    assert client.calls[0]["inferenceConfig"]["temperature"] == 0.0
    assert client.calls[0]["modelId"] == "test-model"
    repair = client.calls[1]["messages"][-1]["content"][0]["text"]
    assert "invalid JSON" in repair


def test_validation_gives_up_after_two_retries():
    rubric = load_rubric(ROOT / "rubric.yaml")
    client = _Client([_response("nope"), _response("{"), _response("still bad")])
    with pytest.raises(EvaluationFailed):
        evaluate_deck(client, "test-model", rubric, _Deck(), sleeper=lambda _delay: None)
    assert len(client.calls) == 3


def test_throttling_backs_off_and_then_succeeds():
    rubric = load_rubric(ROOT / "rubric.yaml")
    throttled = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "Converse",
    )
    client = _Client([throttled, _response(_valid(rubric.names))])
    delays: list[float] = []
    judgment = evaluate_deck(
        client,
        "test-model",
        rubric,
        _Deck(),
        sleeper=delays.append,
    )
    assert judgment.summary == "A usable draft."
    assert delays
    assert len(client.calls) == 2
