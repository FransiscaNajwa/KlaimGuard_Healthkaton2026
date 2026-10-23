from sqlalchemy.orm import Session

from app.domain.schemas import AnalyticsDashboardResponse, StatsOverviewResponse
from app.infrastructure.repositories import ClaimRepository


def get_dashboard_overview(db: Session) -> StatsOverviewResponse:
    summary = ClaimRepository.get_summary_stats(db)
    total_claims = summary["total_claims"]
    reviewed_claims = summary["reviewed_claims"]
    audit_coverage = (
        (reviewed_claims / total_claims * 100) if total_claims else 0.0
    )
    return StatsOverviewResponse(
        total_claims=total_claims,
        safe_claims=summary["safe_claims"],
        fraud_claims=summary["fraud_claims"],
        upcoding_count=summary["upcoding_count"],
        unbundling_count=summary["unbundling_count"],
        total_potential_saving_idr=summary["total_potential_saving_idr"],
        audit_coverage_pct=audit_coverage,
    )


def get_analytics_dashboard_data(db: Session) -> AnalyticsDashboardResponse:
    data = ClaimRepository.get_analytics_dashboard(db)
    return AnalyticsDashboardResponse(
        financial_summary=data["financial_summary"],
        los_breakdown=data["los_breakdown"],
        cost_buckets=data["cost_buckets"],
        top_anomalies=data["top_anomalies"],
        high_impact_claims=data["high_impact_claims"],
    )