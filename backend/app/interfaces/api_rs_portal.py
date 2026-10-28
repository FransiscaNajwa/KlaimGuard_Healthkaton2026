import json
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload

from app.infrastructure.database import SessionLocal
from app.infrastructure.orm_models import (
    Claim, ClarificationFinding, DisputeCase, DisputeEvent, HospitalActivity,
    HospitalResponse, HospitalResponseDocument,
)
from app.interfaces.dependencies import get_db_session
from app.security.anonymizer import DataAnonymizer
from app.security.rbac import UserRole, require_roles


router = APIRouter(prefix="/api/v1/rs", tags=["Portal Rumah Sakit"])
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "rs_responses"
MAX_FILE_BYTES = 10 * 1024 * 1024
ANONYMIZER = DataAnonymizer()


class ResponseDraftRequest(BaseModel):
    explanation_type: str = Field(pattern="^(administratif|koding|klinis)$")
    notes: str = Field(default="", max_length=10000)


def _rs_user(user: dict[str, str] = Depends(require_roles(UserRole.PETUGAS_KLAIM_RS))) -> dict[str, str]:
    if not user.get("facility_code"):
        raise HTTPException(status_code=403, detail="Akun RS belum terikat ke faskes")
    return user


def _case_for_facility(db: Session, dispute_id: str, facility_code: str) -> DisputeCase:
    case = db.scalars(
        select(DisputeCase)
        .join(Claim, Claim.claim_id == DisputeCase.claim_id)
        .options(joinedload(DisputeCase.claim).joinedload(Claim.facility))
        .where(DisputeCase.dispute_id == dispute_id, Claim.facility.has(facility_code=facility_code))
    ).first()
    if case is None:
        # Do not disclose whether a clarification belonging to another facility exists.
        raise HTTPException(status_code=404, detail="Permintaan klarifikasi tidak ditemukan")
    if case.status not in {"sent", "closed"}:
        raise HTTPException(status_code=404, detail="Permintaan klarifikasi tidak ditemukan")
    return case


def _log(db: Session, user: dict[str, str], action: str, case: DisputeCase | None = None,
         version: int | None = None, details: str = "") -> None:
    db.add(HospitalActivity(
        user_id=user["user_id"], facility_code=user["facility_code"],
        dispute_case_id=case.id if case else None, action=action,
        response_version=version, details=details,
    ))


def _current_response(db: Session, case: DisputeCase) -> HospitalResponse | None:
    return db.scalars(
        select(HospitalResponse)
        .where(HospitalResponse.dispute_case_id == case.id)
        .order_by(HospitalResponse.version_number.desc())
    ).first()


def _case_summary(db: Session, case: DisputeCase) -> dict:
    response = _current_response(db, case)
    findings = db.scalars(select(ClarificationFinding).where(ClarificationFinding.dispute_case_id == case.id)).all()
    if case.status == "closed":
        status = "completed"
    elif response and response.status == "submitted":
        status = "responded"
    else:
        status = "needs_response"
    return {
        "clarification_id": case.dispute_id,
        "claim_id": case.claim.claim_id,
        "sep_number": ANONYMIZER.mask_sep_number(case.claim.sep_number),
        "facility_name": case.claim.facility.name if case.claim.facility else "Faskes demo",
        "issued_at": case.sent_at,
        "received_at": case.received_at,
        "deadline_at": case.deadline_at,
        "status": status,
        "findings_count": len(findings),
        "response_version": response.version_number if response else None,
    }


@router.get("/profile")
def facility_profile(user: dict[str, str] = Depends(_rs_user), db: Session = Depends(get_db_session)) -> dict:
    from app.infrastructure.orm_models import HealthFacility
    facility = db.scalars(select(HealthFacility).where(HealthFacility.facility_code == user["facility_code"])).first()
    if facility is None:
        raise HTTPException(status_code=404, detail="Faskes akun ini belum tersedia")
    return {"facility_code": facility.facility_code, "name": facility.name, "address": facility.address}


