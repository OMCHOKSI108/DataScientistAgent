"""
Configuration module – loads environment variables via Pydantic BaseSettings.
All secrets and external service URLs are centralised here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # ── GROQ & OpenRouter LLMs ────────────────────────────
    OPENROUTER_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    LLM_PROVIDER: str = "openrouter"  # openrouter | auto | gemini | groq

    # ── Supabase Auth & Storage ─────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # ── App ─────────────────────────────────────────────────
    APP_TITLE: str = "Autonomous Data Scientist Agent"
    UPLOAD_DIR: str = "uploads"
    CORS_ALLOW_ORIGINS: str = "http://localhost:8080,http://127.0.0.1:8080,http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


def get_settings() -> Settings:
    """Return a fresh Settings instance (always reads current .env)."""
    return Settings()
