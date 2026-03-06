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
        leads_res = supabase.table("customers").select("id", count="exact").execute()
        total_leads = leads_res.count or 0
        
        # ... (Agendamentos logic remains same)
        
        # Let's count "Hot Leads" (>75) as potential high value
        hot_leads_res = supabase.table("customers").select("id", count="exact").filter("lead_score", "gte", 75).execute()
        hot_leads = hot_leads_res.count or 0
        
        return {
            "total_leads": total_leads,
            "monthly_appointments": total_appts,
            "conversion_rate": f"{int((hot_leads / total_leads * 100) if total_leads > 0 else 0)}%",
            "estimated_revenue": hot_leads * 1500
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
        res = supabase.table("customers").select("*").order("created_at", desc=True).limit(50).execute()
        return res.data
    except Exception as e:
        logger.error(f"Error fetching leads: {e}")
        return []

@router.get("/appointments")
# ...
@router.get("/funnel")
async def get_funnel():
    # ...
    supabase = get_supabase()
    try:
        leads = supabase.table("customers").select("id", count="exact").execute().count or 0
        
        # Assuming all in DB are 'contacted' roughly
        contacted = leads 
        
        min_score = 50
        qualified = supabase.table("customers").select("id", count="exact").filter("lead_score", "gte", min_score).execute().count or 0
        
        scheduled = supabase.table("agendamentos").select("id", count="exact").execute().count or 0
        
        return [
            {"name": "Leads Totais", "value": leads, "fill": "#8884d8"},
            {"name": "Qualificados", "value": qualified, "fill": "#82ca9d"},
            {"name": "Agendados", "value": scheduled, "fill": "#ffc658"},
            {"name": "Fechados", "value": int(scheduled * 0.4), "fill": "#d0ed57"} # Est 40% close rate
        ]
    except Exception as e:
        return []
