import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.interfaces.dependencies import get_db_session
from app.infrastructure.security_models import AuditLogEntry
from app.infrastructure.orm_models import HospitalActivity
from app.security.rbac import UserRole, require_roles


router = APIRouter(
    prefix="/api/v1/audit",
    tags=["Audit Trail"],
    dependencies=[Depends(require_roles(UserRole.ADMIN_BPJS))],
)


@router.get("/logs")
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    AuditLogEntry.__table__.create(bind=db.get_bind(), checkfirst=True)
    total = db.scalar(select(func.count()).select_from(AuditLogEntry)) or 0
    entries = db.scalars(
        select(AuditLogEntry)
        .order_by(AuditLogEntry.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    rows = []
    for entry in entries:
        try:
            details = json.loads(entry.details_json)
        except (TypeError, json.JSONDecodeError):
            details = {}
        rows.append(
            {
                "id": entry.id,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "verifier_id": entry.verifier_id,
                "claim_id": entry.claim_id,
                "action_type": entry.action_type,
                "decision": details.get("decision", entry.action_type),
                "notes": details.get("notes", ""),
                "previous_hash": entry.previous_hash,
                "current_hash": entry.current_hash,
            }
        )
    return {
        "data": rows,
        "total_records": total,
        "current_page": page,
        "total_pages": (total + limit - 1) // limit if total else 0,
        "limit": limit,
    }


@router.get("/hospital-activity")
def list_hospital_activity(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    total = db.scalar(select(func.count()).select_from(HospitalActivity)) or 0
    entries = db.scalars(
        select(HospitalActivity)
        .order_by(HospitalActivity.created_at.desc(), HospitalActivity.id.desc())
        .offset((page - 1) * limit).limit(limit)
    ).all()
    return {
        "data": [{
            "user_id": item.user_id, "facility_code": item.facility_code,
            "dispute_case_id": item.dispute_case_id, "action": item.action,
            "response_version": item.response_version, "details": item.details,
            "created_at": item.created_at,
        } for item in entries],
        "total_records": total, "current_page": page,
        "total_pages": (total + limit - 1) // limit if total else 0,
    }
