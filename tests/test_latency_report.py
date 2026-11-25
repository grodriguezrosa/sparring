from typing import Any

from scripts.latency_report import answered_turns, summarize, turn_metrics


def metric(seconds: float) -> dict[str, float]:
    return {"elapsed_time": seconds}


def agent_turn(**metrics: float) -> dict[str, Any]:
    return {
        "role": "agent",
        "message": "never printed",
        "conversation_turn_metrics": {"metrics": {k: metric(v) for k, v in metrics.items()}},
    }


def test_reads_the_known_metrics_of_a_turn() -> None:
    turn = agent_turn(
        convai_ttf_audio_since_silence=2.5,
        convai_llm_service_ttfb=2.2,
        convai_tts_service_ttfb=0.15,
        some_future_metric=9.0,
    )

    assert turn_metrics(turn) == {"perceived": 2.5, "llm_first": 2.2, "tts_first": 0.15}


def test_a_turn_without_metrics_gives_nothing() -> None:
    assert turn_metrics({"role": "user", "conversation_turn_metrics": None}) == {}


def test_only_agent_turns_that_called_the_llm_count() -> None:
    transcript: list[dict[str, Any]] = [
        agent_turn(convai_tts_service_ttfb=0.17),  # the fixed greeting: no LLM call
        {"role": "user", "conversation_turn_metrics": None},
        agent_turn(convai_llm_service_ttfb=1.5, convai_ttf_audio_since_silence=1.8),
    ]

    assert answered_turns(transcript) == [{"llm_first": 1.5, "perceived": 1.8}]


def test_summarizes_median_and_max() -> None:
    turns = [{"perceived": 1.0}, {"perceived": 3.0}, {"perceived": 2.0, "llm_first": 1.5}]

    assert summarize(turns) == {"perceived": (2.0, 3.0), "llm_first": (1.5, 1.5)}
