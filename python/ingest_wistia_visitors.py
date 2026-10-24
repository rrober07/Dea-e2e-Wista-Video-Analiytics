
import json
import uuid
import logging
import time
from datetime import datetime, timezone

import boto3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

AWS_PROFILE = "wistia-dev"
AWS_REGION = "us-east-1"
SECRET_ID = "wistia/dev/api-token"
S3_BUCKET = "wistia-video-analytics-dev"

VISITORS_URL = (
    "https://api.wistia.com/modern/stats/visitors"
)

PAGE_SIZE = 100
MAX_PAGES = 20

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


def get_aws_clients():
    session = boto3.Session(
        profile_name=AWS_PROFILE,
        region_name=AWS_REGION
    )

    return (
        session.client("secretsmanager"),
        session.client("s3")
    )


def get_api_token(secrets_client):
    response = secrets_client.get_secret_value(
        SecretId=SECRET_ID
    )

    secret = json.loads(response["SecretString"])
    return secret["WISTIA_API_TOKEN"]


def create_http_session(token):
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

    adapter = HTTPAdapter(max_retries=retry)
    http.mount("https://", adapter)

    return http


def fetch_visitor_page(http, page):
    response = http.get(
        VISITORS_URL,
        params={
            "page": page,
            "per_page": PAGE_SIZE
        },
        timeout=30
    )

    response.raise_for_status()
    return response.json()


def extract_records(payload):
    # Wistia list responses are expected to be arrays.
    # Handle common wrapped-array formats defensively.
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("visitors", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

    raise ValueError(
        "Unexpected visitor response format. "
        "Inspect the API response structure."
    )


def save_page(s3, page, records, run_id):
    now = datetime.now(timezone.utc)
    ingestion_date = now.strftime("%Y-%m-%d")

    key = (
        "bronze/visitors/"
        f"ingestion_date={ingestion_date}/"
        f"run_id={run_id}/"
        f"page_{page:05d}.json"
    )

    document = {
        "_metadata": {
            "source": "wistia",
            "dataset": "visitors",
            "page": page,
            "record_count": len(records),
            "run_id": run_id,
            "ingestion_timestamp": now.isoformat()
        },
        "data": records
    }

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(document).encode("utf-8"),
        ContentType="application/json"
    )

    logger.info(
        "Saved page=%s records=%s",
        page,
        len(records)
    )


def main():
    secrets_client, s3 = get_aws_clients()
    token = get_api_token(secrets_client)
    http = create_http_session(token)

    run_id = str(uuid.uuid4())
    total_records = 0
    total_pages = 0

    logger.info("Starting visitor ingestion")
    logger.info("Run ID: %s", run_id)

    try:
        for page in range(1, MAX_PAGES + 1):
            logger.info("Fetching visitor page %s", page)

            payload = fetch_visitor_page(http, page)
            records = extract_records(payload)

            if not records:
                logger.info("No more visitor records")
                break

            save_page(s3, page, records, run_id)

            total_records += len(records)
            total_pages += 1

            if len(records) < PAGE_SIZE:
                logger.info("Reached final page")
                break

            time.sleep(0.2)
        else:
            logger.warning(
                "Reached maximum page limit (%s). "
                "There may be more visitor records to fetch.",
                MAX_PAGES
            )
    finally:
        http.close()

    logger.info("Visitor ingestion completed")
    logger.info("Pages saved: %s", total_pages)
    logger.info("Total visitors: %s", total_records)


if __name__ == "__main__":
    main()
