from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_llm
from app.llm.base import LLMClient
from app.schemas.profile import Profile, ProfileRequest
from app.services.profile import analyze_job_offer_and_cv

router = APIRouter(tags=["profile"])


@router.post("/profile")
async def create_profile(
    request: ProfileRequest, llm: Annotated[LLMClient, Depends(get_llm)]
) -> Profile:
    """Analyze the job offer and the CV and return the structured profile (nothing is stored)."""
    return await analyze_job_offer_and_cv(llm, job_offer=request.job_offer, cv=request.cv)
