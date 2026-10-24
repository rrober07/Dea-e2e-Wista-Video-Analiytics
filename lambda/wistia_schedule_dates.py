from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("America/Chicago")


def get_processing_dates(now=None):
    if now is None:
        now = datetime.now(timezone.utc)

    local_date = now.astimezone(TIMEZONE).date()
    processing_date = local_date - timedelta(days=1)

    return {
        "start_date": processing_date.isoformat(),
        "end_date": processing_date.isoformat()
    }


if __name__ == "__main__":
    test_cases = [
        ("2026-10-25T07:00:00+00:00", "2026-10-24"),
        ("2026-11-02T08:00:00+00:00", "2026-11-01"),
        ("2027-03-15T07:00:00+00:00", "2027-03-14"),
    ]

    for timestamp, expected in test_cases:
        result = get_processing_dates(
            datetime.fromisoformat(timestamp)
        )

        assert result["start_date"] == expected
        assert result["end_date"] == expected

        print(f"PASS: {timestamp} -> {result['start_date']}")

    print("\nSUCCESS: Daily date calculation verified.")
