"""Spoken interview from the terminal: microphone and speakers, through the real voice agent.

Same chain as scripts/text_interview.py, but with real audio, so the latency is the one a
candidate actually gets. At the end it prints the latency report of this conversation.

    make dev ; make tunnel ; make agent-config URL=...      (see CLAUDE.md, Commands)
    uv run python -m scripts.voice_interview --plan backups/last-plan.json
    uv run python -m scripts.voice_interview --offer my_offer.txt --cv my_cv.txt

Use headphones: otherwise the microphone hears Mateo and he interrupts himself.
macOS asks for microphone permission for your terminal the first time.
Needs the `voice` dependency group (pyaudio): `brew install portaudio` once, and
`make voice-interview` installs the rest.
Ctrl+C ends the interview. Each run uses one conversation of the agent's daily limit.
"""

import argparse
import json
import signal
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from types import FrameType

import httpx
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface

from app.config import get_settings
from scripts import latency_report
from scripts.text_interview import SAMPLE_CV, SAMPLE_OFFER, build_plan

METRICS_DELAY_S = 8  # ElevenLabs stores the per-turn metrics a few seconds after the end


class PlannedConversation(Conversation):
    """The SDK conversation, but using the single-use signed URL from our /voice-session.

    The SDK would otherwise request its own signed URL, which no plan is bound to, and our
    custom LLM endpoint would refuse the conversation (404). `_get_signed_url` is private
    SDK API: if an SDK upgrade breaks this, check how it builds the WebSocket URL now.
    """

    def __init__(self, signed_url: str, **kwargs: object) -> None:
        self._our_signed_url = signed_url
        super().__init__(**kwargs)  # type: ignore[arg-type]

    def _get_signed_url(self) -> str:
        return self._our_signed_url


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Spoken interview through the real agent.")
    parser.add_argument("--api", default="http://localhost:8000", help="our backend")
    parser.add_argument("--offer", type=Path, default=SAMPLE_OFFER)
    parser.add_argument("--cv", type=Path, default=SAMPLE_CV)
    parser.add_argument("--plan", type=Path, help="reuse a plan JSON instead of generating one")
    args = parser.parse_args(argv)

    settings = get_settings()
    code = settings.access_codes[0].get_secret_value()
    with httpx.Client(base_url=args.api, headers={"X-Access-Code": code}, timeout=120) as api:
        if args.plan:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
        else:
            plan = build_plan(api, args.offer, args.cv)
        try:
            session = api.post("/voice-session", json={"plan": plan})
        except httpx.ConnectError:
            print(f"The backend at {args.api} is not running. Start `make voice-dev` first,")
            print("wait for 'Ready', and run this again in another terminal.")
            return 1
        if session.is_error:
            print(f"Could not start the voice session: HTTP {session.status_code} {session.text}")
            return 1
    conversation_id = session.json()["conversation_id"]

    conversation = PlannedConversation(
        session.json()["signed_url"],
        # The SDK requires a client, but never uses it: the signed URL comes from our API,
        # so the real ElevenLabs key is not needed here.
        client=ElevenLabs(api_key="unused"),
        agent_id=settings.elevenlabs_agent_id,
        requires_auth=True,
        audio_interface=DefaultAudioInterface(),
        callback_agent_response=lambda text: print(f"\nMateo: {text}"),
        callback_user_transcript=lambda text: print(f"\nTú: {text}"),
    )

    def stop(_signum: int, _frame: FrameType | None) -> None:
        conversation.end_session()

    signal.signal(signal.SIGINT, stop)
    titles = ", ".join(topic["title"] for topic in plan["topics"])
    print(f"Plan: {plan['duration_minutes']} min, topics: {titles}")
    print("Speak when Mateo greets you. Ctrl+C ends the interview.")
    conversation.start_session()
    conversation.wait_for_session_end()

    print(f"\nConversation {conversation_id} ended. Latency report in {METRICS_DELAY_S} s...")
    time.sleep(METRICS_DELAY_S)
    return latency_report.main([conversation_id])


if __name__ == "__main__":
    sys.exit(main())
