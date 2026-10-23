from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.domain.schemas import FeedbackCreate, FeedbackResponse
from app.infrastructure.repositories import ClaimRepository, FeedbackRepository
from app.interfaces.dependencies import get_db_session
from app.security.anonymizer import DataAnonymizer
from app.security.audit_logger import CryptographicAuditLogger
from app.security.hitl_guard import HumanInTheLoopGuard
from app.security.rbac import UserRole, require_roles


router = APIRouter(prefix="/api/v1/feedback", tags=["Verifier Feedback"])
ANONYMIZER = DataAnonymizer()


@router.post("/", response_model=FeedbackResponse, status_code=201)
def create_feedback(
    feedback_data: FeedbackCreate,
    current_user: dict[str, str] = Depends(
        require_roles(UserRole.ADMIN_AUDIT)
    ),
    db: Session = Depends(get_db_session),
) -> FeedbackResponse:
    claim = ClaimRepository.get_by_id(db, feedback_data.claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    sanitized_notes = ANONYMIZER.sanitize_doctor_notes(feedback_data.notes)
    authenticated_feedback = feedback_data.model_copy(
        update={
            "verifier_id": current_user["user_id"],
            "notes": sanitized_notes,
        }
    )
    ai_verdict = {
        "is_fraud": claim.is_fraud,
        "risk_score": 0.98 if claim.regulatory_rule_id else 0.0,
        "rule_result": (
            {"regulatory_rule_id": claim.regulatory_rule_id}
            if claim.regulatory_rule_id
            else None
        ),
    }
    guard = HumanInTheLoopGuard(current_verifier_id=current_user["user_id"])
    try:
        override_validation = guard.validate_override(
            ai_verdict,
            authenticated_feedback.decision,
            authenticated_feedback.notes,
        )
        if authenticated_feedback.decision == "DISPUTE_TO_RS":
            guard.enforce_safety_boundary("DISPUTE")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    action_type = {
        "DISPUTE_TO_RS": "DISPUTE_SENT",
        "CONFIRMED_FRAUD": (
            "FLAG_OVERRIDDEN"
            if override_validation["approved_override"]
            else "FLAG_CONFIRMED"
        ),
        "APPROVED_SAFE": (
            "FLAG_OVERRIDDEN"
            if override_validation["approved_override"]
            else "REVIEW_CONFIRMED"
        ),
    }[authenticated_feedback.decision]
    audit_logger = CryptographicAuditLogger(db)
    feedback = FeedbackRepository.create(db, authenticated_feedback)
    audit_logger.log_verification_action(
        verifier_id=current_user["user_id"],
        claim_id=claim.claim_id,
        action_type=action_type,
        details={
            "decision": authenticated_feedback.decision,
            "notes": sanitized_notes,
            "override_validation": override_validation,
            "claim_snapshot": {
                "sep_number": ANONYMIZER.mask_sep_number(claim.sep_number),
                "doctor_notes": ANONYMIZER.sanitize_doctor_notes(
                    claim.doctor_notes
                ),
                "admin_billing_code": claim.admin_billing_code,
                "is_fraud": claim.is_fraud,
                "regulatory_rule_id": claim.regulatory_rule_id,
                "legal_source": claim.rule.legal_source if claim.rule else None,
                "regulation_ref": claim.rule.regulation_ref if claim.rule else None,
            },
        },
    )
    db.refresh(feedback)
    return FeedbackResponse.model_validate(feedback)


@router.get("/{claim_id}", response_model=list[FeedbackResponse])
def get_claim_feedback(
    claim_id: str,
    _current_user: dict[str, str] = Depends(
        require_roles(UserRole.ADMIN_BPJS, UserRole.ADMIN_AUDIT)
    ),
    db: Session = Depends(get_db_session),
) -> list[FeedbackResponse]:
    if ClaimRepository.get_by_id(db, claim_id) is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    feedback = FeedbackRepository.get_by_claim_id(db, claim_id)
    responses = [FeedbackResponse.model_validate(item) for item in feedback]
    for response in responses:
        response.notes = ANONYMIZER.sanitize_doctor_notes(response.notes)
    return responses
