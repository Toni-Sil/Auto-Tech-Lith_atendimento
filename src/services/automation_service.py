from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any
import asyncio

from src.models.automation import AutomationRule
from src.schemas.automation import AutomationRuleCreate, AutomationRuleUpdate
from src.utils.logger import setup_logger
from src.services.notification_service import notification_service
from src.schemas.notification import NotificationCreate

logger = setup_logger(__name__)

class AutomationService:
    async def create_rule(self, session: AsyncSession, tenant_id: int, data: AutomationRuleCreate) -> AutomationRule:
        rule = AutomationRule(
            tenant_id=tenant_id,
            name=data.name,
            description=data.description,
            trigger_event=data.trigger_event,
            action_type=data.action_type,
            action_payload=data.action_payload,
            is_active=data.is_active
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return rule

    async def get_rules(self, session: AsyncSession, tenant_id: int) -> List[AutomationRule]:
        result = await session.execute(select(AutomationRule).where(AutomationRule.tenant_id == tenant_id))
        return result.scalars().all()

    async def update_rule(self, session: AsyncSession, tenant_id: int, rule_id: int, data: AutomationRuleUpdate) -> AutomationRule:
        rule = await session.scalar(select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.tenant_id == tenant_id))
        if not rule:
            return None
            
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(rule, key, value)
            
        await session.commit()
        await session.refresh(rule)
        return rule

    async def process_event(self, session: AsyncSession, tenant_id: int, trigger_event: str, context: Dict[str, Any]):
        """
        The core of the Automation Engine.
        Finds all active rules for the given event and executes their actions.
        """
        rules = await session.execute(
            select(AutomationRule)
            .where(
                AutomationRule.tenant_id == tenant_id,
                AutomationRule.trigger_event == trigger_event,
                AutomationRule.is_active == True
            )
        )
        
        for rule in rules.scalars().all():
            logger.info(f"Triggering Automation Rule #{rule.id}: {rule.name}")
            # Run action asynchronously so it doesn't block the caller event
            asyncio.create_task(self._execute_action(session, rule, context))
            
    async def _execute_action(self, session: AsyncSession, rule: AutomationRule, context: Dict[str, Any]):
        """Executes the specific action defined by the rule."""
        try:
            if rule.action_type == "send_email":
                # Example: Email the tenant admin via Notification module
                # In real life, recipient_id might come from context or rule config
                recipient_id = rule.action_payload.get("recipient_id") or context.get("owner_id")
                if recipient_id:
                    msg = NotificationCreate(
                        channel="email",
                        title=rule.action_payload.get("subject", "Automated Notification"),
                        message=rule.action_payload.get("body", "An event occurred."),
                        recipient_id=recipient_id
                    )
                    await notification_service.create_notification(session, rule.tenant_id, msg)
                    
            elif rule.action_type == "webhook":
                # Would do a HTTP POST to rule.action_payload["url"]
                logger.info(f"Automation Webhook Fire: {rule.action_payload.get('url')} with {context}")
                
            elif rule.action_type == "update_status":
                # Internal data mutation
                logger.info(f"Automation Status Update: {context}")
        except Exception as e:
            logger.error(f"Failed to execute rule {rule.id}: {e}")

automation_service = AutomationService()
