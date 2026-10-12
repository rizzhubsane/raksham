#!/usr/bin/env python3
"""Score pitch-deck submissions with Amazon Bedrock and write the results to CSV."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path

from botocore.exceptions import BotoCoreError, NoCredentialsError

from deckeval.judge import bedrock_client, resolve_model_id
from deckeval.privacy import public_error
from deckeval.rubric import RubricError, load_rubric
from deckeval.runner import RunConfig, run
from deckeval.storage import StorageError, download_s3, download_s3_if_exists

DEFAULT_RUBRIC = Path(__file__).resolve().parent / "rubric.yaml"
logger = logging.getLogger("eval_decks")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate pitch-deck submissions with Amazon Bedrock and write scores to CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python eval_decks.py --input sample_input.csv --output results.csv --dry-run --limit 1\n"
            "  python eval_decks.py --input submissions.csv --output results.csv --workers 5\n"
            "  python eval_decks.py --input submissions.csv --output results.csv --resume\n"
            "  python eval_decks.py --s3-input s3://bucket/submissions.csv "
            "--s3-output s3://bucket/results.csv --output results.csv\n"
        ),
    )
    parser.add_argument("--input", help="Local CSV of submissions")
    parser.add_argument("--output", help="Local CSV to write")
    parser.add_argument("--rubric", default=str(DEFAULT_RUBRIC), help="Path to rubric.yaml")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N rows")
    parser.add_argument("--resume", action="store_true", help="Skip rows already scored in the output")
    parser.add_argument("--dry-run", action="store_true", help="Download and extract only; do not call Bedrock")
    parser.add_argument("--workers", type=int, default=5, help="Concurrent submissions (default: 5)")
    parser.add_argument("--max-images", type=int, default=15, help="Maximum slide images sent to the model")
    parser.add_argument("--cache-dir", default=".cache", help="Directory for downloaded decks")
    parser.add_argument("--s3-input", help="s3://bucket/key CSV to read")
    parser.add_argument("--s3-output", help="s3://bucket/key CSV to write")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    try:
        _validate_args(args)
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    try:
        rubric = load_rubric(Path(args.rubric))
        needs_aws = bool(args.s3_input or args.s3_output or not args.dry_run)
        region = _region() if needs_aws else None
        if not args.dry_run and not region:
            logger.error("Set AWS_REGION, or set a default region with aws configure.")
            return 2
        input_path, output_path = _prepare_paths(args, region)
        client = None if args.dry_run else bedrock_client(region)
        summary = run(
            RunConfig(
                rubric=rubric,
                input_path=input_path,
                output_path=output_path,
                cache_dir=Path(args.cache_dir),
                workers=args.workers,
                resume=args.resume,
                dry_run=args.dry_run,
                limit=args.limit,
                model_id="" if args.dry_run else resolve_model_id(),
                max_images=args.max_images,
                client=client,
                s3_output=args.s3_output,
                region=region,
            )
        )
    except (RubricError, StorageError) as exc:
        logger.error("%s", exc)
        return 2
    except NoCredentialsError:
        logger.error("No AWS credentials found. Use an IAM role or run aws configure.")
        return 2
    except BotoCoreError as exc:
        logger.error("AWS request failed: %s", public_error(exc))
        return 2
    print(summary)
    return 0


def _validate_args(args: argparse.Namespace) -> None:
    if args.workers < 1:
        raise ValueError("--workers must be at least 1")
    if args.max_images < 1:
        raise ValueError("--max-images must be at least 1")
    if args.limit is not None and args.limit < 0:
        raise ValueError("--limit must be 0 or greater")


def _region() -> str | None:
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if region:
        return region
    try:
        import boto3

        return boto3.Session().region_name
    except Exception:
        return None


def _prepare_paths(args: argparse.Namespace, region: str | None) -> tuple[Path, Path]:
    if args.s3_input:
        input_path = Path(args.input) if args.input else Path(tempfile.mkdtemp(prefix="eval-decks-")) / "input.csv"
        download_s3(args.s3_input, input_path, region)
    elif args.input:
        input_path = Path(args.input)
    else:
        raise StorageError("Provide --input or --s3-input")

    if args.output:
        output_path = Path(args.output)
    elif args.s3_output:
        output_path = Path(tempfile.mkdtemp(prefix="eval-decks-")) / "output.csv"
    else:
        raise StorageError("Provide --output or --s3-output")

    if args.resume and args.s3_output and not output_path.exists():
        download_s3_if_exists(args.s3_output, output_path, region)
    return input_path, output_path


if __name__ == "__main__":
    raise SystemExit(main())
