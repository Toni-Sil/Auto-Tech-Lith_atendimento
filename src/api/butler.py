"""
Butler API Router — Master Admin endpoints for the Mordomo Digital.

All endpoints require Master Admin role (owner + tenant_id=None).
"""

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import get_db
from src.models.butler_log import ButlerLog, ButlerActionType, ButlerSeverity
from src.api.auth import get_current_user
from src.utils.logger import setup_logger

logger = setup_logger(__name__)
butler_router = APIRouter(prefix="/butler", tags=["Butler Agent"])


# ── RBAC gate ─────────────────────────────────────────────────────────────────

async def _require_master(current_user=Depends(get_current_user)):
    if current_user.role not in ["owner", "admin", "master_admin"] or current_user.tenant_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Master Admin only")
    return current_user


# ── Request / Response schemas ─────────────────────────────────────────────────

class RunActionRequest(BaseModel):
    action:    str
    params:    dict = {}
    tenant_id: Optional[int] = None

class OnboardingAdvanceRequest(BaseModel):
    reset: bool = False


# ── Endpoints ─────────────────────────────────────────────────────────────────

@butler_router.get("/status")
async def get_butler_status(
    db: AsyncSession = Depends(get_db),
    _=Depends(_require_master),
):
    """Current infrastructure health snapshot."""
    from src.agents.butler_agent import butler_agent
    from src.config import settings
    try:
        status_obj = await butler_agent.monitor_infrastructure(db, database_url=settings.DATABASE_URL)
        return status_obj.to_dict()
    except Exception as e:
        logger.error(f"Butler status check failed: {e}")
        return {"overall": "unknown", "error": str(e), "timestamp": datetime.utcnow().isoformat()}


@butler_router.get("/logs")
async def get_butler_logs(
    limit: int = 50,
    page: int = 1,
    severity: Optional[str] = None,
    action_type: Optional[str] = None,
    tenant_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(_require_master),
):
    """Paginated butler decision log."""
    stmt = select(ButlerLog).order_by(desc(ButlerLog.timestamp))

    if severity:
        stmt = stmt.where(ButlerLog.severity == severity)
    if action_type:
        stmt = stmt.where(ButlerLog.action_type == action_type)
    if tenant_id:
        stmt = stmt.where(ButlerLog.tenant_id == tenant_id)

    offset = (page - 1) * limit
    stmt = stmt.offset(offset).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    return [
        {
            "id":           r.id,
            "timestamp":    r.timestamp.isoformat() if r.timestamp else None,
            "action_type":  r.action_type.value if r.action_type else None,
            "severity":     r.severity.value if r.severity else None,
            "tenant_id":    r.tenant_id,
            "description":  r.description,
            "result":       r.result,
            "operator":     r.operator,
            "requires_approval": r.requires_approval,
        }
        for r in rows
    ]


@butler_router.get("/churn")
async def get_churn_risks(
    threshold: float = 0.4,
    db: AsyncSession = Depends(get_db),
    _=Depends(_require_master),
):
    """Latest churn risk list (tenants with significant usage drops)."""
    from src.agents.butler.churn_detector import get_churn_risks as _get_risks
    from dataclasses import asdict
    risks = await _get_risks(db, drop_threshold=threshold)
    return [asdict(r) for r in risks]


@butler_router.get("/billing-report")
async def get_billing_report(
    db: AsyncSession = Depends(get_db),
    _=Depends(_require_master),
):
    """Current billing monitor report: quota alerts + financial summary."""
    from src.agents.butler.billing_monitor import generate_consolidated_report
    return await generate_consolidated_report(db)


@butler_router.post("/run-action")
async def run_butler_action(
    req: RunActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_require_master),
):
    """Manually trigger an approved Butler action."""
    from src.agents.butler_agent import butler_agent
    from src.agents.butler.butler_tools import TOOL_REGISTRY

    if req.action not in TOOL_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action '{req.action}'. Available: {list(TOOL_REGISTRY.keys())}"
        )

    result = await butler_agent.run_tool(
        db,
        action_name=req.action,
        params=req.params,
        tenant_id=req.tenant_id,
        operator=f"master:{current_user.id}",
    )
    return result


@butler_router.post("/onboard/{tenant_id}")
async def onboard_tenant(
    tenant_id: int,
    req: OnboardingAdvanceRequest = OnboardingAdvanceRequest(),
    db: AsyncSession = Depends(get_db),
    _=Depends(_require_master),
):
    """Get or advance onboarding state for a tenant."""
    from src.agents.butler_agent import butler_agent
    from src.agents.butler.onboarding import reset_onboarding

    if req.reset:
        reset_onboarding(tenant_id)

    return await butler_agent.onboard_tenant(db, tenant_id=tenant_id)


@butler_router.post("/onboard/{tenant_id}/advance")
async def advance_onboarding(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(_require_master),
):
    """Mark current onboarding step as complete and return next step."""
    from src.agents.butler_agent import butler_agent
    return await butler_agent.advance_tenant_onboarding(db, tenant_id=tenant_id)


@butler_router.get("/scheduler/jobs")
async def list_scheduler_jobs(_=Depends(_require_master)):
    """List all scheduled Butler jobs and their next run times."""
    from src.workers.butler_worker import get_job_status
    return get_job_status()


@butler_router.post("/scheduler/jobs/{job_id}/run-now")
async def trigger_job_now(
    job_id: str,
    _=Depends(_require_master),
):
    """Manually trigger a scheduled job immediately."""
    from src.workers.butler_worker import get_scheduler
    sched = get_scheduler()
    job = sched.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    job.modify(next_run_time=datetime.now())
    return {"status": "triggered", "job_id": job_id}


@butler_router.post("/approve/{log_id}")
async def approve_butler_action(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_require_master),
):
    """
    Approve a pending high-severity Butler action.
    After approval, the action will be executed on the next trigger.
    """
    log_entry = await db.get(ButlerLog, log_id)
    if not log_entry:
        raise HTTPException(status_code=404, detail="Action log not found")
    if log_entry.requires_approval != 1:
        raise HTTPException(status_code=400, detail="This action doesn't require approval")

    # Mark approved
    log_entry.requires_approval = 2
    log_entry.approved_by = f"master:{current_user.id}"
    await db.commit()

    # Now execute the actual tool
    from src.agents.butler_agent import butler_agent
    import json
    meta = log_entry.meta or {}
    action = meta.get("action")
    params = meta.get("params", {})

    if action:
        from src.agents.butler.butler_tools import execute_tool
        result = await execute_tool(action, params, operator=f"master:{current_user.id}")
        log_entry.result = result.get("status", "ok")
        log_entry.detail = json.dumps(result)[:500]
        await db.commit()
        return {"status": "approved_and_executed", "result": result}

    return {"status": "approved", "log_id": log_id}
