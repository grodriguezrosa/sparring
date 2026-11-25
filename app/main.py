from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import agent_llm, health, interview_plan, profile, voice
from app.api.deps import get_http_client
from app.api.errors import register_error_handlers


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield  # the app runs here
    # Shutdown: close the shared connection pool, if it was ever created.
    if get_http_client.cache_info().currsize:
        await get_http_client().aclose()


app = FastAPI(title="Sparring API", lifespan=lifespan)

register_error_handlers(app)

app.include_router(health.router)
app.include_router(profile.router)
app.include_router(interview_plan.router)
app.include_router(voice.router)
app.include_router(agent_llm.router)
