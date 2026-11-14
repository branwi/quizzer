from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./problems.db"
    secret_key: SecretStr | None = None
    access_token_minutes: int = Field(default=60, gt=0)
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
