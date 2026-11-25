from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.profile import Profile

MAX_PROFILE_CHARS = 40_000
MAX_PLAN_CHARS = 40_000

type Focus = Literal["verify_claim", "explore_gap", "core_skill"]
type Importance = Literal["high", "medium", "low"]


class InterviewPlanRequest(BaseModel):
    """The profile returned by POST /profile, plus the desired interview length."""

    profile: Profile
    duration_minutes: int = Field(default=30, ge=15, le=60)

    @model_validator(mode="after")
    def profile_is_not_too_large(self) -> Self:
        # The profile comes back from the client, so it is untrusted and must be bounded.
        if len(self.profile.model_dump_json()) > MAX_PROFILE_CHARS:
            raise ValueError(f"profile is too large (max {MAX_PROFILE_CHARS} characters)")
        return self


class PlannedTopic(BaseModel):
    title: str = Field(description="Short name of the topic")
    requirement: str = Field(
        description="Description of the profile requirement this topic evaluates, copied exactly"
    )
    focus: Focus = Field(
        description=(
            "verify_claim: the CV claims it, check its depth; "
            "explore_gap: the CV does not cover it, find out what the candidate knows anyway; "
            "core_skill: essential skill that needs direct technical questions"
        )
    )
    importance: Importance = Field(
        description="high for mandatory requirements; medium or low for nice-to-have ones"
    )
    opening_question: str = Field(description="First question, open and suited to be spoken")
    follow_up_questions: list[str] = Field(
        min_length=1, max_length=4, description="Questions to dig deeper depending on the answer"
    )
    good_answer_signals: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Concrete things a strong answer would mention; used later for scoring",
    )


class PlanDraft(BaseModel):
    """What the LLM generates. Minutes per topic are allocated in code afterwards."""

    intro: str = Field(description="Interviewer's first words: greeting and format, 2-3 sentences")
    topics: list[PlannedTopic] = Field(min_length=3, max_length=8)


class InterviewTopic(PlannedTopic):
    minutes: int


class InterviewPlan(BaseModel):
    intro: str
    duration_minutes: int
    topics: list[InterviewTopic] = Field(min_length=1)
