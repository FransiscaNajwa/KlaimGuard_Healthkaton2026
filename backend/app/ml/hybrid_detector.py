import json
from typing import Any

from sqlalchemy.orm import Session

from app.ml.clinical_nlp import ClinicalNLPParser
from app.ml.rule_engine import RegulatoryRuleEngine
from app.ml.xgboost_scorer import XGBoostRiskScorer


class HybridFraudDetector:
    def __init__(self, db_session: Session):
        self.rule_engine = RegulatoryRuleEngine(db_session)
        self.clinical_parser = ClinicalNLPParser()
        self.risk_scorer = XGBoostRiskScorer()

    @staticmethod
    def _billing_codes(value: Any) -> list[str]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = [value]
        if not isinstance(value, (list, tuple)):
            return []
        return [str(code).strip() for code in value if str(code).strip()]

    def analyze_claim(self, claim_data: dict[str, Any]) -> dict[str, Any]:
        billing_codes = self._billing_codes(claim_data.get("admin_billing_code", []))
        claim_id = str(claim_data.get("claim_id", ""))
        rule_result = self.rule_engine.evaluate(billing_codes)

        if rule_result is not None:
            audit_narrative = (
                f"Deterministic violation {rule_result['rule_code']} detected. "
                f"Legal basis: {rule_result['legal_source']}; "
                f"{rule_result['regulation_ref']}. "
                f"Clinical finding: {rule_result['clinical_narrative']} "
                f"Recommendation: {rule_result['recommendation']}"
            )
            return {
                "claim_id": claim_id,
                "is_fraud": True,
                "fraud_type": rule_result["category"].lower(),
                "risk_score": 0.98,
                "review_status": "FLAGGED",
                "audit_narrative": audit_narrative,
                "rule_result": rule_result,
                "clinical_result": None,
            }

        doctor_notes = str(claim_data.get("doctor_notes", ""))
        clinical_result = self.clinical_parser.verify_clinical_consistency(
            doctor_notes, billing_codes
        )
        total_charge = float(claim_data.get("total_charge", 0.0) or 0.0)
        approved_tariff = float(claim_data.get("approved_tariff", 0.0) or 0.0)
        charge_ratio = total_charge / max(approved_tariff, 1.0)
        has_high_tariff = total_charge >= 7_500_000 or charge_ratio >= 1.5

        if clinical_result["missing_evidence_notes"] and has_high_tariff:
            missing_evidence = " ".join(clinical_result["missing_evidence_notes"])
            return {
                "claim_id": claim_id,
                "is_fraud": True,
                "fraud_type": "upcoding",
                "risk_score": 0.85,
                "review_status": "FLAGGED",
                "audit_narrative": (
                    "Clinical documentation does not support the billed high-severity "
                    f"codes. {missing_evidence} Total charge: Rp {total_charge:,.0f}; "
                    f"approved tariff: Rp {approved_tariff:,.0f}."
                ),
                "rule_result": None,
                "clinical_result": clinical_result,
            }

        features = self.risk_scorer.extract_features(
            int(claim_data.get("length_of_stay", 0) or 0),
            total_charge,
            approved_tariff,
            billing_codes,
        )
        risk_score = self.risk_scorer.predict_risk(features)
        if risk_score > 0.70:
            review_status = "NEED_MANUAL_REVIEW"
            audit_narrative = (
                "Statistical anomaly score exceeds the manual-review threshold; "
                "verifier review is required before a fraud decision."
            )
        elif clinical_result["missing_evidence_notes"]:
            review_status = "CLEARED_WITH_CLINICAL_NOTE"
            audit_narrative = (
                "No deterministic violation or high-tariff clinical mismatch was "
                "found. Review the following evidence note: "
                + " ".join(clinical_result["missing_evidence_notes"])
            )
        else:
            review_status = "CLEARED"
            audit_narrative = (
                "Valid: Keselarasan penuh antara rekam medis dan kode tindakan."
            )

        return {
            "claim_id": claim_id,
            "is_fraud": False,
            "fraud_type": None,
            "risk_score": risk_score,
            "review_status": review_status,
            "audit_narrative": audit_narrative,
            "rule_result": None,
            "clinical_result": clinical_result,
        }