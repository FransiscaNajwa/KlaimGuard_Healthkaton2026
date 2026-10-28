import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.domain.schemas import (
    DisputeCreateRequest,
    DisputeCommentCreate,
    DisputeCommentResponse,
    DisputeEventResponse,
    DisputeResponse,
    DisputeSummaryResponse,
    DisputeVersionResponse,
    DisputeReviewRequest,
    DisputeReevaluationRequest,
    DisputeSentRequest,
    DisputeUpdateRequest,
)
from app.infrastructure.orm_models import Claim, ClarificationFinding, DisputeCase, DisputeComment, DisputeEvent, DisputeVersion, HospitalResponse, HospitalResponseDocument
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


@router.get("/documents/{document_id}")
def download_rs_document(
    document_id: int,
    _user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS)),
    db: Session = Depends(get_db_session),
) -> FileResponse:
    from app.interfaces.api_rs_portal import UPLOAD_DIR
    document = db.get(HospitalResponseDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    path = UPLOAD_DIR / document.stored_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Berkas dokumen tidak tersedia")
    return FileResponse(path, media_type=document.media_type, filename=document.original_filename)


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
    comments = db.scalars(
        select(DisputeComment).where(DisputeComment.dispute_case_id == case.id)
        .order_by(DisputeComment.created_at.asc(), DisputeComment.id.asc())
    ).all()
    versions = db.scalars(
        select(DisputeVersion).where(DisputeVersion.dispute_case_id == case.id)
        .order_by(DisputeVersion.version_number.desc())
    ).all()
    findings = db.scalars(select(ClarificationFinding).where(ClarificationFinding.dispute_case_id == case.id)).all()
    response_rows = db.scalars(select(HospitalResponse).where(HospitalResponse.dispute_case_id == case.id).order_by(HospitalResponse.version_number.asc())).all()
    age = max(0, int((datetime.utcnow() - case.submitted_at).total_seconds() // 3600)) if case.submitted_at and case.status == "in_review" else None
    return DisputeResponse(
        dispute_id=case.dispute_id,
        claim_id=case.claim.claim_id,
        sep_number=ANONYMIZER.mask_sep_number(case.claim.sep_number),
        status=case.status,
        template_code=getattr(case, "template_code", "formal") or "formal",
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
        deadline_at=case.deadline_at,
        received_at=case.received_at,
        created_at=case.created_at,
        updated_at=case.updated_at,
        history=[DisputeEventResponse.model_validate(item) for item in history],
        # SQLAlchemy ORM rows are not Pydantic dictionaries. Serialize explicitly
        # so comment create/list endpoints return the same valid response shape.
        comments=[
            DisputeCommentResponse(
                actor_id=item.actor_id,
                actor_role=item.actor_role,
                body=item.body,
                created_at=item.created_at,
            )
            for item in comments
        ],
        versions=[
            DisputeVersionResponse(
                version_number=item.version_number,
                letter_body=item.letter_body,
                actor_id=item.actor_id,
                note=item.note,
                created_at=item.created_at,
            )
            for item in versions
        ],
        current_version=max((item.version_number for item in versions), default=1),
        is_overdue=bool(age is not None and age >= 48),
        review_age_hours=age,
        findings=[{"type": row.finding_type, "title": row.title, "description": row.description,
                   "regulation_reference": row.regulation_reference,
                   "requested_documents": json.loads(row.requested_documents_json or "[]")} for row in findings],
        hospital_responses=[{
            "version": row.version_number, "status": row.status, "explanation_type": row.explanation_type,
            "notes": row.notes, "submitted_by": row.submitted_by, "submitted_at": row.submitted_at,
            "documents": [{"id": doc.id, "filename": doc.original_filename, "size_bytes": doc.size_bytes}
                          for doc in db.scalars(select(HospitalResponseDocument).where(HospitalResponseDocument.response_id == row.id)).all()],
        } for row in response_rows],
    )


@router.get("/summary", response_model=DisputeSummaryResponse)
def dispute_summary(
    _user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS)),
    db: Session = Depends(get_db_session),
) -> DisputeSummaryResponse:
    rows = db.execute(
        select(DisputeCase.status, func.count(DisputeCase.id))
        .where(DisputeCase.status != "cancelled")
        .group_by(DisputeCase.status)
    ).all()
    counts = {status: count for status, count in rows}
    oldest = db.scalar(select(func.min(DisputeCase.submitted_at)).where(DisputeCase.status == "in_review"))
    oldest_hours = max(0, int((datetime.utcnow() - oldest).total_seconds() // 3600)) if oldest else None
    now = datetime.utcnow()
    sent_cases = db.scalars(select(DisputeCase).where(DisputeCase.status == "sent")).all()
    waiting_response = 0
    waiting_reassessment = 0
    late_response = 0
    for case in sent_cases:
        latest_response = db.scalars(select(HospitalResponse).where(HospitalResponse.dispute_case_id == case.id).order_by(HospitalResponse.version_number.desc())).first()
        has_submitted_response = bool(latest_response and latest_response.status == "submitted")
        if has_submitted_response:
            waiting_reassessment += 1
        else:
            waiting_response += 1
            if case.sent_at and case.sent_at <= now - timedelta(hours=48):
                late_response += 1
    return DisputeSummaryResponse(
        total=sum(counts.values()), drafts=counts.get("draft", 0), in_review=counts.get("in_review", 0),
        overdue_review=db.scalar(select(func.count(DisputeCase.id)).where(DisputeCase.status == "in_review", DisputeCase.submitted_at <= datetime.utcnow() - timedelta(hours=48))) or 0,
        needs_revision=counts.get("needs_revision", 0), approved=counts.get("approved", 0),
        sent=counts.get("sent", 0), closed=counts.get("closed", 0), oldest_pending_hours=oldest_hours,
        waiting_hospital_response=waiting_response,
        waiting_reassessment=waiting_reassessment,
        late_hospital_response=late_response,
    )


@router.get("/", response_model=list[DisputeResponse])
def list_disputes(
    status: str | None = Query(default=None, max_length=30),
    claim_id: str | None = Query(default=None, max_length=50),
    _user: dict[str, str] = Depends(
        require_roles(UserRole.ADMIN_BPJS)
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
    else:
        statement = statement.where(DisputeCase.status != "cancelled")
    if claim_id:
        statement = statement.where(DisputeCase.claim_id == claim_id)
    return [_response(db, case) for case in db.scalars(statement).unique().all()]


@router.delete("/{dispute_id}", response_model=DisputeResponse)
def delete_dispute(
    dispute_id: str,
    user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS)),
    db: Session = Depends(get_db_session),
) -> DisputeResponse:
    case = _case_or_404(db, dispute_id)
    if case.status not in {"draft", "in_review", "needs_revision"}:
        raise HTTPException(
            status_code=409,
            detail="Ajuan yang sudah disetujui atau dikirim ke RS tidak dapat dihapus",
        )
    submitted_response = db.scalar(
        select(HospitalResponse.id).where(
            HospitalResponse.dispute_case_id == case.id,
            HospitalResponse.status == "submitted",
        ).limit(1)
    )
    if submitted_response is not None:
        raise HTTPException(status_code=409, detail="Ajuan dengan respons RS tidak dapat dihapus")

    previous_status = case.status
    case.status = "cancelled"
    case.updated_at = datetime.utcnow()
    _event(
        db,
        case,
        user["user_id"],
        "cancelled",
        "cancelled",
        "Ajuan klarifikasi dihapus dari daftar aktif oleh Admin Verifikator.",
        previous_status,
    )
    db.commit()
    return _response(db, case)


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
    letter_body = draft["formal_letter"]
    if request.template_code == "ringkas":
        letter_body = (f"Kepada Yth.\nKomite Audit Klinis Rumah Sakit\n\nPerihal: Klarifikasi klaim {claim.claim_id}\n\n"
            f"Ditemukan ketidaksesuaian: {claim.rule.violation_type}.\n\nDasar: {claim.rule.legal_source}; {claim.rule.regulation_ref}.\n"
            f"Rekomendasi: {claim.rule.recommendation}\n\nMohon klarifikasi dan dokumen pendukung yang relevan. Draf ini wajib ditinjau sebelum dikirim.")
    elif request.template_code == "rinci":
        letter_body = (f"{draft['formal_letter']}\n\nRINGKASAN KLINIS\n{claim.rule.clinical_narrative}\n\n"
            f"DASAR HUKUM\n{claim.rule.legal_source}\n{claim.rule.regulation_ref}\n\nREKOMENDASI KOREKSI\n{claim.rule.recommendation}")
    case = DisputeCase(
        dispute_id=f"DSP-{uuid.uuid4().hex[:10].upper()}",
        claim_id=claim.claim_id,
        status="draft",
        template_code=request.template_code,
        letter_body=letter_body,
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
    finding_type = {"UPCODING": "koding", "UNBUNDLING": "koding"}.get(claim.rule.category, "administratif")
    db.add(ClarificationFinding(
        dispute_case_id=case.id,
        finding_type=finding_type,
        title=f"Temuan {claim.rule.violation_type}",
        description=claim.rule.clinical_narrative,
        regulation_reference=f"{claim.rule.legal_source}; {claim.rule.regulation_ref}",
        requested_documents_json=json.dumps(["Resume medis", "Hasil pemeriksaan penunjang", "Dokumen pendukung koding"], ensure_ascii=False),
    ))
    db.add(DisputeVersion(dispute_case_id=case.id, version_number=1, letter_body=letter_body, actor_id=user["user_id"], note="Draf awal"))
    _event(db, case, user["user_id"], "created", "draft", "Draf dibuat dari data klaim dan regulasi.")
    db.commit()
    db.refresh(case)
    return _response(db, case)


@router.get("/{dispute_id}", response_model=DisputeResponse)
def get_dispute(
    dispute_id: str,
    _user: dict[str, str] = Depends(
        require_roles(UserRole.ADMIN_BPJS)
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
    next_body = request.letter_body.strip()
    if next_body != case.letter_body:
        latest = db.scalar(select(func.max(DisputeVersion.version_number)).where(DisputeVersion.dispute_case_id == case.id)) or 0
        case.letter_body = next_body
        db.add(DisputeVersion(dispute_case_id=case.id, version_number=latest + 1, letter_body=next_body, actor_id=user["user_id"], note="Perubahan draf"))
    case.updated_at = datetime.utcnow()
    _event(db, case, user["user_id"], "updated", case.status, "Isi draf diperbarui.")
    db.commit()
    return _response(db, case)


@router.post("/{dispute_id}/comments", response_model=DisputeResponse)
def add_dispute_comment(
    dispute_id: str, request: DisputeCommentCreate,
    user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS)),
    db: Session = Depends(get_db_session),
) -> DisputeResponse:
    case = _case_or_404(db, dispute_id)
    db.add(DisputeComment(dispute_case_id=case.id, actor_id=user["user_id"], actor_role=user["role"], body=request.body.strip()))
    case.updated_at = datetime.utcnow()
    _event(db, case, user["user_id"], "commented", case.status, "Menambahkan komentar pada diskusi sanggahan.")
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
    user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS)),
    db: Session = Depends(get_db_session),
) -> DisputeResponse:
    case = _case_or_404(db, dispute_id)
    if case.status != "in_review":
        raise HTTPException(status_code=409, detail="Klarifikasi belum berada pada tahap pemeriksaan akhir")
    if request.action == "request_revision" and len(request.notes.strip()) < 5:
        raise HTTPException(status_code=422, detail="Catatan revisi minimal 5 karakter")
    next_status = "sent" if request.action == "approve" else "needs_revision"
    previous_status = case.status
    case.reviewer_id = user["user_id"]
    case.review_notes = request.notes.strip() or None
    case.status = next_status
    if request.action == "approve":
        if case.claim.facility_id is None or case.claim.facility is None:
            raise HTTPException(status_code=409, detail="Klaim belum ditautkan ke faskes penerima")
        case.recipient = case.claim.facility.name
        case.submission_reference = f"PORTAL-{case.dispute_id}"
        case.sent_at = datetime.utcnow()
        case.deadline_at = case.sent_at + timedelta(days=3)
    case.updated_at = datetime.utcnow()
    event_action = "approved_and_sent_to_hospital" if request.action == "approve" else request.action
    _event(db, case, user["user_id"], event_action, next_status, request.notes.strip(), previous_status)
    if request.notes.strip():
        db.add(DisputeComment(dispute_case_id=case.id, actor_id=user["user_id"], actor_role=user["role"], body=request.notes.strip()))
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
        raise HTTPException(status_code=409, detail="Klarifikasi harus disetujui Verifikator sebelum dicatat dikirim")
    if case.claim.facility_id is None:
        raise HTTPException(status_code=409, detail="Klaim belum ditautkan ke faskes penerima")
    previous_status = case.status
    case.recipient = request.recipient.strip()
    case.submission_reference = request.submission_reference.strip()
    case.sent_at = datetime.utcnow()
    case.deadline_at = case.sent_at + timedelta(days=3)
    case.updated_at = case.sent_at
    case.status = "sent"
    _event(db, case, user["user_id"], "marked_sent", "sent", f"Penerima: {case.recipient}; referensi: {case.submission_reference}", previous_status)
    db.commit()
    return _response(db, case)


@router.post("/{dispute_id}/reevaluate", response_model=DisputeResponse)
def reevaluate_hospital_response(
    dispute_id: str,
    request: DisputeReevaluationRequest,
    user: dict[str, str] = Depends(require_roles(UserRole.ADMIN_BPJS)),
    db: Session = Depends(get_db_session),
) -> DisputeResponse:
    case = _case_or_404(db, dispute_id)
    latest = db.scalars(select(HospitalResponse).where(HospitalResponse.dispute_case_id == case.id).order_by(HospitalResponse.version_number.desc())).first()
    if case.status != "sent" or latest is None or latest.status != "submitted":
        raise HTTPException(status_code=409, detail="Belum ada respons RS yang menunggu penilaian ulang")
    note = request.notes.strip()
    if request.action == "accept":
        previous = case.status
        case.status = "closed"
        _event(db, case, user["user_id"], "accepted_hospital_response", "closed", note or "Penjelasan rumah sakit diterima; pencatatan selesai di aplikasi.", previous)
    elif request.action == "request_additional":
        if len(note) < 5:
            raise HTTPException(status_code=422, detail="Alasan klarifikasi tambahan minimal 5 karakter")
        db.add(HospitalResponse(dispute_case_id=case.id, version_number=latest.version_number + 1,
                                explanation_type=latest.explanation_type, notes="", status="draft", submitted_by=""))
        case.review_notes = note
        case.sent_at = datetime.utcnow()
        case.deadline_at = case.sent_at + timedelta(days=3)
        _event(db, case, user["user_id"], "requested_additional_clarification", "sent", note, "sent")
    case.updated_at = datetime.utcnow()
    db.commit()
    return _response(db, case)
