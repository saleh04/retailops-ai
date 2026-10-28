from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    
    APP_NAME: str
    APP_VERSION: str
    
    model_config = SettingsConfigDict(env_file=".env")
    
@lru_cache
def get_settings():
    return Settings()