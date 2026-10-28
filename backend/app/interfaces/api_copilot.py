from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.domain.schemas import (
    CopilotQueryRequest,
    CopilotQueryResponse,
    DraftDisputeRequest,
    DraftDisputeResponse,
)
from app.infrastructure.repositories import ClaimRepository
from app.interfaces.dependencies import get_db_session
from app.rag.pdf_loader import BACKEND_DIR
from app.rag.rag_service import RegulatoryCopilotService
from app.rag.regulation_metadata import registered_regulations
from app.rag.vector_store import LocalVectorStore
from app.security.rbac import UserRole, require_roles


router = APIRouter(
    prefix="/api/v1/copilot",
    tags=["Regulatory RAG Copilot"],
    dependencies=[Depends(require_roles(UserRole.ADMIN_BPJS))],
)
REGULATIONS_DIR = BACKEND_DIR / "regulation_docs"
VECTOR_INDEX_DIR = BACKEND_DIR / "ml_models" / "vector_index"

_vector_store: LocalVectorStore | None = None


def get_copilot_service() -> RegulatoryCopilotService:
    global _vector_store
    if _vector_store is None:
        _vector_store = LocalVectorStore(str(VECTOR_INDEX_DIR))
    return RegulatoryCopilotService(_vector_store)


@router.post("/query", response_model=CopilotQueryResponse)
def query_regulations(
    request: CopilotQueryRequest,
    db: Session = Depends(get_db_session),
) -> CopilotQueryResponse:
    service = get_copilot_service()
    if not service.vector_store.index_ready:
        raise HTTPException(
            status_code=503,
            detail=(
                "The regulatory index is empty. Ingest the regulation PDFs "
                "before querying the Copilot."
            ),
        )
    query = request.query
    if request.claim_id:
        claim = ClaimRepository.get_by_id(db, request.claim_id)
        if claim is None:
            raise HTTPException(status_code=404, detail="Claim not found")
        if claim.rule:
            query = (
                f"{query} {claim.rule.primary_code} {claim.rule.conflicting_code} "
                f"{claim.rule.violation_type} {claim.rule.clinical_narrative}"
            )
    result = service.generate_answer(query)
    return CopilotQueryResponse(
        query=request.query,
        answer=result["answer_markdown"],
        citations=result["citations"],
        dispute_template=result["drafted_dispute_letter"],
    )


@router.post("/draft-dispute", response_model=DraftDisputeResponse)
def draft_dispute(
    request: DraftDisputeRequest,
    db: Session = Depends(get_db_session),
) -> DraftDisputeResponse:
    claim = ClaimRepository.get_by_id(db, request.claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.rule is None:
        raise HTTPException(
            status_code=409,
            detail="This claim has no linked regulatory rule to support a dispute draft.",
        )

    rule = claim.rule
    draft = get_copilot_service().draft_dispute_letter(
        claim_id=claim.claim_id,
        sep_number=claim.sep_number,
        primary_code=rule.primary_code,
        conflicting_code=rule.conflicting_code,
        violation_type=rule.violation_type,
        legal_source=rule.legal_source,
        regulation_ref=rule.regulation_ref,
        clinical_narrative=rule.clinical_narrative,
        recommendation=rule.recommendation,
    )
    active_references = sorted(
        {
            f"{item['source_document']}, halaman {item['page_number']}"
            for item in draft["citations"]
        }
    )
    return DraftDisputeResponse(
        claim_id=claim.claim_id,
        dispute_template=draft["formal_letter"],
        legal_source="Dokumen regulasi aktif" if active_references else "Belum ditemukan",
        regulation_ref="; ".join(active_references) if active_references else "Perlu verifikasi manual",
        citations=draft["citations"],
    )


@router.get("/regulations-status")
def regulations_status() -> dict[str, object]:
    available_documents = sorted(path.name for path in REGULATIONS_DIR.glob("*.pdf"))
    store = get_copilot_service().vector_store
    indexed_documents = store.indexed_documents
    return {
        "index_ready": store.index_ready,
        "vector_index_file_present": store.index_path.is_file(),
        "indexed_documents": len(indexed_documents),
        "indexed_document_names": indexed_documents,
        "indexed_chunks": store.chunk_count,
        "available_documents": available_documents,
        "available_document_count": len(available_documents),
        "regulation_status": registered_regulations(),
    }
