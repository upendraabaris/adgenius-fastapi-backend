# app/config.py
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./adgenius.db")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change_me")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    MCP_CONFIG_PATH: str = os.getenv("MCP_CONFIG_PATH", "./mcp_config.json")

settings = Settings()