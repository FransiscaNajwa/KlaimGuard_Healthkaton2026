import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.security_models import AuditLogEntry


GENESIS_HASH = "0" * 64
ALLOWED_ACTIONS = {
    "FLAG_CONFIRMED",
    "FLAG_OVERRIDDEN",
    "DISPUTE_SENT",
    "REVIEW_CONFIRMED",
}


def format_timestamp(timestamp: datetime | str) -> str:
    if isinstance(timestamp, datetime):
        return timestamp.isoformat(timespec="microseconds")
    return datetime.fromisoformat(timestamp).isoformat(timespec="microseconds")


def compute_audit_hash(
    prev_hash: str,
    timestamp_str: str,
    verifier_id: str,
    claim_id: str,
    action: str,
    details: str,
) -> str:
    canonical_payload = json.dumps(
        [prev_hash, timestamp_str, verifier_id, claim_id, action, details],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()


class CryptographicAuditLogger:
    def __init__(self, db_session: Session):
        self.db_session = db_session
        AuditLogEntry.__table__.create(
            bind=db_session.get_bind(), checkfirst=True
        )

    def compute_record_hash(
        self,
        prev_hash: str,
        timestamp_str: str,
        verifier_id: str,
        claim_id: str,
        action: str,
        details: str,
    ) -> str:
        return compute_audit_hash(
            prev_hash, timestamp_str, verifier_id, claim_id, action, details
        )

    def log_verification_action(
        self,
        verifier_id: str,
        claim_id: str,
        action_type: str,
        details: dict[str, Any],
    ) -> AuditLogEntry:
        if action_type not in ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported audit action: {action_type}")

        previous_entry = self.db_session.scalars(
            select(AuditLogEntry).order_by(AuditLogEntry.id.desc()).limit(1)
        ).first()
        previous_hash = (
            previous_entry.current_hash if previous_entry else GENESIS_HASH
        )
        timestamp = datetime.utcnow()
        timestamp_str = format_timestamp(timestamp)
        details_json = json.dumps(
            details,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        current_hash = self.compute_record_hash(
            previous_hash,
            timestamp_str,
            verifier_id,
            claim_id,
            action_type,
            details_json,
        )
        entry = AuditLogEntry(
            timestamp=timestamp,
            verifier_id=verifier_id,
            claim_id=claim_id,
            action_type=action_type,
            details_json=details_json,
            previous_hash=previous_hash,
            current_hash=current_hash,
        )
        try:
            self.db_session.add(entry)
            self.db_session.flush()
            self.db_session.commit()
            self.db_session.refresh(entry)
        except Exception:
            self.db_session.rollback()
            raise
        return entry