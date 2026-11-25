from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.interview_plan import MAX_PLAN_CHARS, InterviewPlan

SIGNED_URL_TTL_SECONDS = 15 * 60  # documented by ElevenLabs


class VoiceSessionRequest(BaseModel):
    """The plan returned by POST /interview-plan, to be followed in this conversation."""

    plan: InterviewPlan

    @model_validator(mode="after")
    def plan_is_not_too_large(self) -> Self:
        # The plan comes back from the client: untrusted, like the CV it was built from.
        if len(self.plan.model_dump_json()) > MAX_PLAN_CHARS:
            raise ValueError(f"plan is too large (max {MAX_PLAN_CHARS} characters)")
        return self


class VoiceSession(BaseModel):
    signed_url: str = Field(
        description="Single-use WebSocket URL the browser uses to talk to the agent"
    )
    conversation_id: str = Field(description="ElevenLabs id of the conversation this URL starts")
    expires_in_seconds: int = Field(
        description="The conversation must start before the signed URL expires"
    )
