"""
conftest.py — Fixtures globais para o pytest.
Garante que variáveis de ambiente mínimas existam antes de qualquer import do src/.
"""
import os
import pytest

# Garante que o ambiente de teste esteja setado antes de qualquer import
os.environ.setdefault("ENV", "test")
os.environ.setdefault("APP_DEBUG", "True")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test_user:test_pass@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-minimum-32-chars")
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMmJ5dGVzISE=")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("EVOLUTION_API_URL", "http://localhost:8080")
os.environ.setdefault("EVOLUTION_SERVER_URL", "http://localhost:8080")
os.environ.setdefault("EVOLUTION_API_KEY", "test-key")
os.environ.setdefault("EVOLUTION_INSTANCE_NAME", "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0000000000:test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "0")
os.environ.setdefault("VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("PUBLIC_URL", "http://localhost:8000")
os.environ.setdefault("METRICS_TOKEN", "test-metrics")
os.environ.setdefault("BACKEND_CORS_ORIGINS", '["http://localhost:3000"]')
