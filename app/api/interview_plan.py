from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_llm
from app.api.security import require_access_code
from app.llm.base import LLMClient
from app.schemas.interview_plan import InterviewPlan, InterviewPlanRequest
from app.services.interview_plan import create_interview_plan

router = APIRouter(tags=["interview-plan"], dependencies=[Depends(require_access_code)])


@router.post("/interview-plan")
async def plan_interview(
    request: InterviewPlanRequest, llm: Annotated[LLMClient, Depends(get_llm)]
) -> InterviewPlan:
    """Build the interview plan from a profile (nothing is stored)."""
    return await create_interview_plan(
        llm, profile=request.profile, duration_minutes=request.duration_minutes
    )
