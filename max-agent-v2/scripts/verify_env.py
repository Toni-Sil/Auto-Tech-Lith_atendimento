from app.config.settings import get_settings

def test_settings_load():
    settings = get_settings()
    print(f"App Name: {settings.app_name}")
    print(f"Debug Mode: {settings.debug}")
    print(f"Gemini Key Loaded: {'NO (Not in Settings class)'}") 
    print(f"OpenAI Key Loaded: {'Yes' if settings.openai_api_key else 'No'}")
    print(f"Supabase URL: {settings.supabase_url}")
    print(f"Evolution URL: {settings.evolution_api_url}")
    print(f"Telegram Token: {'Yes' if settings.telegram_bot_token else 'No'}")

if __name__ == "__main__":
    test_settings_load()
