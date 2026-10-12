"""Run deck evaluation across a submission CSV."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from deckeval.constants import (
    DECK_URL,
    EXPECTED_INPUT_COLUMNS,
    REGN_ID,
    STATUS_DOWNLOAD_FAILED,
    STATUS_DRY_RUN,
    STATUS_EVAL_FAILED,
    STATUS_SCORED,
)
from deckeval.content import (
    DownloadError,
    find_soffice,
    load_deck,
    normalize_url,
    poppler_available,
)
from deckeval.judge import evaluate_deck
from deckeval.privacy import public_error
from deckeval.report import (
    EvaluationRecord,
    apply_output_ranks,
    build_output_row,
    empty_record,
    output_field_order,
    record_from_prior,
    summarize,
)
from deckeval.rubric import Rubric
from deckeval.scoring import weighted_total
from deckeval.storage import StorageError, read_csv, upload_s3, write_csv

logger = logging.getLogger("eval_decks")


@dataclass
class RunConfig:
    rubric: Rubric
    input_path: Path
    output_path: Path
    cache_dir: Path
    workers: int
    resume: bool
    dry_run: bool
    limit: int | None
    model_id: str
    max_images: int
    client: object | None
    s3_output: str | None
    region: str | None


def run(config: RunConfig) -> str:
    """Evaluate each submission and write the output CSV. Returns the summary text."""
    if find_soffice() is None:
        logger.warning("LibreOffice not found; rendering will fall back to text_only")
    elif not poppler_available():
        logger.warning("poppler not found; rendering will fall back to text_only")

    frame = read_csv(config.input_path)
    missing = [column for column in EXPECTED_INPUT_COLUMNS if column not in frame.columns]
    if missing:
        raise StorageError("Input CSV is missing columns: " + ", ".join(missing))
    if config.limit is not None:
        frame = frame.head(config.limit)

    sources = [
        {str(key): "" if value is None else str(value) for key, value in raw.items()}
        for raw in frame.to_dict(orient="records")
    ]
    input_columns = list(frame.columns)
    criteria = config.rubric.criteria
    columns = output_field_order(input_columns, criteria)
    priors = _load_priors(config)

    output_rows: list[dict[str, str]] = []
    pending: list[int] = []
    resumed = 0
    seen: set[str] = set()
    warned: set[str] = set()
    for index, source in enumerate(sources):
        regn_id = source.get(REGN_ID, "").strip()
        if regn_id:
            if regn_id in seen and regn_id not in warned:
                logger.warning("duplicate regn_id=%s", regn_id)
                warned.add(regn_id)
            seen.add(regn_id)
        prior = record_from_prior(priors.get(regn_id, {}), criteria) if config.resume and regn_id else None
        if prior is not None:
            resumed += 1
            output_rows.append(build_output_row(source, input_columns, criteria, prior))
        else:
            output_rows.append(build_output_row(source, input_columns, criteria, empty_record()))
            pending.append(index)

    if not config.dry_run:
        logger.info("model_id=%s", config.model_id)
    logger.info(
        "rows=%s pending=%s resumed=%s workers=%s dry_run=%s",
        len(sources),
        len(pending),
        resumed,
        config.workers,
        config.dry_run,
    )

    if pending:
        with logging_redirect_tqdm():
            with ThreadPoolExecutor(max_workers=config.workers) as executor:
                futures = {
                    executor.submit(_process_one, sources[index], index, config): index
                    for index in pending
                }
                for future in tqdm(
                    as_completed(futures),
                    total=len(futures),
                    desc="Evaluating",
                    unit="deck",
                ):
                    index = futures[future]
                    try:
                        record = future.result()
                    except Exception as exc:
                        regn_id = sources[index].get(REGN_ID, "").strip() or f"row-{index + 1}"
                        reason = public_error(exc)
                        logger.warning("eval_failed regn_id=%s reason=%s", regn_id, reason)
                        record = _failed(STATUS_EVAL_FAILED, reason, config.model_id)
                    output_rows[index] = build_output_row(
                        sources[index], input_columns, criteria, record
                    )
                    apply_output_ranks(output_rows)
                    _flush(output_rows, columns, config)

    apply_output_ranks(output_rows)
    _flush(output_rows, columns, config)
    return summarize(output_rows, resumed=resumed)


def _process_one(source: dict[str, str], index: int, config: RunConfig) -> EvaluationRecord:
    regn_id = source.get(REGN_ID, "").strip() or f"row-{index + 1}"
    evaluated_at = _now()
    url = normalize_url(source.get(DECK_URL, ""))
    if url is None:
        logger.warning("download_failed regn_id=%s reason=missing_or_invalid_link", regn_id)
        return _failed(STATUS_DOWNLOAD_FAILED, "missing_or_invalid_link", "", evaluated_at)

    try:
        deck = load_deck(url, config.cache_dir)
    except DownloadError as exc:
        logger.warning("download_failed regn_id=%s reason=%s", regn_id, exc.reason)
        return _failed(STATUS_DOWNLOAD_FAILED, exc.reason, "", evaluated_at)
    except Exception as exc:
        reason = public_error(exc)
        logger.warning("download_failed regn_id=%s reason=%s", regn_id, reason)
        return _failed(STATUS_DOWNLOAD_FAILED, reason, "", evaluated_at)

    if config.dry_run:
        logger.info(
            "dry_run regn_id=%s slides=%s text_only=%s",
            regn_id,
            len(deck.slides),
            deck.text_only,
        )
        return EvaluationRecord(
            status=STATUS_DRY_RUN,
            total=None,
            scores={},
            justifications={},
            summary=f"Extracted {len(deck.slides)} slides.",
            text_only=deck.text_only,
            model_id="",
            evaluated_at=evaluated_at,
            error="",
        )

    try:
        if config.client is None:
            raise EvaluationError("Bedrock client is not configured")
        judgment = evaluate_deck(
            config.client,
            config.model_id,
            config.rubric,
            deck,
            max_images=config.max_images,
        )
        scores = {item.name: item.score for item in judgment.criteria}
        justifications = {item.name: item.justification for item in judgment.criteria}
        total = weighted_total(scores, config.rubric.criteria)
    except Exception as exc:
        reason = public_error(exc)
        logger.warning("eval_failed regn_id=%s reason=%s", regn_id, reason)
        return _failed(STATUS_EVAL_FAILED, reason, config.model_id, evaluated_at, deck.text_only)

    logger.info("scored regn_id=%s total=%.1f text_only=%s", regn_id, total, deck.text_only)
    return EvaluationRecord(
        status=STATUS_SCORED,
        total=total,
        scores=scores,
        justifications=justifications,
        summary=judgment.summary,
        text_only=deck.text_only,
        model_id=config.model_id,
        evaluated_at=evaluated_at,
        error="",
    )


class EvaluationError(Exception):
    """The runner could not score a row."""


def _failed(
    status: str,
    reason: str,
    model_id: str,
    evaluated_at: str | None = None,
    text_only: bool | None = None,
) -> EvaluationRecord:
    return EvaluationRecord(
        status=status,
        total=None,
        scores={},
        justifications={},
        summary="",
        text_only=text_only,
        model_id=model_id,
        evaluated_at=evaluated_at or _now(),
        error=reason,
    )


def _load_priors(config: RunConfig) -> dict[str, dict[str, str]]:
    if not config.resume or not config.output_path.is_file():
        return {}
    frame = read_csv(config.output_path)
    priors: dict[str, dict[str, str]] = {}
    for raw in frame.to_dict(orient="records"):
        row = {str(key): "" if value is None else str(value) for key, value in raw.items()}
        regn_id = row.get(REGN_ID, "").strip()
        if regn_id:
            priors[regn_id] = row
    return priors


def _flush(rows: list[dict[str, str]], columns: list[str], config: RunConfig) -> None:
    normalized = [{column: row.get(column, "") for column in columns} for row in rows]
    frame = pd.DataFrame(normalized, columns=columns)
    write_csv(frame, config.output_path)
    if config.s3_output:
        upload_s3(config.output_path, config.s3_output, config.region)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
