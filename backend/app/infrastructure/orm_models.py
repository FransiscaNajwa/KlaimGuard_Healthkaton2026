from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    facility_id: Mapped[Optional[int]] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    rule: Mapped[Optional[RegulatoryRule]] = relationship("RegulatoryRule")
    facility: Mapped[Optional["HealthFacility"]] = relationship("HealthFacility")


class HealthFacility(Base):
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    facility_code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(Text, default="")


class HospitalAccount(Base):
    __tablename__ = "hospital_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    facility: Mapped["HealthFacility"] = relationship("HealthFacility")


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
    template_code: Mapped[str] = mapped_column(String(30), default="formal")
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
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
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


class DisputeComment(Base):
    __tablename__ = "dispute_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dispute_case_id: Mapped[int] = mapped_column(ForeignKey("dispute_cases.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(50))
    actor_role: Mapped[str] = mapped_column(String(30))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class DisputeVersion(Base):
    __tablename__ = "dispute_versions"
    __table_args__ = (UniqueConstraint("dispute_case_id", "version_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dispute_case_id: Mapped[int] = mapped_column(ForeignKey("dispute_cases.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    letter_body: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(50))
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class ClarificationFinding(Base):
    __tablename__ = "clarification_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dispute_case_id: Mapped[int] = mapped_column(ForeignKey("dispute_cases.id"), index=True)
    finding_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    regulation_reference: Mapped[str] = mapped_column(Text, default="")
    requested_documents_json: Mapped[str] = mapped_column(Text, default="[]")


class HospitalResponse(Base):
    __tablename__ = "hospital_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dispute_case_id: Mapped[int] = mapped_column(ForeignKey("dispute_cases.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    explanation_type: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    submitted_by: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class HospitalResponseDocument(Base):
    __tablename__ = "hospital_response_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    response_id: Mapped[int] = mapped_column(ForeignKey("hospital_responses.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(80), unique=True)
    media_type: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class HospitalActivity(Base):
    __tablename__ = "hospital_activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), index=True)
    facility_code: Mapped[str] = mapped_column(String(30), index=True)
    dispute_case_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dispute_cases.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40))
    response_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
