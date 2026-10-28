from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.domain.schemas import RegulatoryRuleSchema
from app.infrastructure.repositories import RuleRepository
from app.interfaces.dependencies import get_db_session
from app.security.rbac import UserRole, require_roles


router = APIRouter(
    prefix="/api/v1/rules",
    tags=["Regulatory Knowledge Base"],
    dependencies=[Depends(require_roles(UserRole.ADMIN_BPJS))],
)


@router.get("/", response_model=list[RegulatoryRuleSchema])
def list_rules(db: Session = Depends(get_db_session)) -> list[RegulatoryRuleSchema]:
    return [
        RegulatoryRuleSchema.model_validate(rule)
        for rule in RuleRepository.get_all(db)
    ]


@router.get("/{rule_code}", response_model=RegulatoryRuleSchema)
def get_rule(
    rule_code: str, db: Session = Depends(get_db_session)
) -> RegulatoryRuleSchema:
    rule = RuleRepository.get_by_code(db, rule_code)
    if rule is None:
        raise HTTPException(status_code=404, detail="Regulatory rule not found")
    return RegulatoryRuleSchema.model_validate(rule)
