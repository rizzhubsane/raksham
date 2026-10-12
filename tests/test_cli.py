"""CLI and resume behavior that does not call AWS."""

import csv
from pathlib import Path

import pandas as pd

from deckeval.constants import (
    DECK_URL,
    EXPECTED_INPUT_COLUMNS,
    RANK,
    REGN_ID,
    STATUS,
    TOTAL,
)
from deckeval.report import (
    EvaluationRecord,
    apply_output_ranks,
    build_output_row,
    output_field_order,
)
from deckeval.rubric import load_rubric
from deckeval.runner import RunConfig, run
from deckeval.storage import read_csv, write_csv
from eval_decks import main

ROOT = Path(__file__).resolve().parents[1]


def _source(regn_id: str = "RK-1", team: str = "Northwind", url: str = "-") -> dict[str, str]:
    row = {column: "-" for column in EXPECTED_INPUT_COLUMNS}
    row[REGN_ID] = regn_id
    row["Team Name"] = team
    row["Candidate's Name"] = "Ada Example"
    row["Candidate's Email"] = "ada@example.com"
    row[DECK_URL] = url
    return row


def _write_input(path: Path, team: str = "Northwind") -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(EXPECTED_INPUT_COLUMNS))
        writer.writeheader()
        writer.writerow(_source(team=team))


def test_sample_input_has_one_fake_row():
    frame = pd.read_csv(ROOT / "sample_input.csv", dtype=str, keep_default_na=False)
    assert list(frame.columns) == list(EXPECTED_INPUT_COLUMNS)
    assert len(frame) == 1
    assert frame.iloc[0][REGN_ID] == "RKHM-10042"


def test_dry_run_marks_a_blank_link_without_calling_bedrock(tmp_path: Path, capsys):
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    _write_input(source)
    code = main(
        [
            "--input",
            str(source),
            "--output",
            str(output),
            "--rubric",
            str(ROOT / "rubric.yaml"),
            "--dry-run",
            "--workers",
            "1",
            "--cache-dir",
            str(tmp_path / "cache"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "download_failed: 1" in captured.out
    frame = read_csv(output)
    assert frame.iloc[0][STATUS] == "download_failed"
    assert frame.iloc[0]["error"] == "missing_or_invalid_link"
    assert frame.iloc[0][TOTAL] == ""
    assert frame.iloc[0][RANK] == ""
    assert "ada@example.com" not in captured.out
    assert "ada@example.com" not in captured.err
    assert "Ada Example" not in captured.out
    assert "Ada Example" not in captured.err


def test_resume_keeps_scores_and_uses_the_latest_row_text(tmp_path: Path):
    rubric = load_rubric(ROOT / "rubric.yaml")
    record = EvaluationRecord(
        status="scored",
        total=8.0,
        scores={criterion.name: 8 for criterion in rubric.criteria},
        justifications={criterion.name: "Slide 1 is specific." for criterion in rubric.criteria},
        summary="Kept from the previous run.",
        text_only=False,
        model_id="test-model",
        evaluated_at="2026-04-01T00:00:00+00:00",
        error="",
    )
    prior = build_output_row(_source(team="Old Team"), EXPECTED_INPUT_COLUMNS, rubric.criteria, record)
    apply_output_ranks([prior])
    output = tmp_path / "output.csv"
    columns = output_field_order(EXPECTED_INPUT_COLUMNS, rubric.criteria)
    write_csv(pd.DataFrame([prior], columns=columns), output)

    source = tmp_path / "input.csv"
    _write_input(source, team="Updated Team")
    summary = run(
        RunConfig(
            rubric=rubric,
            input_path=source,
            output_path=output,
            cache_dir=tmp_path / "cache",
            workers=1,
            resume=True,
            dry_run=True,
            limit=None,
            model_id="",
            max_images=15,
            client=None,
            s3_output=None,
            region=None,
        )
    )
    frame = read_csv(output)
    assert frame.iloc[0]["Team Name"] == "Updated Team"
    assert frame.iloc[0][STATUS] == "scored"
    assert frame.iloc[0][TOTAL] == "8.0"
    assert frame.iloc[0][RANK] == "1"
    assert frame.iloc[0]["Overall summary"] == "Kept from the previous run."
    assert "scored: 1 (resumed: 1)" in summary


def test_missing_paths_and_bad_workers_exit_2(tmp_path: Path):
    output = tmp_path / "output.csv"
    assert main(["--output", str(output), "--dry-run"]) == 2
    source = tmp_path / "input.csv"
    _write_input(source)
    assert (
        main(
            [
                "--input",
                str(source),
                "--output",
                str(output),
                "--rubric",
                str(tmp_path / "missing.yaml"),
                "--dry-run",
            ]
        )
        == 2
    )
    assert main(["--input", str(source), "--output", str(output), "--workers", "0", "--dry-run"]) == 2
