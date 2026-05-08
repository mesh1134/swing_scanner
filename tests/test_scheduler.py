import unittest
from datetime import datetime

from swing_scanner.scheduler import (
    is_scheduled_scan_time,
    register_weekday_scan_jobs,
    seconds_to_next_scan,
)


class _FakeJobBuilder:
    def __init__(self, registry, weekday):
        self.registry = registry
        self.weekday = weekday

    def at(self, value):
        self.value = value
        return self

    def do(self, job_func):
        entry = (self.weekday, self.value)
        self.registry.append(entry)
        self.job_func = job_func
        return entry


class _FakeEvery:
    def __init__(self, registry):
        self.registry = registry

    def __getattr__(self, attr_name):
        return _FakeJobBuilder(self.registry, attr_name)


class _FakeSchedule:
    def __init__(self):
        self.registry = []

    def every(self):
        return _FakeEvery(self.registry)


class SchedulerTests(unittest.TestCase):
    def test_scheduled_scan_time_match(self):
        self.assertTrue(is_scheduled_scan_time(datetime(2026, 5, 8, 9, 20, 0)))

    def test_scheduled_scan_time_weekend(self):
        self.assertFalse(is_scheduled_scan_time(datetime(2026, 5, 9, 9, 20, 0)))

    def test_seconds_to_next_scan(self):
        now = datetime(2026, 5, 8, 10, 7, 30)
        self.assertEqual(seconds_to_next_scan(now), 7650)

    def test_register_weekday_jobs(self):
        fake_schedule = _FakeSchedule()
        jobs = register_weekday_scan_jobs(fake_schedule, lambda: None)
        self.assertEqual(len(jobs), 15)
        self.assertIn(("monday", "09:20"), fake_schedule.registry)
        self.assertIn(("friday", "15:00"), fake_schedule.registry)


if __name__ == "__main__":
    unittest.main()
