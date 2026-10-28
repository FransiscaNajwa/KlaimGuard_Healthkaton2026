from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RegulatoryRuleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_code: str
    category: str
    legal_source: str
    regulation_ref: str
    primary_code: str
    conflicting_code: str
    violation_type: str
    clinical_narrative: str
    recommendation: str


class CodeAuditItem(BaseModel):
    code: str
    code_type: Literal["ICD-10-PRIMARY", "ICD-10-SECONDARY", "ICD-9-CM"]
    description: str
    status: Literal["VALID", "VIOLATION"]
    violation_type: Optional[str] = None
    rule_source: Optional[str] = None
    clinical_note: str


class ClaimListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: str
    sep_number: str
    doctor_notes: str
    admin_billing_code: str
    length_of_stay: int
    total_charge: float
    approved_tariff: float
    potential_saving: float
    is_fraud: bool
    fraud_type: Optional[str]
    created_at: datetime


class ClaimDetailResponse(ClaimListResponse):
    audit_notes: Optional[str]
    rule: Optional[RegulatoryRuleSchema]
    code_breakdown: list[CodeAuditItem] = Field(default_factory=list)
    risk_score: float = 0.0
    reason_narrative: str = ""


class ManualClaimAnalysisRequest(BaseModel):
    claim_id: str = Field(min_length=1, max_length=50)
    doctor_notes: str = Field(min_length=1, max_length=10000)
    admin_billing_code: list[str] = Field(min_length=1, max_length=30)
    length_of_stay: int = Field(ge=1, le=365)
    total_charge: float = Field(ge=0)


class ManualClaimAnalysisResponse(BaseModel):
    claim_id: str
    sep_number: str
    doctor_notes: str
    admin_billing_code: str
    length_of_stay: int
    total_charge: float
    approved_tariff: float
    potential_saving: float
    is_fraud: bool
    fraud_type: Optional[str]
    risk_score: float
    reason_narrative: str
    audit_notes: Optional[str] = None
    rule: Optional[RegulatoryRuleSchema] = None
    code_breakdown: list[CodeAuditItem] = Field(default_factory=list)


class ClaimFilterParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=500)
    search: Optional[str] = None
    status: Optional[Literal["safe", "fraud"]] = None
    fraud_type: Optional[Literal["upcoding", "unbundling"]] = None


class ClaimPaginationResponse(BaseModel):
    total_records: int
    current_page: int
    total_pages: int
    data: list[ClaimListResponse]


class FeedbackCreate(BaseModel):
    claim_id: str = Field(min_length=1, max_length=50)
    verifier_id: str = Field(min_length=1, max_length=50)
    decision: Literal["CONFIRMED_FRAUD", "APPROVED_SAFE", "DISPUTE_TO_RS"]
    notes: str = Field(min_length=1)


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: str
    verifier_id: str
    decision: str
    notes: str
    created_at: datetime


class StatsOverviewResponse(BaseModel):
    total_claims: int
    safe_claims: int
    fraud_claims: int
    upcoding_count: int
    unbundling_count: int
    total_potential_saving_idr: float
    audit_coverage_pct: float


class FinancialSummaryItem(BaseModel):
    total_claims: int
    total_charge: float
    total_approved: float
    total_saving: float
    safe_charge: float
    safe_approved: float
    upcoding_charge: float
    upcoding_approved: float
    upcoding_saving: float
    unbundling_charge: float
    unbundling_approved: float
    unbundling_saving: float


class LosBreakdownItem(BaseModel):
    length_of_stay: int
    count: int
    fraud_count: int
    fraud_rate_pct: float
    avg_charge: float
    avg_tariff: float
    total_saving: float


class CostBucketItem(BaseModel):
    bucket: str
    count: int
    fraud_count: int
    fraud_rate_pct: float
    total_charge: float
    total_saving: float


class TopAnomalyItem(BaseModel):
    admin_billing_code: str
    fraud_type: str
    count: int
    total_charge: float
    total_saving: float
    rule_code: str
    regulation_ref: str


class AnalyticsDashboardResponse(BaseModel):
    financial_summary: FinancialSummaryItem
    los_breakdown: list[LosBreakdownItem]
    cost_buckets: list[CostBucketItem]
    top_anomalies: list[TopAnomalyItem]
    high_impact_claims: list[ClaimListResponse]


class BatchAuditRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=5500)


class BatchAuditResponse(BaseModel):
    processed_count: int
    flagged_count: int
    execution_time_seconds: float
    total_saved_idr: float
    results: list[ClaimListResponse] = Field(default_factory=list)


class CopilotQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    claim_id: Optional[str] = None


class CitationItem(BaseModel):
    source_document: str
    page_number: int = Field(ge=1)
    excerpt: str


class CopilotQueryResponse(BaseModel):
    query: str
    answer: str
    citations: list[CitationItem]
    dispute_template: str


class DraftDisputeResponse(BaseModel):
    claim_id: str
    dispute_template: str
    legal_source: str
    regulation_ref: str
    citations: list[CitationItem]


class DraftDisputeRequest(BaseModel):
    claim_id: str = Field(min_length=1, max_length=50)


class DisputeCreateRequest(BaseModel):
    claim_id: str = Field(min_length=1, max_length=50)
    template_code: Literal["formal", "ringkas", "rinci"] = "formal"


class DisputeUpdateRequest(BaseModel):
    letter_body: str = Field(min_length=20, max_length=30000)


class DisputeReviewRequest(BaseModel):
    action: Literal["approve", "request_revision"]
    notes: str = Field(default="", max_length=3000)


class DisputeReevaluationRequest(BaseModel):
    action: Literal["accept", "request_additional"]
    notes: str = Field(default="", max_length=3000)


class DisputeSentRequest(BaseModel):
    recipient: str = Field(min_length=2, max_length=255)
    submission_reference: str = Field(min_length=2, max_length=100)


class DisputeEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    actor_id: str
    action: str
    from_status: Optional[str]
    to_status: str
    notes: str
    created_at: datetime


class DisputeCommentCreate(BaseModel):
    body: str = Field(min_length=3, max_length=4000)


class DisputeCommentResponse(BaseModel):
    actor_id: str
    actor_role: str
    body: str
    created_at: datetime


class DisputeVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_number: int
    letter_body: str
    actor_id: str
    note: str
    created_at: datetime


class DisputeSummaryResponse(BaseModel):
    total: int
    drafts: int
    in_review: int
    overdue_review: int
    needs_revision: int
    approved: int
    sent: int
    closed: int
    waiting_hospital_response: int = 0
    waiting_reassessment: int = 0
    late_hospital_response: int = 0
    oldest_pending_hours: Optional[int] = None


class DisputeResponse(BaseModel):
    dispute_id: str
    claim_id: str
    sep_number: str
    status: str
    template_code: str = "formal"
    letter_body: str
    legal_source: str
    regulation_ref: str
    recommendation: str
    citations: list[CitationItem]
    created_by: str
    reviewer_id: Optional[str]
    review_notes: Optional[str]
    recipient: Optional[str]
    submission_reference: Optional[str]
    submitted_at: Optional[datetime]
    sent_at: Optional[datetime]
    deadline_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    history: list[DisputeEventResponse] = Field(default_factory=list)
    comments: list[DisputeCommentResponse] = Field(default_factory=list)
    versions: list[DisputeVersionResponse] = Field(default_factory=list)
    current_version: int = 1
    is_overdue: bool = False
    review_age_hours: Optional[int] = None
    hospital_responses: list[dict] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)
