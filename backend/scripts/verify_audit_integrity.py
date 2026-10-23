import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select

from app.infrastructure.database import SessionLocal
from app.infrastructure.security_models import AuditLogEntry
from app.security.audit_logger import (
    GENESIS_HASH,
    CryptographicAuditLogger,
    format_timestamp,
)


RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"


def verify_audit_chain() -> int:
    with SessionLocal() as db:
        logger = CryptographicAuditLogger(db)
        statement = select(AuditLogEntry).order_by(AuditLogEntry.id.asc())
        entries = list(db.scalars(statement).all())

        expected_previous_hash = GENESIS_HASH
        for entry in entries:
            expected_current_hash = logger.compute_record_hash(
                entry.previous_hash,
                format_timestamp(entry.timestamp),
                entry.verifier_id,
                entry.claim_id,
                entry.action_type,
                entry.details_json,
            )
            if (
                entry.previous_hash != expected_previous_hash
                or entry.current_hash != expected_current_hash
            ):
                print(
                    f"{RED}[CRITICAL INTEGRITY BREACH] Audit record ID "
                    f"{entry.id} has been tampered!{RESET}"
                )
                return 1
            expected_previous_hash = entry.current_hash

    print(
        f"{GREEN}[INTEGRITY VERIFIED] All {len(entries)} audit records are "
        f"mathematically secure and valid.{RESET}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(verify_audit_chain())