"""
Supabase Client Singleton
Antigravity Skill: database-patterns
"""
from typing import Optional
from supabase import create_client, Client
from app.config.settings import get_settings

class SupabaseClient:
    _instance: Optional[Client] = None

    @classmethod
    def get_client(cls) -> Client:
        if cls._instance is None:
            settings = get_settings()
            cls._instance = create_client(
                supabase_url=settings.supabase_url,
                supabase_key=settings.supabase_key
            )
        return cls._instance
