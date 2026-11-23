from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    deepseek_api_key: SecretStr
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"


@lru_cache
def get_settings() -> Settings:
    # Pyright does not know that BaseSettings fills fields from the environment and .env,
    # so it reports deepseek_api_key as missing. mypy (with the pydantic plugin) gets it right.
    return Settings()  # pyright: ignore[reportCallIssue]
