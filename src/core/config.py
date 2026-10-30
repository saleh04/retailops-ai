from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    
    APP_NAME: str
    APP_VERSION: str
    
    DEFAULT_SQLITE_URL: str
    POOL_PRE_PING: bool 
    CONNECT_TIMEOUT: int
    
    model_config = SettingsConfigDict(
    env_file=BASE_DIR / ".env",
    env_file_encoding="utf-8",
    extra="ignore",
    )
    
@lru_cache
def get_settings():
    return Settings()