import os
from datetime import datetime, timezone
from typing import Any, Iterable


VALID_DECISIONS = {"CONFIRMED_FRAUD", "APPROVED_SAFE", "DISPUTE_TO_RS"}
RESTRICTED_STATUSES = {"DISPUTE", "DISPUTE_TO_RS", "REJECT", "PENALTY", "SANCTION"}


class HumanInTheLoopGuard:
    def __init__(
        self,
        current_verifier_id: str | None = None,
        certified_verifier_ids: Iterable[str] | None = None,
    ):
        configured_ids = (
            certified_verifier_ids
            if certified_verifier_ids is not None
            else os.getenv("KLAIMGUARD_CERTIFIED_VERIFIER_IDS", "").split(",")
        )
        self.current_verifier_id = current_verifier_id
        self.certified_verifier_ids = {
            verifier_id.strip()
            for verifier_id in configured_ids
            if verifier_id and verifier_id.strip()
        }

    def validate_override(
        self,
        ai_verdict: dict[str, Any],
        verifier_decision: str,
        reason_notes: str,
    ) -> dict[str, Any]:
        decision = verifier_decision.strip().upper()
        if decision not in VALID_DECISIONS:
            raise ValueError(f"Unsupported verifier decision: {verifier_decision}")

        ai_is_fraud = bool(ai_verdict.get("is_fraud", False))
        if decision == "DISPUTE_TO_RS":
            is_override = True
        else:
            human_is_fraud = decision == "CONFIRMED_FRAUD"
            is_override = human_is_fraud != ai_is_fraud

        justification = reason_notes.strip()
        if is_override and len(justification) < 10:
            raise ValueError(
                "An AI verdict override requires at least 10 characters of justification."
            )

        return {
            "approved_override": is_override,
            "verifier_decision": decision,
            "reason_notes": justification,
            "ai_high_confidence": float(ai_verdict.get("risk_score", 0.0)) >= 0.9,
            "legal_rule_flag": ai_verdict.get("rule_result") is not None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def enforce_safety_boundary(self, proposed_claim_status: str) -> None:
        status = proposed_claim_status.strip().upper()
        if status not in RESTRICTED_STATUSES:
            return
        verifier_id = self.current_verifier_id
        if verifier_id not in self.certified_verifier_ids:
            raise PermissionError(
                "A certified human verifier must authorize dispute, rejection, or penalty transitions."
            )