@router.get("/dashboard")
def dashboard(user: dict[str, str] = Depends(_rs_user), db: Session = Depends(get_db_session)) -> dict:
    cases = db.scalars(
        select(DisputeCase).join(Claim, Claim.claim_id == DisputeCase.claim_id)
        .options(joinedload(DisputeCase.claim).joinedload(Claim.facility))
        .where(Claim.facility.has(facility_code=user["facility_code"]), DisputeCase.status.in_(["sent", "closed"]))
        .order_by(DisputeCase.updated_at.desc())
    ).unique().all()
    summaries = [_case_summary(db, case) for case in cases]
    now = datetime.utcnow()
    return {
        "needs_response": sum(item["status"] == "needs_response" and (item["response_version"] or 0) <= 1 for item in summaries),
        "waiting_bpjs_review": sum(item["status"] == "responded" for item in summaries),
        "needs_correction": sum(item["status"] == "needs_response" and (item["response_version"] or 0) > 1 for item in summaries),
        "completed": sum(item["status"] == "completed" for item in summaries),
        "approaching_deadline": sum(item["status"] == "needs_response" and item["deadline_at"] is not None and 0 <= (item["deadline_at"] - now).total_seconds() <= 24 * 3600 for item in summaries),
    }


@router.get("/clarifications")
def list_clarifications(user: dict[str, str] = Depends(_rs_user), db: Session = Depends(get_db_session)) -> list[dict]:
    cases = db.scalars(
        select(DisputeCase).join(Claim, Claim.claim_id == DisputeCase.claim_id)
        .options(joinedload(DisputeCase.claim).joinedload(Claim.facility))
        .where(Claim.facility.has(facility_code=user["facility_code"]), DisputeCase.status.in_(["sent", "closed"]))
        .order_by(DisputeCase.updated_at.desc())
    ).unique().all()
    return [_case_summary(db, case) for case in cases]


@router.get("/clarifications/{dispute_id}")
def clarification_detail(dispute_id: str, user: dict[str, str] = Depends(_rs_user), db: Session = Depends(get_db_session)) -> dict:
    case = _case_for_facility(db, dispute_id, user["facility_code"])
    findings = db.scalars(select(ClarificationFinding).where(ClarificationFinding.dispute_case_id == case.id)).all()
    response = _current_response(db, case)
    docs = db.scalars(select(HospitalResponseDocument).where(HospitalResponseDocument.response_id == response.id)).all() if response else []
    _log(db, user, "opened_clarification", case)
    if case.received_at is None:
        case.received_at = datetime.utcnow()
        db.add(DisputeEvent(dispute_case_id=case.id, actor_id=user["user_id"], action="received_by_rs",
                            from_status="sent", to_status="sent", notes="Permintaan klarifikasi dibuka melalui portal RS."))
    db.commit()
    activities = db.scalars(select(HospitalActivity).where(HospitalActivity.dispute_case_id == case.id).order_by(HospitalActivity.created_at.asc())).all()
    return {
        **_case_summary(db, case),
        "letter_body": case.letter_body,
        "followup_notes": case.review_notes if response and response.version_number > 1 else None,
        "claim_summary": {"doctor_notes": case.claim.doctor_notes, "billing_codes": case.claim.admin_billing_code,
                          "length_of_stay": case.claim.length_of_stay},
        "findings": [{"type": row.finding_type, "title": row.title, "description": row.description,
                      "regulation_reference": row.regulation_reference,
                      "requested_documents": json.loads(row.requested_documents_json or "[]")} for row in findings],
        "response": ({"id": response.id, "version": response.version_number, "status": response.status,
                      "explanation_type": response.explanation_type, "notes": response.notes,
                      "documents": [{"id": doc.id, "filename": doc.original_filename} for doc in docs]} if response else None),
        "timeline": sorted(
            [{"action": e.action, "at": e.created_at, "notes": e.notes} for e in db.scalars(
                select(DisputeEvent).where(DisputeEvent.dispute_case_id == case.id).order_by(DisputeEvent.created_at.asc())
            ).all()] + [{"action": activity.action, "at": activity.created_at, "notes": activity.details} for activity in activities],
            key=lambda entry: entry["at"],
        ),
    }


