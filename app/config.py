from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_ACCESS_CODE_LENGTH = 16


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    deepseek_api_key: SecretStr
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"

    elevenlabs_api_key: SecretStr
    elevenlabs_agent_id: str
    elevenlabs_base_url: str = "https://api.elevenlabs.io"

    # Comma-separated in .env: ACCESS_CODES=code-for-me,code-for-tester-1
    access_codes: Annotated[list[SecretStr], NoDecode] = Field(min_length=1)
    voice_sessions_per_code_per_day: int = Field(default=3, ge=1)

    @field_validator("access_codes", mode="before")
    @classmethod
    def split_access_codes(cls, value: object) -> object:
        if isinstance(value, str):
            return [code.strip() for code in value.split(",") if code.strip()]
        return value

    @field_validator("access_codes")
    @classmethod
    def access_codes_are_long_enough(cls, codes: list[SecretStr]) -> list[SecretStr]:
        if any(len(code.get_secret_value()) < MIN_ACCESS_CODE_LENGTH for code in codes):
            raise ValueError(
                f"every access code needs at least {MIN_ACCESS_CODE_LENGTH} characters"
            )
        return codes


@lru_cache
def get_settings() -> Settings:
    # Pyright does not know that BaseSettings fills fields from the environment and .env,
    # so it reports the required fields as missing. mypy (with the pydantic plugin) gets it right.
    return Settings()  # pyright: ignore[reportCallIssue]
