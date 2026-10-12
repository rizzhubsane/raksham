"""Local CSV and optional S3 reads and writes."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import boto3
import pandas as pd
from botocore.exceptions import ClientError


class StorageError(ValueError):
    """The input or output location could not be used."""


def read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise StorageError(f"Input CSV not found: {path}")
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (OSError, pd.errors.ParserError, UnicodeError) as exc:
        raise StorageError(f"Could not read CSV: {path.name}") from exc
    return frame


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
    temporary.replace(path)


def parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise StorageError(f"Expected an s3://bucket/key URI, got: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def download_s3(uri: str, dest: Path, region: str | None) -> None:
    bucket, key = parse_s3_uri(uri)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _client(region).download_file(bucket, key, str(dest))


def download_s3_if_exists(uri: str, dest: Path, region: str | None) -> bool:
    """Download an object. Return False when the key is missing."""
    bucket, key = parse_s3_uri(uri)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _client(region).download_file(bucket, key, str(dest))
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
            return False
        raise
    return True


def upload_s3(src: Path, uri: str, region: str | None) -> None:
    bucket, key = parse_s3_uri(uri)
    _client(region).upload_file(str(src), bucket, key)


def _client(region: str | None):
    kwargs = {}
    if region:
        kwargs["region_name"] = region
    return boto3.client("s3", **kwargs)
