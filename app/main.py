from fastapi import FastAPI

from app.api import health, profile
from app.api.errors import register_error_handlers

app = FastAPI(title="Sparring API")

register_error_handlers(app)

app.include_router(health.router)
app.include_router(profile.router)
