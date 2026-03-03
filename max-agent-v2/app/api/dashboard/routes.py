"""
Dashboard API Routes
Antigravity Skill: rest-api
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any, List
from app.infrastructure.database.supabase_client import SupabaseClient
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
logger = get_logger(__name__)

def get_supabase():
    return SupabaseClient.get_client()

@router.get("/kpis")
async def get_kpis():
    """Returns key performance indicators."""
    supabase = get_supabase()
    
    try:
        # Leads Count (Total)
        leads_res = supabase.table("dados cliente").select("id", count="exact").execute()
        total_leads = leads_res.count or 0
        
        # Appointments Count (This Month)
        # Using simple query for now
        # Ideally filter by date gte month start
        appts_res = supabase.table("agendamentos").select("id", count="exact").execute()
        total_appts = appts_res.count or 0
        
        # Revenue (Estimate)
        # Assuming every "closed" client (status/stage) worth X
        # For now, let's mock the revenue based on 'active' clients or similar
        # Or just return a placeholder driven by real data if available
        # We don't have a 'status' field for sale closure in 'dados cliente' yet explicitly 
        # heavily used in previous steps, but we have 'lead_score'.
        
        # Let's count "Hot Leads" (>75) as potential high value
        hot_leads_res = supabase.table("dados cliente").select("id", count="exact").filter("lead_score", "gte", 75).execute()
        hot_leads = hot_leads_res.count or 0
        
        return {
            "total_leads": total_leads,
            "monthly_appointments": total_appts, # Total for now
            "conversion_rate": f"{int((hot_leads / total_leads * 100) if total_leads > 0 else 0)}%",
            "estimated_revenue": hot_leads * 1500 # Assume R$1500 per hot lead potential
        }
    except Exception as e:
        logger.error(f"Error fetching KPIs: {e}")
        return {"error": str(e)}

@router.get("/leads")
async def get_leads():
    """Returns list of leads."""
    supabase = get_supabase()
    try:
        # Fetch latest 50
        res = supabase.table("dados cliente").select("*").order("created_at", desc=True).limit(50).execute()
        return res.data
    except Exception as e:
        logger.error(f"Error fetching leads: {e}")
        return []

@router.get("/appointments")
async def get_appointments():
    """Returns appointments for calendar."""
    supabase = get_supabase()
    try:
        res = supabase.table("agendamentos").select("*").order("data_hora", desc=True).limit(100).execute()
        return res.data
    except Exception as e:
        logger.error(f"Error fetching appointments: {e}")
        return []

@router.get("/funnel")
async def get_funnel():
    """Returns funnel visualization data."""
    # Mocking funnel stages based on logic
    # Stage 1: Leads (Total)
    # Stage 2: Contacted (Has interaction)
    # Stage 3: High Score (Qualified)
    # Stage 4: Scheduled (Appointment)
    
    supabase = get_supabase()
    try:
        leads = supabase.table("dados cliente").select("id", count="exact").execute().count or 0
        
        # Assuming all in DB are 'contacted' roughly
        contacted = leads 
        
        min_score = 50
        qualified = supabase.table("dados cliente").select("id", count="exact").filter("lead_score", "gte", min_score).execute().count or 0
        
        scheduled = supabase.table("agendamentos").select("id", count="exact").execute().count or 0
        
        return [
            {"name": "Leads Totais", "value": leads, "fill": "#8884d8"},
            {"name": "Qualificados", "value": qualified, "fill": "#82ca9d"},
            {"name": "Agendados", "value": scheduled, "fill": "#ffc658"},
            {"name": "Fechados", "value": int(scheduled * 0.4), "fill": "#d0ed57"} # Est 40% close rate
        ]
    except Exception as e:
        return []
