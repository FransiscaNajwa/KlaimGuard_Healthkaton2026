from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.infrastructure.orm_models import Claim, HealthFacility, HospitalAccount
from app.interfaces.dependencies import get_db_session
from app.security.auth import (
    ADMIN_BPJS_USERNAME,
    RS_DEMO_USERNAME,
    RS_DEMO_FACILITY_CODE,
    hash_password,
)
from app.security.rbac import UserRole, require_roles


router = APIRouter(
    prefix="/api/v1/facilities",
    tags=["Facility Management"],
    dependencies=[Depends(require_roles(UserRole.ADMIN_BPJS))],
)


class FacilityCreateRequest(BaseModel):
    facility_code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=2, max_length=160)
    address: str = Field(default="", max_length=1000)
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=10, max_length=128)
    claim_ids: list[str] = Field(min_length=1, max_length=100)


@router.get("")
def list_facilities(db: Session = Depends(get_db_session)) -> list[dict]:
    facilities = db.scalars(select(HealthFacility).order_by(HealthFacility.name)).all()
    accounts = db.scalars(select(HospitalAccount)).all()
    account_by_facility = {account.facility_id: account for account in accounts}
    return [
        {
            "id": facility.id,
            "facility_code": facility.facility_code,
            "name": facility.name,
            "address": facility.address,
            "username": (
                account_by_facility[facility.id].username
                if facility.id in account_by_facility
                else RS_DEMO_USERNAME
                if facility.facility_code == RS_DEMO_FACILITY_CODE
                else None
            ),
            "account_active": account_by_facility[facility.id].is_active
            if facility.id in account_by_facility
            else facility.facility_code == RS_DEMO_FACILITY_CODE,
            "claim_count": db.scalar(
                select(func.count(Claim.id)).where(Claim.facility_id == facility.id)
            )
            or 0,
        }
        for facility in facilities
    ]


@router.get("/claim-options")
def list_claim_options(
    search: str = Query(default="", max_length=100),
    db: Session = Depends(get_db_session),
) -> list[dict[str, str | None]]:
    statement = select(Claim.claim_id, HealthFacility.name).outerjoin(
        HealthFacility, Claim.facility_id == HealthFacility.id
    )
    if search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(Claim.claim_id.ilike(term), Claim.sep_number.ilike(term))
        )
    rows = db.execute(statement.order_by(Claim.claim_id).limit(100)).all()
    return [
        {"claim_id": claim_id, "current_facility": facility_name}
        for claim_id, facility_name in rows
    ]


@router.post("", status_code=201)
def create_facility(
    request: FacilityCreateRequest,
    user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS)),
    db: Session = Depends(get_db_session),
) -> dict:
    facility_code = request.facility_code.strip().upper()
    username = request.username.strip()
    reserved_usernames = {
        ADMIN_BPJS_USERNAME.casefold(),
        RS_DEMO_USERNAME.casefold(),
    }
    if username.casefold() in reserved_usernames:
        raise HTTPException(status_code=409, detail="Username sudah digunakan akun sistem")
    if db.scalar(select(HealthFacility.id).where(func.upper(HealthFacility.facility_code) == facility_code)):
        raise HTTPException(status_code=409, detail="Kode faskes sudah terdaftar")
    if db.scalar(select(HospitalAccount.id).where(func.lower(HospitalAccount.username) == username.lower())):
        raise HTTPException(status_code=409, detail="Username petugas RS sudah terdaftar")

    claim_ids = list(dict.fromkeys(item.strip().upper() for item in request.claim_ids if item.strip()))
    if not claim_ids:
        raise HTTPException(status_code=422, detail="Pilih setidaknya satu klaim untuk faskes ini")
    claims = db.scalars(select(Claim).where(Claim.claim_id.in_(claim_ids))).all()
    found_ids = {claim.claim_id.upper() for claim in claims}
    missing_ids = [claim_id for claim_id in claim_ids if claim_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=422, detail=f"ID klaim tidak ditemukan: {', '.join(missing_ids[:10])}")

    facility = HealthFacility(
        facility_code=facility_code,
        name=request.name.strip(),
        address=request.address.strip(),
    )
    db.add(facility)
    db.flush()
    account = HospitalAccount(
        username=username,
        password_hash=hash_password(request.password),
        facility_id=facility.id,
    )
    db.add(account)
    for claim in claims:
        claim.facility_id = facility.id
    db.commit()
    return {
        "id": facility.id,
        "facility_code": facility.facility_code,
        "name": facility.name,
        "username": account.username,
        "assigned_claims": len(claims),
        "created_by": user["user_id"],
    }
