"""Assemble the output table and the end-of-run summary."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from deckeval.constants import (
    ERROR,
    EVALUATED_AT,
    MODEL_ID,
    RANK,
    STATUS,
    STATUS_DOWNLOAD_FAILED,
    STATUS_DRY_RUN,
    STATUS_EVAL_FAILED,
    STATUS_SCORED,
    SUMMARY,
    TEXT_ONLY,
    TOTAL,
    justification_column,
    score_column,
)
from deckeval.rubric import Criterion
from deckeval.scoring import assign_ranks

_BINS: tuple[tuple[str, float, float], ...] = (
    ("[0,2)", 0.0, 2.0),
    ("[2,4)", 2.0, 4.0),
    ("[4,6)", 4.0, 6.0),
    ("[6,8)", 6.0, 8.0),
    ("[8,10]", 8.0, 10.0001),
)


@dataclass(frozen=True)
class EvaluationRecord:
    status: str
    total: float | None
    scores: dict[str, int]
    justifications: dict[str, str]
    summary: str
    text_only: bool | None
    model_id: str
    evaluated_at: str
    error: str


def empty_record() -> EvaluationRecord:
    return EvaluationRecord(
        status="",
        total=None,
        scores={},
        justifications={},
        summary="",
        text_only=None,
        model_id="",
        evaluated_at="",
        error="",
    )


def output_field_order(input_columns: Sequence[str], criteria: Sequence[Criterion]) -> list[str]:
    ordered = list(input_columns)
    extras = [score_column(criterion.name) for criterion in criteria]
    extras.extend(justification_column(criterion.name) for criterion in criteria)
    extras.extend([SUMMARY, STATUS, TEXT_ONLY, MODEL_ID, EVALUATED_AT, ERROR])
    for column in extras:
        if column not in ordered:
            ordered.append(column)
    return ordered


def build_output_row(
    source: dict[str, str],
    input_columns: Sequence[str],
    criteria: Sequence[Criterion],
    record: EvaluationRecord,
) -> dict[str, str]:
    row = {column: source.get(column, "") for column in input_columns}
    row[RANK] = ""
    scored = record.status == STATUS_SCORED and record.total is not None
    row[TOTAL] = f"{record.total:.1f}" if scored else ""
    for criterion in criteria:
        if scored:
            row[score_column(criterion.name)] = str(record.scores[criterion.name])
            row[justification_column(criterion.name)] = record.justifications.get(criterion.name, "")
        else:
            row[score_column(criterion.name)] = ""
            row[justification_column(criterion.name)] = ""
    row[SUMMARY] = record.summary
    row[STATUS] = record.status
    row[TEXT_ONLY] = "" if record.text_only is None else str(record.text_only).lower()
    row[MODEL_ID] = record.model_id
    row[EVALUATED_AT] = record.evaluated_at
    row[ERROR] = record.error
    return row


def apply_output_ranks(rows: list[dict[str, str]]) -> None:
    totals: list[float | None] = []
    for row in rows:
        raw = row.get(TOTAL, "").strip()
        if row.get(STATUS) != STATUS_SCORED or raw == "":
            totals.append(None)
            continue
        totals.append(float(raw))
    for row, rank in zip(rows, assign_ranks(totals)):
        row[RANK] = "" if rank is None else str(rank)


def record_from_prior(prior: dict[str, str], criteria: Sequence[Criterion]) -> EvaluationRecord | None:
    """Rebuild a scored row from an existing output file. Incomplete rows are re-run."""
    if prior.get(STATUS, "").strip() != STATUS_SCORED:
        return None
    try:
        total = float(prior[TOTAL])
        scores: dict[str, int] = {}
        justifications: dict[str, str] = {}
        for criterion in criteria:
            raw_score = prior[score_column(criterion.name)].strip()
            if raw_score == "":
                return None
            scores[criterion.name] = int(raw_score)
            justifications[criterion.name] = prior.get(justification_column(criterion.name), "")
    except (KeyError, TypeError, ValueError):
        return None
    text_only = {"true": True, "false": False}.get(prior.get(TEXT_ONLY, "").strip().lower())
    return EvaluationRecord(
        status=STATUS_SCORED,
        total=total,
        scores=scores,
        justifications=justifications,
        summary=prior.get(SUMMARY, ""),
        text_only=text_only,
        model_id=prior.get(MODEL_ID, ""),
        evaluated_at=prior.get(EVALUATED_AT, ""),
        error="",
    )


def distribution(scores: Sequence[float]) -> list[tuple[str, int]]:
    counts: list[tuple[str, int]] = []
    for label, low, high in _BINS:
        count = sum(1 for score in scores if low <= score < high)
        counts.append((label, count))
    return counts


def summarize(rows: Sequence[dict[str, str]], resumed: int = 0) -> str:
    counts = {
        STATUS_SCORED: 0,
        STATUS_DOWNLOAD_FAILED: 0,
        STATUS_EVAL_FAILED: 0,
        STATUS_DRY_RUN: 0,
    }
    scores: list[float] = []
    text_only = 0
    for row in rows:
        status = row.get(STATUS, "")
        if status in counts:
            counts[status] += 1
        if status == STATUS_SCORED:
            raw = row.get(TOTAL, "").strip()
            if raw:
                scores.append(float(raw))
            if row.get(TEXT_ONLY, "").strip().lower() == "true":
                text_only += 1
    lines = [
        "Evaluation summary",
        f"scored: {counts[STATUS_SCORED]} (resumed: {resumed})",
        f"download_failed: {counts[STATUS_DOWNLOAD_FAILED]}",
        f"eval_failed: {counts[STATUS_EVAL_FAILED]}",
        f"dry_run: {counts[STATUS_DRY_RUN]}",
        f"text_only: {text_only}",
        "score distribution:",
    ]
    for label, count in distribution(scores):
        lines.append(f"  {label}: {count}")
    if scores:
        lines.append(f"mean: {statistics.fmean(scores):.1f}")
        lines.append(f"median: {statistics.median(scores):.1f}")
        lines.append(f"min: {min(scores):.1f}")
        lines.append(f"max: {max(scores):.1f}")
    else:
        lines.append("mean: n/a")
        lines.append("median: n/a")
        lines.append("min: n/a")
        lines.append("max: n/a")
    return "\n".join(lines)
