import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain.schemas import (
    DisputeCreateRequest,
    DisputeEventResponse,
    DisputeResponse,
    DisputeReviewRequest,
    DisputeSentRequest,
    DisputeUpdateRequest,
)
from app.infrastructure.orm_models import Claim, DisputeCase, DisputeEvent
from app.interfaces.dependencies import get_db_session
from app.rag.rag_service import RegulatoryCopilotService
from app.rag.vector_store import LocalVectorStore
from app.security.anonymizer import DataAnonymizer
from app.security.rbac import UserRole, require_roles


router = APIRouter(prefix="/api/v1/disputes", tags=["Dispute Workflow"])
VECTOR_INDEX_DIR = Path(__file__).resolve().parents[2] / "ml_models" / "vector_index"
ANONYMIZER = DataAnonymizer()
_vector_store: LocalVectorStore | None = None


def _copilot() -> RegulatoryCopilotService:
    global _vector_store
    if _vector_store is None:
        _vector_store = LocalVectorStore(str(VECTOR_INDEX_DIR))
    return RegulatoryCopilotService(_vector_store)


def _event(
    db: Session,
    case: DisputeCase,
    actor_id: str,
    action: str,
    to_status: str,
    notes: str = "",
    from_status: str | None = None,
) -> None:
    db.add(
        DisputeEvent(
            dispute_case_id=case.id,
            actor_id=actor_id,
            action=action,
            from_status=from_status if from_status is not None else case.status,
            to_status=to_status,
            notes=notes,
        )
    )


def _case_or_404(db: Session, dispute_id: str) -> DisputeCase:
    case = db.scalars(
        select(DisputeCase)
        .options(joinedload(DisputeCase.claim))
        .where(DisputeCase.dispute_id == dispute_id)
    ).first()
    if case is None:
        raise HTTPException(status_code=404, detail="Sanggahan tidak ditemukan")
    return case


def _response(db: Session, case: DisputeCase) -> DisputeResponse:
    history = db.scalars(
        select(DisputeEvent)
        .where(DisputeEvent.dispute_case_id == case.id)
        .order_by(DisputeEvent.created_at.asc(), DisputeEvent.id.asc())
    ).all()
    return DisputeResponse(
        dispute_id=case.dispute_id,
        claim_id=case.claim.claim_id,
        sep_number=ANONYMIZER.mask_sep_number(case.claim.sep_number),
        status=case.status,
        letter_body=case.letter_body,
        legal_source=case.legal_source,
        regulation_ref=case.regulation_ref,
        recommendation=case.recommendation,
        citations=json.loads(case.citations_json or "[]"),
        created_by=case.created_by,
        reviewer_id=case.reviewer_id,
        review_notes=case.review_notes,
        recipient=case.recipient,
        submission_reference=case.submission_reference,
        submitted_at=case.submitted_at,
        sent_at=case.sent_at,
        created_at=case.created_at,
        updated_at=case.updated_at,
        history=[DisputeEventResponse.model_validate(item) for item in history],
    )


@router.get("/", response_model=list[DisputeResponse])
def list_disputes(
    status: str | None = Query(default=None, max_length=30),
    claim_id: str | None = Query(default=None, max_length=50),
    _user: dict[str, str] = Depends(
        require_roles(UserRole.ADMIN_BPJS, UserRole.ADMIN_AUDIT)
    ),
    db: Session = Depends(get_db_session),
) -> list[DisputeResponse]:
    statement = (
        select(DisputeCase)
        .options(joinedload(DisputeCase.claim))
        .order_by(DisputeCase.updated_at.desc(), DisputeCase.id.desc())
        .limit(500)
    )
    if status:
        statement = statement.where(DisputeCase.status == status)
    if claim_id:
        statement = statement.where(DisputeCase.claim_id == claim_id)
    return [_response(db, case) for case in db.scalars(statement).unique().all()]


