"""Typed interview in the terminal, through the real voice agent (text turns, no microphone).

It goes through the whole real chain: our API (profile, plan, voice session) -> ElevenLabs
agent -> our custom LLM endpoint (tunnel) -> DeepSeek. Useful before the frontend exists.
Needs `make dev`, `make tunnel` and `make agent-config URL=...` first. Each run uses one
conversation of the agent's daily limit.

    uv run python -m scripts.text_interview                      # sample offer + CV
    uv run python -m scripts.text_interview --offer my_offer.txt --cv my_cv.txt
    uv run python -m scripts.text_interview --plan backups/last-plan.json
    uv run python -m scripts.text_interview --say "Sí, te oigo" --say "..."   # non-interactive
"""

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import websockets

from app.config import get_settings

SAMPLE_OFFER = Path("tests/fixtures/job_offer_python.txt")
SAMPLE_CV = Path("tests/fixtures/sample_cv.txt")
LAST_PLAN = Path("backups/last-plan.json")
REPLY_TIMEOUT_S = 60
QUIT_WORDS = {"", "salir", "exit", "quit"}


def build_plan(api: httpx.Client, offer: Path, cv: Path) -> dict[str, Any]:
    print("Analysing the job offer and the CV, then planning the interview (~25 s)...")
    profile = api.post(
        "/profile",
        json={"job_offer": offer.read_text(encoding="utf-8"), "cv": cv.read_text(encoding="utf-8")},
    )
    profile.raise_for_status()
    plan = api.post("/interview-plan", json={"profile": profile.json()})
    plan.raise_for_status()
    data: dict[str, Any] = plan.json()
    LAST_PLAN.parent.mkdir(exist_ok=True)
    LAST_PLAN.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Plan saved to {LAST_PLAN} (reuse it with --plan)")
    return data


async def next_agent_reply(ws: websockets.ClientConnection) -> str | None:
    """Wait for the agent's next full reply, answering pings meanwhile. None if it hung up."""
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=REPLY_TIMEOUT_S)
        except (TimeoutError, websockets.ConnectionClosed):
            return None
        event = json.loads(raw)
        if event.get("type") == "ping":
            await ws.send(json.dumps({"type": "pong", "event_id": event["ping_event"]["event_id"]}))
        elif event.get("type") == "agent_response":
            reply: str = event["agent_response_event"]["agent_response"]
            return reply


async def talk(signed_url: str, scripted: list[str] | None) -> None:
    """Interactive if `scripted` is None; otherwise send those answers and stop."""
    async with websockets.connect(signed_url, open_timeout=15) as ws:
        await ws.send(json.dumps({"type": "conversation_initiation_client_data"}))
        sent_at = time.perf_counter()
        while True:
            reply = await next_agent_reply(ws)
            if reply is None:
                print("\n[the conversation ended]")
                return
            # Time from our message to the agent's full reply text (no audio in text turns).
            print(f"\nMateo ({time.perf_counter() - sent_at:.1f} s): {reply}")
            if scripted is None:
                answer = (await asyncio.to_thread(input, "Tú: ")).strip()
            elif scripted:
                answer = scripted.pop(0)
                print(f"Tú: {answer}")
            else:
                return
            if answer.lower() in QUIT_WORDS:
                return
            await ws.send(json.dumps({"type": "user_message", "text": answer}))
            sent_at = time.perf_counter()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Typed interview through the real voice agent.")
    parser.add_argument("--api", default="http://localhost:8000", help="our backend")
    parser.add_argument("--offer", type=Path, default=SAMPLE_OFFER)
    parser.add_argument("--cv", type=Path, default=SAMPLE_CV)
    parser.add_argument("--plan", type=Path, help="reuse a plan JSON instead of generating one")
    parser.add_argument("--say", action="append", default=[], help="scripted answers, in order")
    args = parser.parse_args(argv)

    code = get_settings().access_codes[0].get_secret_value()
    with httpx.Client(base_url=args.api, headers={"X-Access-Code": code}, timeout=120) as api:
        if args.plan:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
        else:
            plan = build_plan(api, args.offer, args.cv)
        session = api.post("/voice-session", json={"plan": plan})
        if session.is_error:
            print(f"Could not start the voice session: HTTP {session.status_code} {session.text}")
            return 1
    titles = ", ".join(topic["title"] for topic in plan["topics"])
    print(f"Plan: {plan['duration_minutes']} min, topics: {titles}")
    print("Type your answers; an empty line ends the interview.")

    asyncio.run(talk(session.json()["signed_url"], list(args.say) if args.say else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
