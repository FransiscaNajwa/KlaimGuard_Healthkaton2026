from typing import Optional

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.domain.schemas import ClaimFilterParams, FeedbackCreate
from app.infrastructure.orm_models import Claim, Feedback, RegulatoryRule


class ClaimRepository:
    @staticmethod
    def get_by_id(db: Session, claim_id: str) -> Optional[Claim]:
        statement = (
            select(Claim)
            .options(joinedload(Claim.rule))
            .where(Claim.claim_id == claim_id)
        )
        return db.scalars(statement).first()

    @staticmethod
    def get_paginated(
        db: Session, params: ClaimFilterParams
    ) -> tuple[int, list[Claim]]:
        filters = []
        if params.search:
            search_term = f"%{params.search.strip()}%"
            filters.append(
                or_(
                    Claim.claim_id.ilike(search_term),
                    Claim.sep_number.ilike(search_term),
                    Claim.doctor_notes.ilike(search_term),
                    Claim.admin_billing_code.ilike(search_term),
                )
            )
        if params.status == "safe":
            filters.append(Claim.is_fraud.is_(False))
        elif params.status == "fraud":
            filters.append(Claim.is_fraud.is_(True))
        if params.fraud_type:
            filters.append(Claim.fraud_type == params.fraud_type)

        count_statement = select(func.count(Claim.id)).where(*filters)
        total = db.scalar(count_statement) or 0
        statement = (
            select(Claim)
            .options(joinedload(Claim.rule))
            .where(*filters)
            .order_by(Claim.id.asc())
            .offset(params.skip)
            .limit(params.limit)
        )
        return total, list(db.scalars(statement).all())

    @staticmethod
    def get_batch_claims(db: Session, limit: int) -> list[Claim]:
        statement = (
            select(Claim)
            .options(joinedload(Claim.rule))
            .order_by(Claim.is_fraud.desc(), Claim.id.asc())
            .limit(limit)
        )
        return list(db.scalars(statement).all())

    @staticmethod
    def get_summary_stats(db: Session) -> dict[str, int | float]:
        reviewed_claims = (
            select(func.count(func.distinct(Feedback.claim_id)))
            .where(Feedback.claim_id.in_(select(Claim.claim_id)))
            .scalar_subquery()
        )
        statement = select(
            func.count(Claim.id).label("total_claims"),
            func.coalesce(
                func.sum(case((Claim.is_fraud.is_(False), 1), else_=0)), 0
            ).label("safe_claims"),
            func.coalesce(
                func.sum(case((Claim.is_fraud.is_(True), 1), else_=0)), 0
            ).label("fraud_claims"),
            func.coalesce(
                func.sum(case((Claim.fraud_type == "upcoding", 1), else_=0)), 0
            ).label("upcoding_count"),
            func.coalesce(
                func.sum(case((Claim.fraud_type == "unbundling", 1), else_=0)), 0
            ).label("unbundling_count"),
            func.coalesce(func.sum(Claim.potential_saving), 0.0).label(
                "total_potential_saving_idr"
            ),
            reviewed_claims.label("reviewed_claims"),
        )
        row = db.execute(statement).one()
        return {
            "total_claims": int(row.total_claims),
            "safe_claims": int(row.safe_claims),
            "fraud_claims": int(row.fraud_claims),
            "upcoding_count": int(row.upcoding_count),
            "unbundling_count": int(row.unbundling_count),
            "total_potential_saving_idr": float(row.total_potential_saving_idr),
            "reviewed_claims": int(row.reviewed_claims or 0),
        }

    @staticmethod
    def get_analytics_dashboard(db: Session) -> dict:
        statement_fin = select(
            func.count(Claim.id).label("total_claims"),
            func.coalesce(func.sum(Claim.total_charge), 0.0).label("total_charge"),
            func.coalesce(func.sum(Claim.approved_tariff), 0.0).label("total_approved"),
            func.coalesce(func.sum(Claim.potential_saving), 0.0).label("total_saving"),
            func.coalesce(func.sum(case((Claim.is_fraud.is_(False), Claim.total_charge), else_=0.0)), 0.0).label("safe_charge"),
            func.coalesce(func.sum(case((Claim.is_fraud.is_(False), Claim.approved_tariff), else_=0.0)), 0.0).label("safe_approved"),
            func.coalesce(func.sum(case((Claim.fraud_type == "upcoding", Claim.total_charge), else_=0.0)), 0.0).label("upcoding_charge"),
            func.coalesce(func.sum(case((Claim.fraud_type == "upcoding", Claim.approved_tariff), else_=0.0)), 0.0).label("upcoding_approved"),
            func.coalesce(func.sum(case((Claim.fraud_type == "upcoding", Claim.potential_saving), else_=0.0)), 0.0).label("upcoding_saving"),
            func.coalesce(func.sum(case((Claim.fraud_type == "unbundling", Claim.total_charge), else_=0.0)), 0.0).label("unbundling_charge"),
            func.coalesce(func.sum(case((Claim.fraud_type == "unbundling", Claim.approved_tariff), else_=0.0)), 0.0).label("unbundling_approved"),
            func.coalesce(func.sum(case((Claim.fraud_type == "unbundling", Claim.potential_saving), else_=0.0)), 0.0).label("unbundling_saving"),
        )
        fin_row = db.execute(statement_fin).one()
        financial_summary = {
            "total_claims": int(fin_row.total_claims),
            "total_charge": float(fin_row.total_charge),
            "total_approved": float(fin_row.total_approved),
            "total_saving": float(fin_row.total_saving),
            "safe_charge": float(fin_row.safe_charge),
            "safe_approved": float(fin_row.safe_approved),
            "upcoding_charge": float(fin_row.upcoding_charge),
            "upcoding_approved": float(fin_row.upcoding_approved),
            "upcoding_saving": float(fin_row.upcoding_saving),
            "unbundling_charge": float(fin_row.unbundling_charge),
            "unbundling_approved": float(fin_row.unbundling_approved),
            "unbundling_saving": float(fin_row.unbundling_saving),
        }

        statement_los = (
            select(
                Claim.length_of_stay,
                func.count(Claim.id).label("count"),
                func.coalesce(func.sum(case((Claim.is_fraud.is_(True), 1), else_=0)), 0).label("fraud_count"),
                func.coalesce(func.avg(Claim.total_charge), 0.0).label("avg_charge"),
                func.coalesce(func.avg(Claim.approved_tariff), 0.0).label("avg_tariff"),
                func.coalesce(func.sum(Claim.potential_saving), 0.0).label("total_saving"),
            )
            .group_by(Claim.length_of_stay)
            .order_by(Claim.length_of_stay.asc())
        )
        los_rows = db.execute(statement_los).all()
        los_breakdown = [
            {
                "length_of_stay": int(r.length_of_stay),
                "count": int(r.count),
                "fraud_count": int(r.fraud_count),
                "fraud_rate_pct": round((float(r.fraud_count) / float(r.count) * 100), 1) if r.count else 0.0,
                "avg_charge": round(float(r.avg_charge), 2),
                "avg_tariff": round(float(r.avg_tariff), 2),
                "total_saving": float(r.total_saving),
            }
            for r in los_rows
        ]

        bucket_case = case(
            (Claim.total_charge < 5000000, "< Rp 5 Jt"),
            (Claim.total_charge < 10000000, "Rp 5 - 10 Jt"),
            (Claim.total_charge < 15000000, "Rp 10 - 15 Jt"),
            else_="> Rp 15 Jt",
        ).label("bucket")
        statement_bucket = (
            select(
                bucket_case,
                func.count(Claim.id).label("count"),
                func.coalesce(func.sum(case((Claim.is_fraud.is_(True), 1), else_=0)), 0).label("fraud_count"),
                func.coalesce(func.sum(Claim.total_charge), 0.0).label("total_charge"),
                func.coalesce(func.sum(Claim.potential_saving), 0.0).label("total_saving"),
            )
            .group_by(bucket_case)
            .order_by(func.min(Claim.total_charge).asc())
        )
        bucket_rows = db.execute(statement_bucket).all()
        cost_buckets = [
            {
                "bucket": str(r.bucket),
                "count": int(r.count),
                "fraud_count": int(r.fraud_count),
                "fraud_rate_pct": round((float(r.fraud_count) / float(r.count) * 100), 1) if r.count else 0.0,
                "total_charge": float(r.total_charge),
                "total_saving": float(r.total_saving),
            }
            for r in bucket_rows
        ]

        statement_top_anomalies = (
            select(
                Claim.admin_billing_code,
                Claim.fraud_type,
                func.count(Claim.id).label("count"),
                func.coalesce(func.sum(Claim.total_charge), 0.0).label("total_charge"),
                func.coalesce(func.sum(Claim.potential_saving), 0.0).label("total_saving"),
                func.coalesce(RegulatoryRule.rule_code, "-").label("rule_code"),
                func.coalesce(RegulatoryRule.regulation_ref, "-").label("regulation_ref"),
            )
            .outerjoin(RegulatoryRule, Claim.regulatory_rule_id == RegulatoryRule.id)
            .where(Claim.is_fraud.is_(True))
            .group_by(Claim.admin_billing_code, Claim.fraud_type, RegulatoryRule.rule_code, RegulatoryRule.regulation_ref)
            .order_by(func.sum(Claim.potential_saving).desc())
            .limit(10)
        )
        anomaly_rows = db.execute(statement_top_anomalies).all()
        top_anomalies = [
            {
                "admin_billing_code": str(r.admin_billing_code),
                "fraud_type": str(r.fraud_type or "anomali"),
                "count": int(r.count),
                "total_charge": float(r.total_charge),
                "total_saving": float(r.total_saving),
                "rule_code": str(r.rule_code),
                "regulation_ref": str(r.regulation_ref),
            }
            for r in anomaly_rows
        ]

        statement_high_impact = (
            select(Claim)
            .where(Claim.is_fraud.is_(True))
            .order_by(Claim.potential_saving.desc())
            .limit(5)
        )
        high_impact_claims = list(db.scalars(statement_high_impact).all())

        return {
            "financial_summary": financial_summary,
            "los_breakdown": los_breakdown,
            "cost_buckets": cost_buckets,
            "top_anomalies": top_anomalies,
            "high_impact_claims": high_impact_claims,
        }


class RuleRepository:
    @staticmethod
    def get_all(db: Session) -> list[RegulatoryRule]:
        statement = select(RegulatoryRule).order_by(RegulatoryRule.rule_code.asc())
        return list(db.scalars(statement).all())

    @staticmethod
    def get_by_code(db: Session, rule_code: str) -> Optional[RegulatoryRule]:
        statement = select(RegulatoryRule).where(
            RegulatoryRule.rule_code == rule_code
        )
        return db.scalars(statement).first()


class FeedbackRepository:
    @staticmethod
    def create(db: Session, feedback_data: FeedbackCreate) -> Feedback:
        feedback = Feedback(
            claim_id=feedback_data.claim_id,
            verifier_id=feedback_data.verifier_id,
            is_fraud=feedback_data.decision == "CONFIRMED_FRAUD",
            decision=feedback_data.decision,
            notes=feedback_data.notes,
        )
        db.add(feedback)
        db.flush()
        return feedback

    @staticmethod
    def get_by_claim_id(db: Session, claim_id: str) -> list[Feedback]:
        statement = (
            select(Feedback)
            .where(Feedback.claim_id == claim_id)
            .order_by(Feedback.created_at.desc(), Feedback.id.desc())
        )
        return list(db.scalars(statement).all())