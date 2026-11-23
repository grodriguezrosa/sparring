from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.llm.base import LLMProviderError
from app.llm.structured import LLMOutputError


async def _provider_unavailable(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "The AI service is unavailable. Please try again later."},
    )


async def _invalid_output(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": "The AI returned an invalid response. Please try again."},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Turn LLM module errors into clear HTTP responses, for every endpoint."""
    app.add_exception_handler(LLMProviderError, _provider_unavailable)
    app.add_exception_handler(LLMOutputError, _invalid_output)
