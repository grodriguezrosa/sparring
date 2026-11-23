from fastapi import FastAPI

from app.api import agent_llm, health, interview_plan, profile, voice
from app.api.errors import register_error_handlers

app = FastAPI(title="Sparring API")

register_error_handlers(app)

app.include_router(health.router)
app.include_router(profile.router)
app.include_router(interview_plan.router)
app.include_router(voice.router)
app.include_router(agent_llm.router)
