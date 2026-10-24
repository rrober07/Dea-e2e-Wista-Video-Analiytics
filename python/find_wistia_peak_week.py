
import json
import logging
from collections import defaultdict
from datetime import date, timedelta

import boto3
import requests

AWS_PROFILE = "wistia-dev"
AWS_REGION = "us-east-1"
SECRET_ID = "wistia/dev/api-token"

MEDIA_IDS = ["8hunphufxp", "9k4tbcdfg0"]

START_DATE = date(2026, 4, 1)
END_DATE = date(2026, 9, 30)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


def get_token():
    session = boto3.Session(
        profile_name=AWS_PROFILE,
        region_name=AWS_REGION
    )

    response = session.client(
        "secretsmanager"
    ).get_secret_value(
        SecretId=SECRET_ID
    )

    return json.loads(
        response["SecretString"]
    )["WISTIA_API_TOKEN"]


def fetch_daily_stats(media_id, token):
    url = (
        "https://api.wistia.com/modern/stats/medias/"
        f"{media_id}/by_date"
    )

    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "X-Wistia-API-Version": "2026-09"
        },
        params={
            "start_date": START_DATE.isoformat(),
            "end_date": END_DATE.isoformat()
        },
        timeout=60
    )

    response.raise_for_status()
    return response.json()


def main():
    token = get_token()

    daily = defaultdict(
        lambda: {
            "play_count": 0,
            "load_count": 0,
            "hours_watched": 0.0
        }
    )

    for media_id in MEDIA_IDS:
        records = fetch_daily_stats(media_id, token)

        logger.info(
            "Media %s returned %s daily records",
            media_id,
            len(records)
        )

        for record in records:
            day = record["date"]

            daily[day]["play_count"] += int(
                record.get("play_count") or 0
            )
            daily[day]["load_count"] += int(
                record.get("load_count") or 0
            )
            daily[day]["hours_watched"] += float(
                record.get("hours_watched") or 0
            )

    results = []

    current = START_DATE
    last_start = END_DATE - timedelta(days=6)

    while current <= last_start:
        plays = 0
        loads = 0
        hours = 0.0

        for offset in range(7):
            day = (
                current + timedelta(days=offset)
            ).isoformat()

            plays += daily[day]["play_count"]
            loads += daily[day]["load_count"]
            hours += daily[day]["hours_watched"]

        results.append({
            "start": current,
            "end": current + timedelta(days=6),
            "plays": plays,
            "loads": loads,
            "hours": hours
        })

        current += timedelta(days=1)

    results.sort(
        key=lambda item: (
            item["plays"],
            item["hours"]
        ),
        reverse=True
    )

    print("\nTOP 10 HISTORICAL SEVEN-DAY WINDOWS")
    print("-" * 75)

    for rank, item in enumerate(results[:10], start=1):
        print(
            f"{rank:2}. "
            f"{item['start']} to {item['end']} | "
            f"Plays: {item['plays']:6} | "
            f"Loads: {item['loads']:6} | "
            f"Hours: {item['hours']:.2f}"
        )

    if results:
        best = results[0]

        print("\nRECOMMENDED HISTORICAL WINDOW")
        print(f"Start date: {best['start']}")
        print(f"End date:   {best['end']}")
        print(f"Total plays: {best['plays']}")


if __name__ == "__main__":
    main()
