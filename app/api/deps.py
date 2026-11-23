from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.llm.base import LLMClient
from app.llm.deepseek import DeepSeekLLM


def get_llm(settings: Annotated[Settings, Depends(get_settings)]) -> LLMClient:
    """The LLM used by the endpoints. Tests replace it with FakeLLM."""
    return DeepSeekLLM(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
