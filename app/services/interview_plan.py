from collections.abc import Sequence

from app.llm.base import LLMClient
from app.llm.structured import generate_structured
from app.llm.untrusted import UNTRUSTED_DATA_POLICY, delimit
from app.schemas.interview_plan import Importance, InterviewPlan, InterviewTopic, PlanDraft
from app.schemas.profile import Profile

IMPORTANCE_WEIGHTS: dict[Importance, int] = {"high": 3, "medium": 2, "low": 1}


def _system_prompt(duration_minutes: int) -> str:
    return f"""You are a senior technical interviewer. Using the candidate profile below, you
prepare a {duration_minutes}-minute technical voice interview for that job offer.

Rules:
- Between 3 and 8 topics, in the order they will be asked: open with the candidate's real
  experience to warm up, then the core skills, and leave the gaps for the second half.
- Each topic evaluates one requirement of the profile. Copy its description exactly into
  `requirement`.
- focus: "verify_claim" for requirements the CV claims (ask about the specific experience
  quoted in cv_evidence and check its depth); "explore_gap" for gaps (find out what the
  candidate knows anyway, without penalizing honesty); "core_skill" for essential skills
  that need direct technical questions.
- importance: "high" for mandatory requirements, "medium" or "low" for nice-to-have ones.
- This is a spoken interview: one open, concrete question at a time; no code to read aloud,
  no lists inside questions.
- good_answer_signals: concrete technical points a strong answer would include.
- intro: the interviewer's first words: greet the candidate and explain the format.
- Write every text in Spanish, addressing the candidate as "tú".

{UNTRUSTED_DATA_POLICY}"""


def allocate_minutes(importances: Sequence[Importance], duration_minutes: int) -> list[int]:
    """Split the duration across topics by importance.

    Every topic gets at least one minute and the total is exactly `duration_minutes`.
    """
    if not importances:
        return []
    if duration_minutes < len(importances):
        raise ValueError("duration_minutes must be at least one minute per topic")

    weights = [IMPORTANCE_WEIGHTS[importance] for importance in importances]
    spare = duration_minutes - len(weights)  # one minute per topic is guaranteed first
    exact_shares = [spare * weight / sum(weights) for weight in weights]
    minutes = [1 + int(share) for share in exact_shares]

    # Hand out the minutes lost when rounding down, largest fractional part first.
    leftover = duration_minutes - sum(minutes)
    by_remainder = sorted(
        range(len(exact_shares)),
        key=lambda i: exact_shares[i] - int(exact_shares[i]),
        reverse=True,
    )
    for i in by_remainder[:leftover]:
        minutes[i] += 1
    return minutes


async def create_interview_plan(
    llm: LLMClient, *, profile: Profile, duration_minutes: int
) -> InterviewPlan:
    """Generate the interview plan for a profile and allocate the time per topic."""
    draft = await generate_structured(
        llm,
        system=_system_prompt(duration_minutes),
        user=delimit("profile", profile.model_dump_json(indent=2)),
        schema=PlanDraft,
    )
    minutes = allocate_minutes([topic.importance for topic in draft.topics], duration_minutes)
    topics = [
        InterviewTopic.model_validate({**topic.model_dump(), "minutes": topic_minutes})
        for topic, topic_minutes in zip(draft.topics, minutes, strict=True)
    ]
    return InterviewPlan(intro=draft.intro, duration_minutes=duration_minutes, topics=topics)
