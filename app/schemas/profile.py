from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

MAX_CHARS = 20_000

type Level = Literal["junior", "mid", "senior", "lead"]
type Coverage = Literal["yes", "partial", "no"]


class ProfileRequest(BaseModel):
    """What the user sends: the job offer and the CV as text."""

    model_config = ConfigDict(str_strip_whitespace=True)

    job_offer: str = Field(min_length=50, max_length=MAX_CHARS)
    cv: str = Field(min_length=50, max_length=MAX_CHARS)


class Requirement(BaseModel):
    description: str = Field(description="Requirement as stated in the job offer")
    mandatory: bool = Field(description="true if the offer presents it as essential")
    cv_coverage: Coverage = Field(description="Whether the CV demonstrates this requirement")
    cv_evidence: str | None = Field(
        default=None,
        description="Fragment copied verbatim from the CV that supports it; null if none",
    )


class Profile(BaseModel):
    """Structured profile of the job offer against the CV. The basis of the interview plan."""

    role: str = Field(description="Job title")
    level: Level = Field(description="Seniority level the offer asks for")
    stack: list[str] = Field(description="Technologies the offer asks for")
    responsibilities: list[str] = Field(description="Main responsibilities of the role")
    requirements: list[Requirement]
    candidate_summary: str = Field(description="2-3 sentences on the candidate vs the offer")

    # mypy does not support decorators on top of @property; Pydantic documents this ignore.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def gaps(self) -> list[Requirement]:
        """Requirements the CV does not fully cover. Computed, never asked from the LLM."""
        return [r for r in self.requirements if r.cv_coverage != "yes"]
