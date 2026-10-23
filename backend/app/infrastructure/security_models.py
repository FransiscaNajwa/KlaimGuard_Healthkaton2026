from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class AuditLogEntry(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    verifier_id: Mapped[str] = mapped_column(String(50), index=True)
    claim_id: Mapped[str] = mapped_column(String(50), index=True)
    action_type: Mapped[str] = mapped_column(String(50))
    details_json: Mapped[str] = mapped_column(Text)
    previous_hash: Mapped[str] = mapped_column(String(64))
    current_hash: Mapped[str] = mapped_column(String(64), index=True)