"""
Configurações centralizadas usando Pydantic Settings
Antigravity Skill: software-architecture
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    """Configurações da aplicação"""
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )
    
    # Evolution API
    evolution_api_url: str
    evolution_api_key: str
    evolution_instance_name: str
    
    # Supabase
    supabase_url: str
    supabase_key: str
    
    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_whisper_model: str = "whisper-1"
    
    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str
    
    # Email
    resend_api_key: str
    sender_email: str
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Application
    app_name: str = "MAX Agent"
    app_version: str = "2.0.0"
    debug: bool = False
    log_level: str = "INFO"
    
    # Admin
    admin_port: int = 5000
    admin_secret_key: str
    
    # Multi-tenant
    tenant_id: int = 1 # Default for internal agent or as fallback

# Singleton
_settings: Optional[Settings] = None

def get_settings() -> Settings:
    """Retorna instância singleton das configurações"""
    global _settings
    if _settings is None:
        _settings = Settings() # type: ignore
    return _settings
