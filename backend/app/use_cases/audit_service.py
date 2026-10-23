import json
import re
import time
from typing import Optional

from sqlalchemy.orm import Session

from app.domain.schemas import (
    BatchAuditResponse,
    ClaimDetailResponse,
    ClaimListResponse,
    CodeAuditItem,
)
from app.ml.hybrid_detector import HybridFraudDetector
from app.infrastructure.orm_models import Claim, RegulatoryRule
from app.infrastructure.repositories import ClaimRepository


def _parse_billing_codes(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return [value.strip()] if value and value.strip() else []
    if not isinstance(parsed, list):
        return []
    return [str(code).strip() for code in parsed if str(code).strip()]


def _code_type(code: str, index: int) -> str:
    if re.match(r"^\d{2}(?:\.|$)", code):
        return "ICD-9-CM"
    return "ICD-10-PRIMARY" if index == 0 else "ICD-10-SECONDARY"


def generate_code_breakdown(
    claim: Claim, rule: Optional[RegulatoryRule]
) -> list[CodeAuditItem]:
    codes = _parse_billing_codes(claim.admin_billing_code)
    breakdown = []
    for index, code in enumerate(codes):
        is_violation = rule is not None and code == rule.conflicting_code
        breakdown.append(
            CodeAuditItem(
                code=code,
                code_type=_code_type(code, index),
                description=(
                    rule.clinical_narrative
                    if is_violation and rule is not None
                    else f"Billing code {code}"
                ),
                status="VIOLATION" if is_violation else "VALID",
                violation_type=rule.violation_type if is_violation and rule else None,
                rule_source=(
                    f"{rule.legal_source} | {rule.regulation_ref}"
                    if is_violation and rule
                    else None
                ),
                clinical_note=(
                    rule.clinical_narrative
                    if is_violation and rule
                    else claim.doctor_notes
                ),
            )
        )
    return breakdown


def _apply_hybrid_result(claim: Claim, result: dict) -> Claim:
    claim.is_fraud = result["is_fraud"]
    claim.fraud_type = result["fraud_type"]
    rule_result = result["rule_result"]
    claim.regulatory_rule_id = (
        rule_result["regulatory_rule_id"] if rule_result is not None else None
    )
    claim.potential_saving = (
        max(claim.total_charge - claim.approved_tariff, 0.0)
        if claim.is_fraud
        else 0.0
    )
    claim.audit_notes = (
        result["audit_narrative"]
        if result["review_status"] != "CLEARED"
        else None
    )
    return claim


def evaluate_claim(db: Session, claim: Claim) -> Claim:
    detector = HybridFraudDetector(db)
    result = detector.analyze_claim(
        {
            "claim_id": claim.claim_id,
            "doctor_notes": claim.doctor_notes,
            "admin_billing_code": claim.admin_billing_code,
            "length_of_stay": claim.length_of_stay,
            "total_charge": claim.total_charge,
            "approved_tariff": claim.approved_tariff,
        }
    )
    return _apply_hybrid_result(claim, result)


def get_detailed_claim(
    db: Session, claim_id: str
) -> Optional[ClaimDetailResponse]:
    claim = ClaimRepository.get_by_id(db, claim_id)
    if claim is None:
        return None
    response = ClaimDetailResponse.model_validate(claim)
    analysis = HybridFraudDetector(db).analyze_claim(
        {
            "claim_id": claim.claim_id,
            "doctor_notes": claim.doctor_notes,
            "admin_billing_code": claim.admin_billing_code,
            "length_of_stay": claim.length_of_stay,
            "total_charge": claim.total_charge,
            "approved_tariff": claim.approved_tariff,
        }
    )
    return response.model_copy(
        update={
            "code_breakdown": generate_code_breakdown(claim, claim.rule),
            "risk_score": analysis["risk_score"],
            "reason_narrative": analysis["audit_narrative"],
        }
    )


def run_batch_simulation(db: Session, limit: int) -> BatchAuditResponse:
    started_at = time.perf_counter()
    claims = ClaimRepository.get_batch_claims(db, limit)
    detector = HybridFraudDetector(db)
    flagged_count = 0
    total_saved = 0.0
    for claim in claims:
        result = detector.analyze_claim(
            {
                "claim_id": claim.claim_id,
                "doctor_notes": claim.doctor_notes,
                "admin_billing_code": claim.admin_billing_code,
                "length_of_stay": claim.length_of_stay,
                "total_charge": claim.total_charge,
                "approved_tariff": claim.approved_tariff,
            }
        )
        _apply_hybrid_result(claim, result)
        if claim.is_fraud:
            flagged_count += 1
            total_saved += claim.potential_saving
    db.commit()
    return BatchAuditResponse(
        processed_count=len(claims),
        flagged_count=flagged_count,
        execution_time_seconds=time.perf_counter() - started_at,
        total_saved_idr=total_saved,
        results=[ClaimListResponse.model_validate(claim) for claim in claims],
    )