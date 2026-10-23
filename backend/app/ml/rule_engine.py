import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.orm_models import RegulatoryRule


def normalize_code(code: str) -> str:
    return re.sub(r"[.\s]+", "", str(code)).upper()


class RegulatoryRuleEngine:
    def __init__(self, db_session: Session):
        statement = select(RegulatoryRule).order_by(RegulatoryRule.rule_code.asc())
        self.rules = list(db_session.scalars(statement).all())

    def evaluate(self, billing_codes: list[str]) -> Optional[dict[str, Any]]:
        billed_codes = {normalize_code(code) for code in billing_codes}
        for rule in self.rules:
            required_codes = {
                normalize_code(rule.primary_code),
                normalize_code(rule.conflicting_code),
            }
            if required_codes.issubset(billed_codes):
                return {
                    "rule_code": rule.rule_code,
                    "regulatory_rule_id": rule.id,
                    "category": rule.category,
                    "legal_source": rule.legal_source,
                    "regulation_ref": rule.regulation_ref,
                    "primary_code": rule.primary_code,
                    "conflicting_code": rule.conflicting_code,
                    "violation_type": rule.violation_type,
                    "clinical_narrative": rule.clinical_narrative,
                    "recommendation": rule.recommendation,
                }
        return None