@router.post("/", response_model=DisputeResponse, status_code=201)
def create_dispute(
    request: DisputeCreateRequest,
    user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS)),
    db: Session = Depends(get_db_session),
) -> DisputeResponse:
    claim = db.scalars(
        select(Claim).options(joinedload(Claim.rule)).where(Claim.claim_id == request.claim_id)
    ).first()
    if claim is None:
        raise HTTPException(status_code=404, detail="Klaim tidak ditemukan")
    if claim.rule is None:
        raise HTTPException(status_code=409, detail="Klaim belum memiliki dasar aturan untuk draf sanggahan")
    if not _copilot().vector_store.index_ready:
        raise HTTPException(status_code=503, detail="Indeks regulasi belum tersedia")

    draft = _copilot().draft_dispute_letter(
        claim_id=claim.claim_id,
        sep_number=claim.sep_number,
        primary_code=claim.rule.primary_code,
        conflicting_code=claim.rule.conflicting_code,
        violation_type=claim.rule.violation_type,
        legal_source=claim.rule.legal_source,
        regulation_ref=claim.rule.regulation_ref,
        clinical_narrative=claim.rule.clinical_narrative,
        recommendation=claim.rule.recommendation,
    )
    case = DisputeCase(
        dispute_id=f"DSP-{uuid.uuid4().hex[:10].upper()}",
        claim_id=claim.claim_id,
        status="draft",
        letter_body=draft["formal_letter"],
        legal_source=claim.rule.legal_source,
        regulation_ref=claim.rule.regulation_ref,
        recommendation=claim.rule.recommendation,
        citations_json=json.dumps(draft["citations"], ensure_ascii=False),
        created_by=user["user_id"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(case)
    db.flush()
    _event(db, case, user["user_id"], "created", "draft", "Draf dibuat dari data klaim dan regulasi.")
    db.commit()
    db.refresh(case)
    return _response(db, case)


@router.get("/{dispute_id}", response_model=DisputeResponse)
def get_dispute(
    dispute_id: str,
    _user: dict[str, str] = Depends(
        require_roles(UserRole.ADMIN_BPJS, UserRole.ADMIN_AUDIT)
    ),
    db: Session = Depends(get_db_session),
) -> DisputeResponse:
    return _response(db, _case_or_404(db, dispute_id))


@router.patch("/{dispute_id}", response_model=DisputeResponse)
def update_dispute(
    dispute_id: str,
    request: DisputeUpdateRequest,
    user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS)),
    db: Session = Depends(get_db_session),
) -> DisputeResponse:
    case = _case_or_404(db, dispute_id)
    if case.status not in {"draft", "needs_revision"}:
        raise HTTPException(status_code=409, detail="Draf hanya dapat diedit saat berstatus draft atau perlu revisi")
    case.letter_body = request.letter_body.strip()
    case.updated_at = datetime.utcnow()
    _event(db, case, user["user_id"], "updated", case.status, "Isi draf diperbarui.")
    db.commit()
    return _response(db, case)


@router.post("/{dispute_id}/submit", response_model=DisputeResponse)
def submit_for_review(
    dispute_id: str,
    user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS)),
    db: Session = Depends(get_db_session),
) -> DisputeResponse:
    case = _case_or_404(db, dispute_id)
    if case.status not in {"draft", "needs_revision"}:
        raise HTTPException(status_code=409, detail="Sanggahan tidak berada pada status yang bisa diajukan")
    previous_status = case.status
    case.status = "in_review"
    case.submitted_at = datetime.utcnow()
    case.updated_at = case.submitted_at
    _event(db, case, user["user_id"], "submitted_for_review", "in_review", from_status=previous_status)
    db.commit()
    return _response(db, case)


@router.post("/{dispute_id}/review", response_model=DisputeResponse)
def review_dispute(
    dispute_id: str,
    request: DisputeReviewRequest,
    user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_AUDIT)),
    db: Session = Depends(get_db_session),
) -> DisputeResponse:
    case = _case_or_404(db, dispute_id)
    if request.action == "close":
        if case.status != "sent":
            raise HTTPException(status_code=409, detail="Sanggahan hanya dapat ditutup setelah dikirim")
        next_status = "closed"
    else:
        if case.status != "in_review":
            raise HTTPException(status_code=409, detail="Sanggahan belum menunggu tinjauan Admin Audit")
        if request.action == "request_revision" and len(request.notes.strip()) < 5:
            raise HTTPException(status_code=422, detail="Catatan revisi minimal 5 karakter")
        next_status = "approved" if request.action == "approve" else "needs_revision"
    previous_status = case.status
    case.reviewer_id = user["user_id"]
    case.review_notes = request.notes.strip() or None
    case.status = next_status
    case.updated_at = datetime.utcnow()
    _event(db, case, user["user_id"], request.action, next_status, request.notes.strip(), previous_status)
    db.commit()
    return _response(db, case)


@router.post("/{dispute_id}/sent", response_model=DisputeResponse)
def mark_dispute_sent(
    dispute_id: str,
    request: DisputeSentRequest,
    user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS)),
    db: Session = Depends(get_db_session),
) -> DisputeResponse:
    case = _case_or_404(db, dispute_id)
    if case.status != "approved":
        raise HTTPException(status_code=409, detail="Sanggahan harus disetujui Admin Audit sebelum dicatat dikirim")
    previous_status = case.status
    case.recipient = request.recipient.strip()
    case.submission_reference = request.submission_reference.strip()
    case.sent_at = datetime.utcnow()
    case.updated_at = case.sent_at
    case.status = "sent"
    _event(db, case, user["user_id"], "marked_sent", "sent", f"Penerima: {case.recipient}; referensi: {case.submission_reference}", previous_status)
    db.commit()
    return _response(db, case)
