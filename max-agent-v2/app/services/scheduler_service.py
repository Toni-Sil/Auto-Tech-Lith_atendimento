from celery import Celery  # type: ignore
from app.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "max_scheduler",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.followup", "app.tasks.notifications"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
)
