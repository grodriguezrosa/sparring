import math
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta


def _utc_today() -> date:
    return datetime.now(UTC).date()


class DailyQuota:
    """Counts uses per key and per UTC day, in memory.

    Good enough for a single backend instance; counts are lost on restart.
    Moves to Postgres in phase 1.
    """

    def __init__(self, *, limit_per_day: int, today: Callable[[], date] = _utc_today) -> None:
        self._limit = limit_per_day
        self._today = today
        self._day = today()
        self._used: dict[str, int] = {}

    def try_consume(self, key: str) -> bool:
        """Use one unit for `key` if it has any left today. Return whether it was allowed."""
        self._start_new_day_if_needed()
        used = self._used.get(key, 0)
        if used >= self._limit:
            return False
        self._used[key] = used + 1
        return True

    def refund(self, key: str) -> None:
        """Give back one unit, e.g. when the operation failed for reasons outside the user."""
        self._start_new_day_if_needed()
        if self._used.get(key, 0) > 0:
            self._used[key] -= 1

    def _start_new_day_if_needed(self) -> None:
        today = self._today()
        if today != self._day:
            self._day = today
            self._used.clear()


def seconds_until_utc_midnight(now: datetime | None = None) -> int:
    """Seconds until the quotas reset. Used for the Retry-After header."""
    now = now or datetime.now(UTC)
    next_midnight = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=UTC)
    return math.ceil((next_midnight - now).total_seconds())
