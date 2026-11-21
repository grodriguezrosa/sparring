from fastapi import FastAPI

from app.schemas.health import HealthResponse

app = FastAPI(title="Sparring API")


@app.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok")
