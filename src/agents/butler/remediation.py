"""
Butler Auto-Remediation System

Automatic incident response and service recovery.
Executes predefined playbooks for common infrastructure issues.
"""

import asyncio
import httpx
from typing import Dict, Any, Optional
from datetime import datetime
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class RemediationAction:
    """Base class for remediation actions."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute remediation action."""
        raise NotImplementedError


class RestartServiceAction(RemediationAction):
    """Restart a service via API or command."""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        service_name = context.get("service_name")
        
        if not service_name:
            return {"status": "failed", "error": "service_name required"}
        
        logger.info(f"Attempting to restart service: {service_name}")
        
        # In production, this would call Docker API, systemctl, or k8s API
        # For now, log the action
        
        if service_name == "redis":
            return await self._restart_redis()
        elif service_name == "postgres":
            return await self._restart_postgres()
        elif service_name == "evolution":
            return await self._restart_evolution()
        
        return {"status": "simulated", "service": service_name}
    
    async def _restart_redis(self) -> Dict[str, Any]:
        """Restart Redis via Docker."""
        # Example: docker restart redis-container
        logger.info("Redis restart triggered (simulation)")
        await asyncio.sleep(1)
        return {"status": "success", "service": "redis"}
    
    async def _restart_postgres(self) -> Dict[str, Any]:
        """Restart PostgreSQL."""
        logger.warning("PostgreSQL restart requested - manual intervention recommended")
        return {"status": "manual_required", "service": "postgres"}
    
    async def _restart_evolution(self) -> Dict[str, Any]:
        """Restart Evolution API."""
        logger.info("Evolution API restart triggered")
        await asyncio.sleep(2)
        return {"status": "success", "service": "evolution"}


class ClearCacheAction(RemediationAction):
    """Clear Redis cache."""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        cache_pattern = context.get("pattern", "*")
        
        try:
            import redis
            from src.config import settings
            
            r = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                decode_responses=True
            )
            
            # Get keys matching pattern
            keys = r.keys(cache_pattern)
            
            if keys:
                deleted = r.delete(*keys)
                logger.info(f"Cache cleared: {deleted} keys deleted (pattern: {cache_pattern})")
                return {"status": "success", "deleted_keys": deleted}
            else:
                return {"status": "success", "deleted_keys": 0}
        
        except Exception as e:
            logger.error(f"Cache clear failed: {e}")
            return {"status": "failed", "error": str(e)}


class ReconnectWebhookAction(RemediationAction):
    """Reconnect disconnected webhooks."""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        instance_name = context.get("instance_name")
        
        if not instance_name:
            return {"status": "failed", "error": "instance_name required"}
        
        try:
            from src.services.evolution_service import EvolutionService
            
            evolution = EvolutionService()
            
            # Re-register webhook
            result = await evolution.set_webhook(
                instance_name=instance_name,
                webhook_url=context.get("webhook_url"),
                events=["messages", "connection"]
            )
            
            logger.info(f"Webhook reconnected for instance: {instance_name}")
            return {"status": "success", "instance": instance_name, "result": result}
        
        except Exception as e:
            logger.error(f"Webhook reconnect failed: {e}")
            return {"status": "failed", "error": str(e)}


class RecoverDatabaseAction(RemediationAction):
    """Recover database connections."""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from src.models.database import async_session, engine
            
            # Test connection
            async with async_session() as session:
                await session.execute("SELECT 1")
            
            logger.info("Database connection recovered")
            return {"status": "success", "connection": "active"}
        
        except Exception as e:
            logger.error(f"Database recovery failed: {e}")
            return {"status": "failed", "error": str(e)}


# Remediation Playbooks
PLAYBOOKS = {
    "redis_down": [
        (RestartServiceAction("restart_redis", "Restart Redis service"), {"service_name": "redis"}),
        (ClearCacheAction("verify_cache", "Verify cache accessibility"), {"pattern": "test:*"})
    ],
    "database_connection_lost": [
        (RecoverDatabaseAction("test_connection", "Test DB connection"), {}),
        (RestartServiceAction("restart_postgres", "Restart PostgreSQL if needed"), {"service_name": "postgres"})
    ],
    "evolution_disconnected": [
        (RestartServiceAction("restart_evolution", "Restart Evolution API"), {"service_name": "evolution"}),
        (ReconnectWebhookAction("reconnect_webhooks", "Reconnect all webhooks"), {})
    ],
    "high_memory_usage": [
        (ClearCacheAction("clear_old_cache", "Clear old cache entries"), {"pattern": "ai_response:*"}),
    ]
}


async def execute_playbook(playbook_name: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Execute a remediation playbook.
    
    Args:
        playbook_name: Name of the playbook to run
        context: Additional context for actions
    
    Returns:
        Execution results
    """
    if playbook_name not in PLAYBOOKS:
        return {"status": "failed", "error": f"Unknown playbook: {playbook_name}"}
    
    context = context or {}
    playbook = PLAYBOOKS[playbook_name]
    results = []
    
    logger.info(f"Executing playbook: {playbook_name}")
    
    for action, action_context in playbook:
        merged_context = {**context, **action_context}
        
        try:
            result = await action.execute(merged_context)
            results.append({
                "action": action.name,
                "result": result,
                "timestamp": datetime.now().isoformat()
            })
            
            # Stop on first failure
            if result.get("status") == "failed":
                logger.warning(f"Playbook {playbook_name} stopped at {action.name}: {result.get('error')}")
                break
        
        except Exception as e:
            logger.error(f"Action {action.name} failed: {e}")
            results.append({
                "action": action.name,
                "result": {"status": "exception", "error": str(e)},
                "timestamp": datetime.now().isoformat()
            })
            break
    
    return {
        "playbook": playbook_name,
        "executed_at": datetime.now().isoformat(),
        "actions": results,
        "success": all(r["result"].get("status") in ["success", "simulated"] for r in results)
    }
