from datetime import datetime, timedelta, time
from typing import Optional

SCAN_TIMES = (time(9, 20), time(12, 15), time(15, 0))
SCAN_TIME_STRINGS = ("09:20", "12:15", "15:00")
# 8 days = one full week plus a day buffer to always reach the next weekday slot.
MAX_LOOKAHEAD_DAYS = 8


def is_weekday(now: datetime) -> bool:
    return now.weekday() <= 4


def is_scheduled_scan_time(now: datetime) -> bool:
    current = now.replace(second=0, microsecond=0).time()
    return is_weekday(now) and current in SCAN_TIMES


def seconds_to_next_scan(now: datetime) -> int:
    target: Optional[datetime] = None
    baseline = now.replace(second=0, microsecond=0)
    for day_offset in range(0, MAX_LOOKAHEAD_DAYS):
        candidate_day = baseline + timedelta(days=day_offset)
        if candidate_day.weekday() > 4:
            continue
        for scan_time in SCAN_TIMES:
            candidate = candidate_day.replace(
                hour=scan_time.hour,
                minute=scan_time.minute,
                second=0,
                microsecond=0,
            )
            if candidate > now and (target is None or candidate < target):
                target = candidate
    if target is None:
        fallback_day = baseline + timedelta(days=1)
        while fallback_day.weekday() > 4:
            fallback_day += timedelta(days=1)
        target = fallback_day.replace(hour=SCAN_TIMES[0].hour, minute=SCAN_TIMES[0].minute)
    wait = int((target - now).total_seconds())
    return max(wait, 1)


def register_weekday_scan_jobs(schedule_module, job_func):
    jobs = []
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday")
    for weekday in weekdays:
        weekday_scheduler = getattr(schedule_module.every(), weekday)
        for scan_time in SCAN_TIME_STRINGS:
            jobs.append(weekday_scheduler.at(scan_time).do(job_func))
    return jobs
