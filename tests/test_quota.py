from datetime import UTC, date, datetime

from app.services.quota import DailyQuota, seconds_until_utc_midnight


class FakeCalendar:
    def __init__(self, day: date) -> None:
        self.day = day

    def today(self) -> date:
        return self.day


def test_allows_up_to_the_limit_and_then_blocks() -> None:
    quota = DailyQuota(limit_per_day=2)

    assert quota.try_consume("me") is True
    assert quota.try_consume("me") is True
    assert quota.try_consume("me") is False


def test_each_key_has_its_own_quota() -> None:
    quota = DailyQuota(limit_per_day=1)

    assert quota.try_consume("me") is True
    assert quota.try_consume("tester") is True
    assert quota.try_consume("me") is False


def test_quota_resets_on_a_new_utc_day() -> None:
    calendar = FakeCalendar(date(2026, 11, 23))
    quota = DailyQuota(limit_per_day=1, today=calendar.today)
    quota.try_consume("me")

    calendar.day = date(2026, 11, 24)

    assert quota.try_consume("me") is True


def test_refund_gives_back_one_use() -> None:
    quota = DailyQuota(limit_per_day=1)
    quota.try_consume("me")

    quota.refund("me")

    assert quota.try_consume("me") is True


def test_refund_never_goes_below_zero() -> None:
    quota = DailyQuota(limit_per_day=1)

    quota.refund("me")

    assert quota.try_consume("me") is True
    assert quota.try_consume("me") is False


def test_seconds_until_utc_midnight() -> None:
    assert seconds_until_utc_midnight(datetime(2026, 11, 23, 23, 0, 0, tzinfo=UTC)) == 3600
    assert seconds_until_utc_midnight(datetime(2026, 11, 23, 0, 0, 0, tzinfo=UTC)) == 86_400