@router.put("/clarifications/{dispute_id}/response")
def save_response_draft(dispute_id: str, request: ResponseDraftRequest,
                        user: dict[str, str] = Depends(_rs_user), db: Session = Depends(get_db_session)) -> dict:
    case = _case_for_facility(db, dispute_id, user["facility_code"])
    if case.status != "sent":
        raise HTTPException(status_code=409, detail="Klarifikasi sudah selesai di aplikasi")
    response = _current_response(db, case)
    if response and response.status == "submitted":
        raise HTTPException(status_code=409, detail="Respons yang sudah dikirim terkunci")
    if response is None:
        response = HospitalResponse(dispute_case_id=case.id, version_number=1, submitted_by=user["user_id"])
        db.add(response)
    response.explanation_type = request.explanation_type
    response.notes = request.notes.strip()
    response.status = "draft"
    response.submitted_by = user["user_id"]
    _log(db, user, "saved_response_draft", case, response.version_number)
    db.commit()
    return {"response_id": response.id, "version": response.version_number, "status": response.status}


@router.post("/clarifications/{dispute_id}/documents")
async def upload_response_document(dispute_id: str, file: UploadFile = File(...),
                                   user: dict[str, str] = Depends(_rs_user), db: Session = Depends(get_db_session)) -> dict:
    case = _case_for_facility(db, dispute_id, user["facility_code"])
    if case.status != "sent":
        raise HTTPException(status_code=409, detail="Klarifikasi sudah selesai di aplikasi")
    response = _current_response(db, case)
    if response is None:
        response = HospitalResponse(dispute_case_id=case.id, version_number=1, submitted_by=user["user_id"], explanation_type="administratif", status="draft")
        db.add(response)
        db.flush()
    if response.status == "submitted":
        raise HTTPException(status_code=409, detail="Respons yang sudah dikirim terkunci")
    payload = await file.read(MAX_FILE_BYTES + 1)
    if len(payload) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Ukuran file maksimal 10 MB")
    filename = Path(file.filename or "dokumen").name
    if payload.startswith(b"%PDF-"):
        media_type, suffix = "application/pdf", ".pdf"
    elif payload.startswith(b"\xff\xd8\xff"):
        media_type, suffix = "image/jpeg", ".jpg"
    else:
        raise HTTPException(status_code=415, detail="Format yang didukung hanya PDF dan JPG/JPEG")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored = secrets.token_hex(24) + suffix
    (UPLOAD_DIR / stored).write_bytes(payload)
    document = HospitalResponseDocument(response_id=response.id, original_filename=filename,
                                        stored_filename=stored, media_type=media_type, size_bytes=len(payload))
    db.add(document)
    _log(db, user, "uploaded_document", case, response.version_number, filename)
    db.commit()
    return {"id": document.id, "filename": filename, "size_bytes": len(payload)}


@router.post("/clarifications/{dispute_id}/submit")
def submit_response(dispute_id: str, user: dict[str, str] = Depends(_rs_user), db: Session = Depends(get_db_session)) -> dict:
    case = _case_for_facility(db, dispute_id, user["facility_code"])
    if case.status != "sent":
        raise HTTPException(status_code=409, detail="Klarifikasi sudah selesai di aplikasi")
    response = _current_response(db, case)
    if response is None or (not response.notes.strip() and not db.scalar(select(func.count(HospitalResponseDocument.id)).where(HospitalResponseDocument.response_id == response.id))):
        raise HTTPException(status_code=422, detail="Isi catatan atau unggah dokumen sebelum mengirim respons")
    if response.status == "submitted":
        raise HTTPException(status_code=409, detail="Respons sudah pernah dikirim")
    response.status = "submitted"
    response.submitted_at = datetime.utcnow()
    _log(db, user, "submitted_correction" if response.version_number > 1 else "submitted_response", case, response.version_number)
    db.add(DisputeEvent(dispute_case_id=case.id, actor_id=user["user_id"], action="rs_responded",
                        from_status="sent", to_status="sent", notes="Respons rumah sakit diterima."))
    db.commit()
    return {"status": "responded", "submitted_at": response.submitted_at, "version": response.version_number}


@router.get("/documents/{document_id}")
def download_response_document(document_id: int, user: dict[str, str] = Depends(_rs_user),
                               db: Session = Depends(get_db_session)) -> FileResponse:
    document = db.get(HospitalResponseDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    response = db.get(HospitalResponse, document.response_id)
    case = db.get(DisputeCase, response.dispute_case_id) if response else None
    if case is None:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    _case_for_facility(db, case.dispute_id, user["facility_code"])
    path = UPLOAD_DIR / document.stored_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Berkas dokumen tidak tersedia")
    _log(db, user, "downloaded_document", case, response.version_number, document.original_filename)
    db.commit()
    return FileResponse(path, media_type=document.media_type, filename=document.original_filename)

