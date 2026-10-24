
import json
import uuid
import logging
from datetime import datetime, timezone

import boto3
import requests

AWS_PROFILE = "wistia-dev"
AWS_REGION = "us-east-1"

SECRET_ID = "wistia/dev/api-token"
S3_BUCKET = "wistia-video-analytics-dev"

MEDIA_IDS = [
    "8hunphufxp",
    "9k4tbcdfg0"
]

session = boto3.Session(
    profile_name=AWS_PROFILE,
    region_name=AWS_REGION
)

secrets = session.client("secretsmanager")
s3 = session.client("s3")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger(__name__)


def get_api_token():
    response = secrets.get_secret_value(
        SecretId=SECRET_ID
    )

    secret = json.loads(response["SecretString"])
    return secret["WISTIA_API_TOKEN"]


def fetch_media_stats(media_id, token):
    url = (
        "https://api.wistia.com/v1/stats/medias/"
        f"{media_id}.json"
    )

    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        },
        timeout=30
    )

    response.raise_for_status()
    return response.json()


def fetch_media_metadata(media_id, token):
    url = (
        "https://api.wistia.com/modern/medias/"
        f"{media_id}"
    )

    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "X-Wistia-API-Version": "2026-09"
        },
        timeout=30
    )

    response.raise_for_status()
    return response.json()



def save_to_s3(dataset, media_id, payload, run_id):
    ingestion_timestamp = datetime.now(timezone.utc)
    ingestion_date = ingestion_timestamp.strftime("%Y-%m-%d")

    s3_key = (
        f"bronze/{dataset}/"
        f"ingestion_date={ingestion_date}/"
        f"run_id={run_id}/"
        f"media_id={media_id}.json"
    )

    record = {
        "_metadata": {
            "source": "wistia",
            "dataset": dataset,
            "media_id": media_id,
            "run_id": run_id,
            "ingestion_timestamp": ingestion_timestamp.isoformat()
        },
        "data": payload
    }

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=json.dumps(record).encode("utf-8"),
        ContentType="application/json"
    )

    logger.info(
        "Saved dataset=%s media_id=%s to s3://%s/%s",
        dataset,
        media_id,
        S3_BUCKET,
        s3_key
    )



def main():
    token = get_api_token()
    run_id = str(uuid.uuid4())

    for media_id in MEDIA_IDS:
        logger.info("Processing media_id=%s", media_id)

        logger.info("Fetching media stats")
        stats = fetch_media_stats(media_id, token)

        save_to_s3(
            dataset="media_stats",
            media_id=media_id,
            payload=stats,
            run_id=run_id
        )

        logger.info("Fetching media metadata")
        metadata = fetch_media_metadata(media_id, token)

        logger.info(
            "Metadata fields for %s: %s",
            media_id,
            list(metadata.keys())
        )

        save_to_s3(
            dataset="media_metadata",
            media_id=media_id,
            payload=metadata,
            run_id=run_id
        )

    logger.info(
        "Bronze ingestion completed. Run ID: %s",
        run_id
    )


if __name__ == "__main__":
    main()
