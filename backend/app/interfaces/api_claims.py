import json
from math import ceil
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.domain.schemas import (
    BatchAuditRequest,
    BatchAuditResponse,
    ClaimDetailResponse,
    ClaimFilterParams,
    ClaimListResponse,
    ClaimPaginationResponse,
    ManualClaimAnalysisRequest,
    ManualClaimAnalysisResponse,
)
from app.ml.hybrid_detector import HybridFraudDetector
from app.infrastructure.repositories import ClaimRepository
from app.interfaces.dependencies import get_db_session
from app.security.anonymizer import DataAnonymizer
from app.security.rbac import UserRole, require_roles
from app.use_cases.audit_service import get_detailed_claim, run_batch_simulation


router = APIRouter(
    prefix="/api/v1/claims",
    tags=["Claims Audit"],
    dependencies=[Depends(require_roles(UserRole.ADMIN_BPJS, UserRole.ADMIN_AUDIT))],
)
ANONYMIZER = DataAnonymizer()


def _safe_claim_response(claim) -> ClaimListResponse:
    response = ClaimListResponse.model_validate(claim)
    response.sep_number = ANONYMIZER.mask_sep_number(response.sep_number)
    response.doctor_notes = ANONYMIZER.sanitize_doctor_notes(response.doctor_notes)
    return response


@router.get("/", response_model=ClaimPaginationResponse)
def list_claims(
    params: Annotated[ClaimFilterParams, Query()],
    db: Session = Depends(get_db_session),
) -> ClaimPaginationResponse:
    total, claims = ClaimRepository.get_paginated(db, params)
    return ClaimPaginationResponse(
        total_records=total,
        current_page=params.skip // params.limit + 1,
        total_pages=ceil(total / params.limit) if total else 0,
        data=[_safe_claim_response(claim) for claim in claims],
    )


@router.get("/{claim_id}", response_model=ClaimDetailResponse)
def get_claim_detail(
    claim_id: str, db: Session = Depends(get_db_session)
) -> ClaimDetailResponse:
    claim = get_detailed_claim(db, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    claim.sep_number = ANONYMIZER.mask_sep_number(claim.sep_number)
    claim.doctor_notes = ANONYMIZER.sanitize_doctor_notes(claim.doctor_notes)
    if claim.audit_notes:
        claim.audit_notes = ANONYMIZER.sanitize_doctor_notes(claim.audit_notes)
    for item in claim.code_breakdown:
        item.clinical_note = ANONYMIZER.sanitize_doctor_notes(item.clinical_note)
    claim.reason_narrative = ANONYMIZER.sanitize_doctor_notes(claim.reason_narrative)
    return claim


@router.post("/analyze", response_model=ManualClaimAnalysisResponse)
def analyze_manual_claim(
    request: ManualClaimAnalysisRequest,
    db: Session = Depends(get_db_session),
    _current_user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_AUDIT)),
) -> ManualClaimAnalysisResponse:
    analysis = HybridFraudDetector(db).analyze_claim(
        {
            "claim_id": request.claim_id,
            "doctor_notes": request.doctor_notes,
            "admin_billing_code": request.admin_billing_code,
            "length_of_stay": request.length_of_stay,
            "total_charge": request.total_charge,
            "approved_tariff": request.total_charge,
        }
    )
    rule = analysis["rule_result"]
    codes = request.admin_billing_code
    code_breakdown = [
        {
            "code": code,
            "code_type": "ICD-10-PRIMARY" if index == 0 else "ICD-10-SECONDARY",
            "description": rule["clinical_narrative"] if rule and code == rule["conflicting_code"] else f"Billing code {code}",
            "status": "VIOLATION" if rule and code == rule["conflicting_code"] else "VALID",
            "violation_type": rule["violation_type"] if rule and code == rule["conflicting_code"] else None,
            "rule_source": f"{rule['legal_source']} | {rule['regulation_ref']}" if rule and code == rule["conflicting_code"] else None,
            "clinical_note": ANONYMIZER.sanitize_doctor_notes(request.doctor_notes),
        }
        for index, code in enumerate(codes)
    ]
    return ManualClaimAnalysisResponse(
        claim_id=request.claim_id,
        sep_number="Belum tersedia",
        doctor_notes=ANONYMIZER.sanitize_doctor_notes(request.doctor_notes),
        admin_billing_code=json.dumps(codes),
        length_of_stay=request.length_of_stay,
        total_charge=request.total_charge,
        approved_tariff=0,
        potential_saving=0,
        is_fraud=analysis["is_fraud"],
        fraud_type=analysis["fraud_type"],
        risk_score=analysis["risk_score"],
        reason_narrative=ANONYMIZER.sanitize_doctor_notes(analysis["audit_narrative"]),
        audit_notes=ANONYMIZER.sanitize_doctor_notes(analysis["audit_narrative"]),
        rule=rule,
        code_breakdown=code_breakdown,
    )


@router.post("/simulate-batch", response_model=BatchAuditResponse)
def simulate_batch(
    request: BatchAuditRequest,
    db: Session = Depends(get_db_session),
    _current_user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_AUDIT)),
) -> BatchAuditResponse:
    response = run_batch_simulation(db, request.limit)
    for claim in response.results:
        claim.sep_number = ANONYMIZER.mask_sep_number(claim.sep_number)
        claim.doctor_notes = ANONYMIZER.sanitize_doctor_notes(claim.doctor_notes)
    return response
