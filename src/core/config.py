from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    
    APP_NAME: str
    APP_VERSION: str
    CORS_ORIGINS: list[str] | str = ["*"]
    
    POOL_PRE_PING: bool 
    CONNECT_TIMEOUT: int
    SQL_MAX_ROWS: int = Field(default=100, ge=1)
    SQL_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    
    POSTGRES_USERNAME: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_MAIN_DATABASE: str
    
    CHAT_HISTORY_LIMIT: int = Field(default=10)
    
    GENERATION_BACKEND: Literal["OPENAI", "GEMINI"] = "OPENAI"

    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_API_URL: str | None = None
    GOOGLE_API_KEY: SecretStr | None = None
    
    MODEL_ID: str | None = None
    
    DEFAULT_MAX_TOKENS: int | None = Field(
        default=None,
        gt=0,
    )
    DEFAULT_TEMPERATURE: float | None = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
    )
    LLM_TIMEOUT: float | None = Field(default=60.0, gt=0)
    AGENT_RECURSION_LIMIT: int = Field(default=25, ge=1)
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            return origins or ["*"]
        return value

    @field_validator(
        "OPENAI_API_KEY",
        "OPENAI_API_URL",
        "GOOGLE_API_KEY",
        "MODEL_ID",
        "DEFAULT_MAX_TOKENS",
        "LLM_TIMEOUT",
        mode="before",
    )
    @classmethod
    def empty_values_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value
    
    model_config = SettingsConfigDict(
    env_file=BASE_DIR / ".env",
    env_file_encoding="utf-8",
    extra="ignore",
    )
    
@lru_cache
def get_settings():
    return Settings()