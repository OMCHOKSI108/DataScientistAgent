"""
Configuration module – loads environment variables via Pydantic BaseSettings.
All secrets and external service URLs are centralised here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # ── GROQ LLM ──────────────────────────────────────────
    GROQ_API_KEY: str = ""

    # ── Supabase Auth & Storage ─────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # ── App ─────────────────────────────────────────────────
    APP_TITLE: str = "Autonomous Data Scientist Agent"
    UPLOAD_DIR: str = "uploads"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


def get_settings() -> Settings:
    """Return a fresh Settings instance (always reads current .env)."""
    return Settings()
