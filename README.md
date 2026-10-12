# Deck evaluation CLI

`eval_decks.py` reads a CSV of pitch-deck submissions, downloads each `.pptx`, and asks Amazon Bedrock to score it against `rubric.yaml`. The weighted total and the rank are computed in code. The model never supplies the total.

Candidate names and emails are not written to the log. Progress lines use Regn ID only. The model sees slide text and slide images, not the identity columns.

## Setup

Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Credentials use the default boto3 chain: an EC2 or Lambda IAM role, or a local profile from `aws configure`. Do not put access keys in the code or in the CSV.

```bash
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-5-5
```

`BEDROCK_MODEL_ID` defaults to `global.anthropic.claude-sonnet-5-5` (Claude Sonnet, global inference profile). The Converse call still goes to the Bedrock endpoint in `AWS_REGION`. If that profile is not enabled on the account, set `BEDROCK_MODEL_ID` to a model ID shown in the Bedrock console, for example `anthropic.claude-sonnet-4-6` or `us.anthropic.claude-sonnet-4-6`.

## Enable the model

1. Open the Amazon Bedrock console in the same Region as `AWS_REGION`.
2. Open **Model catalog** (older consoles call this **Model access**).
3. Find the Claude Sonnet model you set in `BEDROCK_MODEL_ID` and enable it.
4. The first Anthropic model on an account asks for a short use-case form. Submit it and wait until access shows as granted.
5. Confirm the model ID or inference profile ID in the console matches `BEDROCK_MODEL_ID`.

## IAM

Attach this to the role that runs the tool. `bedrock:InvokeModel` is what authorizes the Converse API. `bedrock:Converse` is included as well.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ScoreDecks",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:Converse"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
        "arn:aws:bedrock:*:*:inference-profile/*"
      ]
    }
  ]
}
```

Add S3 only when you pass `--s3-input` or `--s3-output`. Narrow the bucket ARNs to the real paths.

```json
{
  "Sid": "ReadSubmissions",
  "Effect": "Allow",
  "Action": ["s3:GetObject"],
  "Resource": "arn:aws:s3:::your-bucket/path/submissions.csv"
}
```

```json
{
  "Sid": "WriteResults",
  "Effect": "Allow",
  "Action": ["s3:PutObject"],
  "Resource": "arn:aws:s3:::your-bucket/path/results.csv"
}
```

`--resume` from S3 also needs `s3:GetObject` on the output key so an existing results file can be downloaded.

## LibreOffice and poppler

Slide images are produced by converting the deck to PDF with LibreOffice headless, then rendering PDF pages with poppler (`pdf2image`). If either tool is missing, that row is still scored from extracted text and `text_only` is `true`.

Amazon Linux 2023:

```bash
sudo dnf install -y libreoffice poppler-utils
```

Amazon Linux 2:

```bash
sudo amazon-linux-extras install libreoffice -y
sudo yum install -y poppler-utils
```

Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y libreoffice poppler-utils
```

Check the binaries:

```bash
soffice --version
pdftoppm -v
```

Install the Impress component if `soffice` converts the deck to an empty PDF. On Ubuntu that is the `libreoffice` package above. On Amazon Linux, install `libreoffice-impress` as well if it is packaged separately.

## Run

From the repository root:

```bash
python eval_decks.py \
  --input sample_input.csv \
  --output results.csv \
  --dry-run \
  --limit 1

python eval_decks.py \
  --input submissions.csv \
  --output results.csv \
  --workers 5

python eval_decks.py \
  --input submissions.csv \
  --output results.csv \
  --resume \
  --workers 8

python eval_decks.py \
  --s3-input s3://your-bucket/round1/submissions.csv \
  --s3-output s3://your-bucket/round1/results.csv \
  --output results.csv \
  --workers 5
```

| Flag | Meaning |
| --- | --- |
| `--input`, `--output` | Local CSV paths. One of `--input` / `--s3-input` is required, and one of `--output` / `--s3-output`. |
| `--rubric` | Rubric YAML. Defaults to `rubric.yaml` next to the script. |
| `--limit N` | Process only the first N rows. |
| `--resume` | Skip a Regn ID that already has `status=scored` in the output file. Ranks are recomputed. |
| `--dry-run` | Download and extract only. No Bedrock call. |
| `--workers` | Parallel submissions. Default 5. LibreOffice itself runs one conversion at a time. |
| `--max-images` | Slide images sent to the model. Default 15, and the request stays under about 8 MB. |
| `--cache-dir` | Download and extract cache. Default `.cache/`, keyed by a hash of the deck URL. |
| `--s3-input`, `--s3-output` | Read or write the CSV on S3. |

A blank cell, `-`, or a non-HTTP value in `Q1: Submit Round 1 Deck` is `download_failed`. Downloads use a connect/read timeout and up to 3 retries with exponential backoff. HTTP 408, 429, and 5xx are retried. The output CSV is rewritten as each row finishes, so `--resume` can continue after an interruption.

Bedrock throttling waits with exponential backoff. If the model returns JSON that does not match the schema, the error is sent back and the call is retried up to 2 more times. A row that still fails is `eval_failed`. Temperature is 0.

## Rubric

`rubric.yaml` is a list of criteria. Each one has `name`, `description`, `weight`, and a `scoring_guide` with keys `0-3`, `4-6`, and `7-10`. Weights must sum to 1.0 or the process exits before it reads the CSV.

The shipped file is a placeholder:

| Criterion | Weight |
| --- | --- |
| Problem clarity | 0.20 |
| Solution and innovation | 0.25 |
| Market and impact | 0.20 |
| Feasibility and execution plan | 0.20 |
| Presentation quality | 0.15 |

The total is `sum(score × weight)` on a 0–10 scale, rounded half-up to one decimal. Rank 1 is the highest score. Ties share a rank and the next rank skips (1, 2, 2, 4). Failed rows are left blank.

## Output

Every original column is kept. `Total Score (out of 10)` and `Rank` are filled in. Extra columns:

- `Score: <criterion>` and `Justification: <criterion>` for each rubric row
- `Overall summary`
- `status` (`scored`, `download_failed`, `eval_failed`, `dry_run`)
- `text_only` (`true` when slide images could not be rendered)
- `model_id`
- `evaluated_at` (UTC)
- `error` (a short reason with emails and URLs removed)

The process prints a summary with scored, failed download, failed eval, and dry-run counts, plus the score distribution.

## Tests

```bash
pytest
```

## Cache and failures

`.cache/<url-hash>/` stores the deck, extracted text, and rendered images. A failed render is not cached, so installing LibreOffice and rerunning will retry images. A failed download deletes a bad file so the next run can fetch it again.
