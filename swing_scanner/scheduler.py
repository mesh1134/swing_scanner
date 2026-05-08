from datetime import datetime, timedelta, time


MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def is_market_hours(now: datetime) -> bool:
    if now.weekday() > 4:
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def seconds_to_next_quarter(now: datetime) -> int:
    next_mark = ((now.minute // 15) + 1) * 15
    if next_mark >= 60:
        target = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        target = now.replace(minute=next_mark, second=0, microsecond=0)
    wait = int((target - now).total_seconds())
    return max(wait, 1)
