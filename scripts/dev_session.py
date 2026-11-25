"""Time-limited voice development session: backend + tunnel + agent config, then auto-stop.

    make voice-dev                     # stops by itself after 30 minutes
    make voice-dev MINUTES=60

It starts the backend and a cloudflared tunnel, points the ElevenLabs agent at the tunnel,
and waits. It stops both processes when the time limit is reached, on Ctrl+C, on a
terminal hang-up, or if either process dies. Nothing is left running in the background.
"""

import argparse
import io
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from datetime import datetime, timedelta
from types import FrameType

import httpx

from scripts import configure_agent

PORT = 8000
LOCAL_URL = f"http://localhost:{PORT}"
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
DEFAULT_MINUTES = 30
MAX_MINUTES = 120  # hard ceiling: a forgotten session can never run for hours
STARTUP_TIMEOUT_S = 40
TUNNEL_READY = "Registered tunnel connection"
# Ask for the tunnel hostname too early and macOS caches "does not exist" for a while,
# so we wait until cloudflared says the tunnel is registered, plus a margin.
DNS_MARGIN_S = 5


class Stop(Exception):
    """Raised by the signal handler to leave the wait loop."""


def find_tunnel_url(line: str) -> str | None:
    match = TUNNEL_URL.search(line)
    return match.group(0) if match else None


def check_minutes(minutes: int) -> int:
    if not 1 <= minutes <= MAX_MINUTES:
        raise ValueError(f"minutes must be between 1 and {MAX_MINUTES}")
    return minutes


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_until_healthy(url: str, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/health", timeout=3).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def stop_all(processes: Sequence[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Time-limited voice development session.")
    parser.add_argument("--minutes", type=int, default=DEFAULT_MINUTES)
    args = parser.parse_args(argv)
    minutes = check_minutes(args.minutes)
    # Print each line as it happens, also when the output goes to a file or a pipe.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)

    if port_in_use(PORT):
        print(f"Port {PORT} is already in use: is another session running? Stop it first:")
        print('  pkill -f "uvicorn app.main:app"; pkill -f "cloudflared tunnel"')
        return 1

    def on_signal(_signum: int, _frame: FrameType | None) -> None:
        raise Stop

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, on_signal)

    processes: list[subprocess.Popen[str]] = []
    try:
        backend = subprocess.Popen(  # noqa: S603  (fixed command)
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--port",
                str(PORT),
                "--log-level",
                "warning",
            ],
            text=True,
        )
        processes.append(backend)
        if not wait_until_healthy(LOCAL_URL, STARTUP_TIMEOUT_S):
            print("The backend did not start.")
            return 1

        tunnel = subprocess.Popen(  # noqa: S603  (fixed command)
            ["cloudflared", "tunnel", "--no-autoupdate", "--url", LOCAL_URL],  # noqa: S607
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        processes.append(tunnel)
        found: list[str] = []
        registered = threading.Event()

        def read_tunnel_output() -> None:
            # Keep draining the pipe for the tunnel's whole life, or it would block.
            if tunnel.stdout is None:
                return
            for line in tunnel.stdout:
                url = find_tunnel_url(line)
                if url and not found:
                    found.append(url)
                if TUNNEL_READY in line:
                    registered.set()

        threading.Thread(target=read_tunnel_output, daemon=True).start()
        if not registered.wait(STARTUP_TIMEOUT_S) or not found:
            print("The tunnel did not come up.")
            return 1
        time.sleep(DNS_MARGIN_S)
        if not wait_until_healthy(found[0], STARTUP_TIMEOUT_S):
            print("The tunnel did not come up.")
            return 1

        if configure_agent.main(["--llm-url", found[0]]) != 0:
            print("Could not configure the agent.")
            return 1

        stop_at = datetime.now() + timedelta(minutes=minutes)
        print(f"\nReady. Tunnel: {found[0]}")
        print(f"Stops automatically at {stop_at:%H:%M} ({minutes} min). Ctrl+C stops it now.")
        end = time.monotonic() + minutes * 60
        while time.monotonic() < end:
            if any(process.poll() is not None for process in processes):
                print("A process died: stopping the session.")
                return 1
            time.sleep(1)
        print("Time limit reached.")
        return 0
    except Stop:
        print("\nStopping...")
        return 0
    finally:
        stop_all(processes)
        print(
            "Backend and tunnel stopped. The agent points at a dead tunnel until the next session."
        )


if __name__ == "__main__":
    sys.exit(main())
