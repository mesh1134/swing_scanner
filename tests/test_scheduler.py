import unittest
from datetime import datetime

from swing_scanner.scheduler import is_market_hours, seconds_to_next_quarter


class SchedulerTests(unittest.TestCase):
    def test_market_hours_weekday(self):
        self.assertTrue(is_market_hours(datetime(2026, 5, 8, 10, 0, 0)))

    def test_market_hours_weekend(self):
        self.assertFalse(is_market_hours(datetime(2026, 5, 9, 10, 0, 0)))

    def test_seconds_to_next_quarter(self):
        now = datetime(2026, 5, 8, 10, 7, 30)
        self.assertEqual(seconds_to_next_quarter(now), 450)


if __name__ == "__main__":
    unittest.main()
