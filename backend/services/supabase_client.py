"""
Supabase client singleton.
Provides a single reusable client instance across the application.
"""

from supabase import create_client, Client
from backend.config import get_settings


_client: Client | None = None


def get_supabase_client() -> Client:
    """Return the cached Supabase client (creates it on first call)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return _client
