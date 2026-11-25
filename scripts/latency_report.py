"""Latency report for voice interviews, from the per-turn metrics ElevenLabs stores.

    uv run python -m scripts.latency_report              # the agent's last 3 conversations
    uv run python -m scripts.latency_report --last 10
    uv run python -m scripts.latency_report conv_abc123  # one conversation

Only timings are printed, never what was said.
"""

import argparse
import statistics
import sys
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from app.config import get_settings

# ElevenLabs metric name -> column label. All in seconds, per agent turn.
METRICS = {
    "convai_ttf_audio_since_silence": "perceived",  # candidate stops talking -> hears Mateo
    "convai_llm_service_ttfb": "llm_first",  # our endpoint's first byte, as ElevenLabs sees it
    "convai_llm_service_ttf_sentence": "llm_sentence",  # first full sentence (TTS can start)
    "convai_tts_service_ttfb": "tts_first",  # voice synthesis first audio
}


def turn_metrics(turn: Mapping[str, Any]) -> dict[str, float]:
    """The metrics of one transcript entry that we know, in seconds."""
    raw = (turn.get("conversation_turn_metrics") or {}).get("metrics") or {}
    return {
        label: float(raw[name]["elapsed_time"])
        for name, label in METRICS.items()
        if isinstance(raw.get(name), Mapping) and "elapsed_time" in raw[name]
    }


def answered_turns(transcript: Sequence[Mapping[str, Any]]) -> list[dict[str, float]]:
    """Metrics of the agent turns that answer the candidate (the greeting has no LLM call)."""
    turns = [turn_metrics(t) for t in transcript if t.get("role") == "agent"]
    return [m for m in turns if "llm_first" in m]


def summarize(turns: Sequence[Mapping[str, float]]) -> dict[str, tuple[float, float]]:
    """Median and max of every metric over the given turns."""
    summary = {}
    for label in METRICS.values():
        values = [turn[label] for turn in turns if label in turn]
        if values:
            summary[label] = (statistics.median(values), max(values))
    return summary


def print_table(title: str, turns: Sequence[Mapping[str, float]]) -> None:
    labels = list(METRICS.values())
    print(f"\n{title}")
    print("  turn  " + "".join(f"{label:>14}" for label in labels))
    for n, turn in enumerate(turns, start=1):
        cells = "".join(
            f"{turn[label]:>13.2f}s" if label in turn else f"{'-':>14}" for label in labels
        )
        print(f"  {n:>4}  {cells}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Per-turn latency of voice interviews.")
    parser.add_argument("conversation_id", nargs="?", help="one conversation (default: latest)")
    parser.add_argument("--last", type=int, default=3, help="how many recent conversations")
    args = parser.parse_args(argv)

    settings = get_settings()
    headers = {"xi-api-key": settings.elevenlabs_api_key.get_secret_value()}
    with httpx.Client(base_url=settings.elevenlabs_base_url, headers=headers, timeout=30) as api:
        if args.conversation_id:
            ids = [args.conversation_id]
        else:
            listing = api.get(
                "/v1/convai/conversations",
                params={"agent_id": settings.elevenlabs_agent_id, "page_size": args.last},
            )
            listing.raise_for_status()
            ids = [c["conversation_id"] for c in listing.json()["conversations"]]

        all_turns: list[dict[str, float]] = []
        for conversation_id in ids:
            detail = api.get(f"/v1/convai/conversations/{conversation_id}")
            detail.raise_for_status()
            turns = answered_turns(detail.json().get("transcript", []))
            if turns:
                print_table(conversation_id, turns)
                all_turns += turns

    if not all_turns:
        print("No answered turns with metrics found.")
        return 1
    print(f"\nOver {len(all_turns)} answered turns (median / max):")
    for label, (median, worst) in summarize(all_turns).items():
        print(f"  {label:>13}: {median:5.2f} s / {worst:5.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
