import subprocess
import sys

import pytest

from scripts.dev_session import MAX_MINUTES, check_minutes, find_tunnel_url, stop_all


def test_finds_the_tunnel_url_in_cloudflared_output() -> None:
    line = "2026-11-23T08:17:20Z INF |  https://abc-def-123.trycloudflare.com  |"

    assert find_tunnel_url(line) == "https://abc-def-123.trycloudflare.com"
    assert find_tunnel_url("INF Starting tunnel") is None


@pytest.mark.parametrize("minutes", [0, -5, MAX_MINUTES + 1])
def test_rejects_durations_outside_the_limits(minutes: int) -> None:
    with pytest.raises(ValueError, match="between 1 and"):
        check_minutes(minutes)


def test_accepts_durations_within_the_limits() -> None:
    assert check_minutes(30) == 30
    assert check_minutes(MAX_MINUTES) == MAX_MINUTES


def test_stop_all_ends_running_processes() -> None:
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], text=True)

    stop_all([sleeper])

    assert sleeper.poll() is not None
