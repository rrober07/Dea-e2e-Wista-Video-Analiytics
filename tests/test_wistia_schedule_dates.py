import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "lambda"),
)

from wistia_schedule_dates import get_processing_dates


class TestWistiaScheduleDates(unittest.TestCase):

    def check_processing_date(self, timestamp, expected):
        result = get_processing_dates(
            datetime.fromisoformat(timestamp)
        )

        self.assertEqual(
            result,
            {
                "start_date": expected,
                "end_date": expected,
            },
        )

    def test_normal_day(self):
        self.check_processing_date(
            "2026-10-25T07:00:00+00:00",
            "2026-10-24",
        )

    def test_month_boundary(self):
        self.check_processing_date(
            "2026-11-01T08:00:00+00:00",
            "2026-10-31",
        )

    def test_year_boundary(self):
        self.check_processing_date(
            "2027-01-01T09:00:00+00:00",
            "2026-12-31",
        )

    def test_daylight_saving_fall(self):
        self.check_processing_date(
            "2026-11-02T08:00:00+00:00",
            "2026-11-01",
        )

    def test_daylight_saving_spring(self):
        self.check_processing_date(
            "2027-03-15T07:00:00+00:00",
            "2027-03-14",
        )

    def test_utc_date_differs_from_central(self):
        self.check_processing_date(
            "2026-10-25T02:00:00+00:00",
            "2026-10-23",
        )


if __name__ == "__main__":
    unittest.main()
