"""Add the synthetic RS portal demo records without resetting existing data."""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.infrastructure.database import Base, SessionLocal, engine
from scripts.additive_migration import migrate_additive_schema
from app.infrastructure import security_models  # noqa: F401
from app.infrastructure.orm_models import (
    Claim, ClarificationFinding, DisputeCase, DisputeEvent, DisputeVersion, HealthFacility,
    HospitalResponse, HospitalResponseDocument,
)
from app.security.auth import RS_DEMO_FACILITY_CODE


def _sample_pdf() -> bytes:
    stream = b"BT /F1 16 Tf 50 760 Td (DOKUMEN SINTETIS - HANYA UNTUK DEMO KLAIMGUARD) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, content in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + content + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(output)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_additive_schema(engine)
    db = SessionLocal()
    try:
        facility = db.query(HealthFacility).filter_by(facility_code=RS_DEMO_FACILITY_CODE).first()
        if facility is None:
            facility = HealthFacility(facility_code=RS_DEMO_FACILITY_CODE, name="RS Demo KlaimGuard", address="Alamat sintetis untuk demonstrasi")
            db.add(facility)
            db.flush()

        for row in db.query(Claim).all():
            row.facility_id = facility.id
        claim = db.query(Claim).filter_by(claim_id="CLM-03576").first()
        if claim is None:
            claim = db.query(Claim).filter(Claim.regulatory_rule_id.is_not(None)).first()
        if claim is None:
            raise RuntimeError("Data klaim demo belum tersedia. Jalankan inisialisasi dataset terlebih dahulu.")

        case = db.query(DisputeCase).filter_by(dispute_id="DSP-RS-DEMO-001").first()
        if case is None:
            now = datetime.utcnow()
            rule = claim.rule
            case = DisputeCase(
                dispute_id="DSP-RS-DEMO-001", claim_id=claim.claim_id, status="sent",
                template_code="formal",
                letter_body=(f"Permintaan klarifikasi klaim {claim.claim_id}.\n\n"
                             f"Temuan: {rule.violation_type if rule else 'Perlu klarifikasi'}\n"
                             f"Dasar: {rule.legal_source if rule else 'Regulasi terkait'}; {rule.regulation_ref if rule else ''}\n\n"
                             "Mohon sampaikan penjelasan dan dokumen pendukung melalui portal ini."),
                legal_source=rule.legal_source if rule else "Regulasi terkait",
                regulation_ref=rule.regulation_ref if rule else "",
                recommendation=rule.recommendation if rule else "Mohon klarifikasi",
                citations_json="[]", created_by="admin.bpjs", reviewer_id="admin.bpjs",
                review_notes="Disetujui untuk demonstrasi alur klarifikasi.", recipient=facility.name,
                submission_reference="DEMO-KLARIFIKASI-001", submitted_at=now - timedelta(minutes=10),
                sent_at=now, deadline_at=now + timedelta(days=3), created_at=now - timedelta(minutes=15), updated_at=now,
            )
            db.add(case)
            db.flush()
            db.add(DisputeVersion(dispute_case_id=case.id, version_number=1, letter_body=case.letter_body, actor_id="admin.bpjs", note="Draf demo"))
            db.add(DisputeEvent(dispute_case_id=case.id, actor_id="admin.bpjs", action="sent_to_hospital", from_status="approved", to_status="sent", notes="Permintaan klarifikasi contoh untuk demo."))
            category = "koding" if claim.rule and claim.rule.category in {"UPCODING", "UNBUNDLING"} else "administratif"
            db.add_all([
                ClarificationFinding(dispute_case_id=case.id, finding_type=category, title="Klarifikasi koding", description="Mohon jelaskan kesesuaian kode diagnosis dan tindakan dengan resume medis.", regulation_reference=f"{case.legal_source}; {case.regulation_ref}", requested_documents_json=json.dumps(["Resume medis", "Lembar asesmen dokter"], ensure_ascii=False)),
                ClarificationFinding(dispute_case_id=case.id, finding_type="administratif", title="Kelengkapan dokumen administrasi", description="Mohon lengkapi dokumen administratif pendukung pengajuan klaim.", regulation_reference="Checklist administrasi klaim (contoh demo)", requested_documents_json=json.dumps(["Surat eligibilitas peserta", "Bukti pelayanan"], ensure_ascii=False)),
            ])
            response = HospitalResponse(dispute_case_id=case.id, version_number=1, explanation_type="koding",
                                        notes="Draf contoh respons sintetis untuk memperlihatkan penyimpanan dokumen pendukung.",
                                        status="draft", submitted_by=os.getenv("RS_DEMO_USERNAME", "petugas.rs"))
            db.add(response)
            db.flush()
            from app.interfaces.api_rs_portal import UPLOAD_DIR
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            sample_name = "demo-resume-sintetis.pdf"
            sample_path = UPLOAD_DIR / sample_name
            if not sample_path.exists():
                sample_path.write_bytes(_sample_pdf())
            db.add(HospitalResponseDocument(response_id=response.id, original_filename="Resume medis sintetis (contoh).pdf",
                                            stored_filename=sample_name, media_type="application/pdf",
                                            size_bytes=sample_path.stat().st_size))
        db.commit()
        print(f"Seed portal RS siap untuk faskes {facility.facility_code} dan klarifikasi {case.dispute_id}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
