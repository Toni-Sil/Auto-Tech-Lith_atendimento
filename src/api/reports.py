from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import RequirePermissions, get_current_user
from src.models.admin import AdminUser
from src.models.database import get_db
from src.services.report_service import report_service

report_router = APIRouter()


@report_router.get("/customers/csv", response_class=PlainTextResponse)
async def export_customers_csv(
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["customers:read"]))],
    db: AsyncSession = Depends(get_db),
):
    """
    Downloads a CSV containing all customers.
    """
    csv_data = await report_service.generate_customers_csv(db, current_user.tenant_id)
    return PlainTextResponse(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=customers_{current_user.tenant_id}.csv"
        },
    )


@report_router.get("/tickets/csv", response_class=PlainTextResponse)
async def export_tickets_csv(
    current_user: Annotated[AdminUser, Depends(RequirePermissions(["tickets:read"]))],
    db: AsyncSession = Depends(get_db),
):
    """
    Downloads a CSV containing all tickets.
    """
    csv_data = await report_service.generate_tickets_csv(db, current_user.tenant_id)
    return PlainTextResponse(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=tickets_{current_user.tenant_id}.csv"
        },
    )
