"""
Notification Tasks
Antigravity Skill: task-scheduling
"""
from celery import shared_task
from datetime import datetime, timezone
from app.infrastructure.database.supabase_client import SupabaseClient
from app.services.notification_service import NotificationService
from app.utils.logger import get_logger

logger = get_logger(__name__)

@shared_task(name="check_briefing_reminders")
async def check_briefing_reminders():
    """
    Checks for appointments occurring in 12h, 6h, and 1h and sends notifications.
    Suggested schedule: Every 15 minutes.
    """
    logger.info("Checking for briefing reminders...")
    supabase = SupabaseClient.get_client()
    notifier = NotificationService()
    
    # Use UTC aware datetime
    now = datetime.now(timezone.utc)
    
    # Time windows (approximate, allowing for the 15m polling interval)
    # We look for appointments starting between X and X+task_interval
    # But safer to just check "is within window AND not sent"
    
    # 1. 12h Reminder (e.g. 11h30m to 12h30m from now)
    # Actually, simplistic logic: 
    #   if 11h < time_until_appt < 13h AND not sent: Send 12h
    
    upcoming_appts = supabase.table("agendamentos").select("*").gte("data_hora", now.isoformat()).execute().data
    
    for appt in upcoming_appts:
        # Handle Supabase timestamp format (ISO 8601)
        # It usually comes as "2023-10-27T10:00:00+00:00" or with Z
        ts_str = appt["data_hora"]
        if ts_str.endswith('Z'):
            ts_str = ts_str.replace('Z', '+00:00')
        
        try:
            appt_time = datetime.fromisoformat(ts_str)
        except ValueError:
            # Fallback for weird formats if necessary
            continue
             
        time_diff = appt_time - now
        hours_until = time_diff.total_seconds() / 3600
        
        # T-12h (Window: 11.5h to 12.5h)
        if 11.5 <= hours_until <= 12.5 and not appt.get("notification_12h_sent"):
            await notifier.send_briefing_notification(appt, "12h")
            supabase.table("agendamentos").update({"notification_12h_sent": True}).eq("id", appt["id"]).execute()
            
        # T-6h (Window: 5.5h to 6.5h)
        elif 5.5 <= hours_until <= 6.5 and not appt.get("notification_6h_sent"):
            await notifier.send_briefing_notification(appt, "6h")
            supabase.table("agendamentos").update({"notification_6h_sent": True}).eq("id", appt["id"]).execute()
            
        # T-1h (Window: 0.5h to 1.5h)
        elif 0.5 <= hours_until <= 1.5 and not appt.get("notification_1h_sent"):
            await notifier.send_briefing_notification(appt, "1h")
            supabase.table("agendamentos").update({"notification_1h_sent": True}).eq("id", appt["id"]).execute()

    logger.info("Reminder check complete.")
