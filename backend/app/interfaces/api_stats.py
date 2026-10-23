from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.domain.schemas import AnalyticsDashboardResponse, StatsOverviewResponse
from app.interfaces.dependencies import get_db_session
from app.security.rbac import UserRole, require_roles
from app.use_cases.stats_service import (
    get_analytics_dashboard_data,
    get_dashboard_overview,
)


router = APIRouter(
    prefix="/api/v1/stats",
    tags=["Analytics & KPI"],
)


@router.get("/overview", response_model=StatsOverviewResponse)
def dashboard_overview(
    db: Session = Depends(get_db_session),
    _current_user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS, UserRole.ADMIN_AUDIT)),
) -> StatsOverviewResponse:
    return get_dashboard_overview(db)


@router.get("/analytics", response_model=AnalyticsDashboardResponse)
def analytics_dashboard(
    db: Session = Depends(get_db_session),
    _current_user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS, UserRole.ADMIN_AUDIT)),
) -> AnalyticsDashboardResponse:
    return get_analytics_dashboard_data(db)
