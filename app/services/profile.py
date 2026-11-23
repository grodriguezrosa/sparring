from app.llm.base import LLMClient
from app.llm.structured import generate_structured
from app.llm.untrusted import UNTRUSTED_DATA_POLICY, delimit
from app.schemas.profile import Profile

PROFILE_SYSTEM_PROMPT = f"""You are a technical recruiting analyst for IT positions.
From a job offer and a candidate's CV, you extract a structured profile that will be used
to prepare a technical interview.

Rules:
- Requirements come from the JOB OFFER, not from the CV. Mark as mandatory only those the
  offer presents as essential.
- For each requirement, state whether the CV covers it ("yes"), partially ("partial") or
  not ("no"). Do not invent experience the CV does not mention.
- In cv_evidence, COPY a fragment of the CV VERBATIM, without paraphrasing or summarizing,
  so it can be quoted during the interview. If the evidence is spread out, copy the most
  representative fragment. If the CV has no evidence, use null.
- The level is the one the offer asks for, not the candidate's level.
- Write every text value in Spanish. Verbatim CV quotes stay exactly as written.

{UNTRUSTED_DATA_POLICY}"""


async def analyze_job_offer_and_cv(llm: LLMClient, *, job_offer: str, cv: str) -> Profile:
    """Extract the structured profile by comparing the job offer with the CV."""
    user = f"{delimit('job_offer', job_offer)}\n\n{delimit('cv', cv)}"
    return await generate_structured(llm, system=PROFILE_SYSTEM_PROMPT, user=user, schema=Profile)
