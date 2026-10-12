"""CSV column names and status values shared by the pipeline."""

from __future__ import annotations

REGN_ID = "Regn ID"
RANK = "Rank"
TOTAL = "Total Score (out of 10)"
DECK_URL = "Q1: Submit Round 1 Deck"
SUMMARY = "Overall summary"
STATUS = "status"
TEXT_ONLY = "text_only"
MODEL_ID = "model_id"
EVALUATED_AT = "evaluated_at"
ERROR = "error"

STATUS_SCORED = "scored"
STATUS_DOWNLOAD_FAILED = "download_failed"
STATUS_EVAL_FAILED = "eval_failed"
STATUS_DRY_RUN = "dry_run"

EXPECTED_INPUT_COLUMNS: tuple[str, ...] = (
    "Regn ID",
    "Rank",
    "Team Name",
    "Team Leader",
    "Candidate's Name",
    "Candidate's Email",
    "Candidate's Gender",
    "Candidate's Location",
    "User Type",
    "Domain",
    "Course",
    "Course Type",
    "Year of Graduation",
    "Work Experience",
    "Candidate's Organisation",
    "Class/Grade",
    "Differently-abled",
    "Total Score (out of 10)",
    "Submission Timestamp",
    "Q1: Submit Round 1 Deck",
)


def score_column(name: str) -> str:
    return f"Score: {name}"


def justification_column(name: str) -> str:
    return f"Justification: {name}"
