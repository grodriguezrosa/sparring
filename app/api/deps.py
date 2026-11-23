from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.llm.base import LLMClient
from app.llm.deepseek import DeepSeekLLM
from app.services.quota import DailyQuota
from app.voice.base import VoiceProvider
from app.voice.elevenlabs import ElevenLabsVoice


def get_llm(settings: Annotated[Settings, Depends(get_settings)]) -> LLMClient:
    """The LLM used by the endpoints. Tests replace it with FakeLLM."""
    return DeepSeekLLM(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )


def get_voice_provider(settings: Annotated[Settings, Depends(get_settings)]) -> VoiceProvider:
    """The voice provider used by the endpoints. Tests replace it with a fake."""
    return ElevenLabsVoice(
        api_key=settings.elevenlabs_api_key,
        agent_id=settings.elevenlabs_agent_id,
        base_url=settings.elevenlabs_base_url,
    )


@lru_cache
def get_voice_quota() -> DailyQuota:
    """One shared quota for the whole process (lru_cache makes it a singleton)."""
    return DailyQuota(limit_per_day=get_settings().voice_sessions_per_code_per_day)
