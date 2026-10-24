import os
import argparse
import json
import logging
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import boto3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

AWS_PROFILE = "wistia-dev"
AWS_REGION = "us-east-1"
SECRET_ID = "wistia/dev/api-token"
S3_BUCKET = "wistia-video-analytics-dev"

EVENTS_URL = "https://api.wistia.com/modern/stats/events"

MEDIA_IDS = ["8hunphufxp", "9k4tbcdfg0"]
PAGE_SIZE = 100
MAX_PAGES = 100

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)




def get_token():
    profile = os.getenv("AWS_PROFILE")

    if profile:
        session = boto3.Session(
            profile_name=profile,
            region_name=AWS_REGION
        )
    else:
        session = boto3.Session(
            region_name=AWS_REGION
        )

    secrets = session.client("secretsmanager")

    response = secrets.get_secret_value(
        SecretId=SECRET_ID
    )

    token = json.loads(
        response["SecretString"]
    )["WISTIA_API_TOKEN"]

    return session, token




def create_http(token):
    http = requests.Session()
    http.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-Wistia-API-Version": "2026-09"
    })
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True
    )
    http.mount("https://", HTTPAdapter(max_retries=retry))
    return http


def extract_records(payload):
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("events", "data", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]

    raise ValueError("Unexpected events API response structure")


def save_page(s3, media_id, start_date, end_date,
              page, payload, record_count, run_id):
    now = datetime.now(timezone.utc)

    key = (
        "bronze/viewing_events/"
        f"start_date={start_date}/"
        f"end_date={end_date}/"
        f"media_id={media_id}/"
        f"run_id={run_id}/"
        f"page_{page:05d}.json"
    )

    document = {
        "_metadata": {
            "source": "wistia",
            "dataset": "viewing_events",
            "media_id": media_id,
            "start_date": start_date,
            "end_date": end_date,
            "page": page,
            "record_count": record_count,
            "run_id": run_id,
            "ingestion_timestamp": now.isoformat()
        },
        "data": payload
    }

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(document).encode("utf-8"),
        ContentType="application/json"
    )

    logger.info(
        "Saved media=%s page=%s records=%s",
        media_id, page, record_count
    )


def ingest_media(http, s3, media_id,
                 start_date, end_date, run_id):
    total = 0

    for page in range(1, MAX_PAGES + 1):
        response = http.get(
            EVENTS_URL,
            params={
                "media_id": media_id,
                "start_date": start_date,
                "end_date": end_date,
                "page": page,
                "per_page": PAGE_SIZE
            },
            timeout=30
        )
        response.raise_for_status()

        payload = response.json()
        records = extract_records(payload)

        logger.info(
            "Media=%s page=%s events=%s",
            media_id, page, len(records)
        )

        if not records:
            return total, True

        save_page(
            s3, media_id, start_date, end_date,
            page, payload, len(records), run_id
        )

        total += len(records)

        if len(records) < PAGE_SIZE:
            return total, True

        time.sleep(0.2)

    logger.warning(
        "Media %s reached MAX_PAGES=%s; "
        "this extraction may be incomplete.",
        media_id, MAX_PAGES
    )
    return total, False


def write_completion_manifest(
    s3_client,
    bucket,
    start_date,
    end_date,
    run_id,
    total_events,
    media_results,
):
    """Write a success marker only after all media ingestion completes."""

    manifest = {
        "status": "SUCCEEDED",
        "dataset": "viewing_events",
        "start_date": start_date,
        "end_date": end_date,
        "run_id": run_id,
        "total_events": total_events,
        "media_results": media_results,
    }

    manifest_key = (
        "bronze/manifests/viewing_events/"
        f"start_date={start_date}/"
        f"end_date={end_date}/"
        f"run_id={run_id}.json"
    )

    s3_client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    print(f"Completion manifest written: s3://{bucket}/{manifest_key}")

    return manifest_key


def run_ingestion(start_date, end_date):
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    today = datetime.now(timezone.utc).date()

    if end < start or (end - start).days > 6:
        raise ValueError(
            "Specify 1 to 7 calendar days, inclusive."
        )

    if end >= today:
        raise ValueError(
            "Historical window must end before today."
        )

    if start < today - timedelta(days=730):
        raise ValueError(
            "Start date is outside the approximate "
            "2-year retention window."
        )

    aws_session, token = get_token()
    s3 = aws_session.client("s3")
    http = create_http(token)
    run_id = str(uuid.uuid4())

    results = []

    try:
        for media_id in MEDIA_IDS:
            logger.info(
                "Starting media=%s window=%s to %s",
                media_id, start, end
            )

            total, complete = ingest_media(
                http,
                s3,
                media_id,
                start.isoformat(),
                end.isoformat(),
                run_id
            )

            if not complete:
                raise RuntimeError(
                    f"Incomplete extraction for media_id={media_id}"
                )

            results.append({
                "media_id": media_id,
                "total_events": total,
                "complete": complete
            })


        manifest_key = write_completion_manifest(
            s3_client=s3,
            bucket=S3_BUCKET,
            start_date=start_date,
            end_date=end_date,
            run_id=run_id,
            total_events=sum(
                item["total_events"] for item in results
            ),
            media_results=results,
        )


    finally:
        http.close()


    return {
        "status": "SUCCEEDED",
        "run_id": run_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "total_events": sum(
            item["total_events"] for item in results
        ),
        "media_results": results,
        "manifest_key": manifest_key,
    }




def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--start-date",
        required=True
    )
    parser.add_argument(
        "--end-date",
        required=True
    )

    args = parser.parse_args()

    try:
        result = run_ingestion(
            args.start_date,
            args.end_date
        )
    except ValueError as exc:
        parser.error(str(exc))

    print(json.dumps(result, indent=2))


def lambda_handler(event, context):
    """
    AWS Lambda entry point.

    Expected event:
    {
        "start_date": "2026-10-20",
        "end_date": "2026-10-20"
    }
    """
    return run_ingestion(
        event["start_date"],
        event["end_date"]
    )


if __name__ == "__main__":
    main()
