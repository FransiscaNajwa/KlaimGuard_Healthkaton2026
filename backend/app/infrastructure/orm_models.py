from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base


class RegulatoryRule(Base):
    __tablename__ = "regulatory_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(20))
    legal_source: Mapped[str] = mapped_column(String(255))
    regulation_ref: Mapped[str] = mapped_column(String(150))
    primary_code: Mapped[str] = mapped_column(String(20), index=True)
    conflicting_code: Mapped[str] = mapped_column(String(20), index=True)
    violation_type: Mapped[str] = mapped_column(String(50))
    clinical_narrative: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    sep_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    doctor_notes: Mapped[str] = mapped_column(Text)
    admin_billing_code: Mapped[str] = mapped_column(Text)
    length_of_stay: Mapped[int] = mapped_column(Integer)
    total_charge: Mapped[float] = mapped_column(Float)
    approved_tariff: Mapped[float] = mapped_column(Float)
    potential_saving: Mapped[float] = mapped_column(Float)
    is_fraud: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    fraud_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    regulatory_rule_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("regulatory_rules.id"), nullable=True
    )
    audit_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    rule: Mapped[Optional[RegulatoryRule]] = relationship("RegulatoryRule")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String(50), index=True)
    verifier_id: Mapped[str] = mapped_column(String(50))
    is_fraud: Mapped[bool] = mapped_column(Boolean)
    decision: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class DisputeCase(Base):
    __tablename__ = "dispute_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dispute_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    letter_body: Mapped[str] = mapped_column(Text)
    legal_source: Mapped[str] = mapped_column(Text)
    regulation_ref: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    citations_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by: Mapped[str] = mapped_column(String(50))
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recipient: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    submission_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    claim: Mapped["Claim"] = relationship("Claim")


class DisputeEvent(Base):
    __tablename__ = "dispute_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dispute_case_id: Mapped[int] = mapped_column(ForeignKey("dispute_cases.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
