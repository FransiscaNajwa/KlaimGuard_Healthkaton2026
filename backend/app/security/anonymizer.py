import hashlib
import re


class DataAnonymizer:
    def __init__(self, salt: str = "JKN-HEALTHKATHON-2026-PEPPER-KEY"):
        self.salt = salt

    def pseudonymize_identifier(self, identifier: str) -> str:
        normalized_identifier = identifier.strip()
        if not normalized_identifier:
            raise ValueError("Identifier must not be empty.")
        digest = hashlib.sha256(
            f"{self.salt}:{normalized_identifier}".encode("utf-8")
        ).hexdigest()
        return f"ID-HASH-{digest[:20].upper()}"

    def mask_patient_name(self, full_name: str) -> str:
        masked_parts = []
        for part in full_name.split():
            if len(part) <= 2:
                masked_parts.append(part)
            else:
                masked_parts.append(f"{part[0]}{'*' * (len(part) - 2)}{part[-1]}")
        return " ".join(masked_parts)

    def mask_sep_number(self, sep_no: str) -> str:
        normalized = sep_no.strip()
        match = re.fullmatch(r"(\d{4})R(\d{3})(\d{4})V(\d+)", normalized)
        if match:
            hospital_code, hospital_branch, date_code, participant_code = (
                match.groups()
            )
            return (
                f"{'*' * len(hospital_code)}R{'*' * len(hospital_branch)}"
                f"{date_code}V{'*' * len(participant_code)}"
            )
        return re.sub(r"[A-Za-z0-9]", "*", normalized)

    def sanitize_doctor_notes(self, notes: str) -> str:
        sanitized = re.sub(
            r"(?<!\d)(?:\d[\s-]?){15}\d(?!\d)",
            "[NIK REDACTED]",
            notes,
        )
        sanitized = re.sub(
            r"(?<!\w)(?:\+?62|0)[\s().-]*\d(?:[\s().-]*\d){7,12}(?!\w)",
            "[PHONE REDACTED]",
            sanitized,
        )
        sanitized = re.sub(
            r"\b(?:alamat|domisili|address)\s*[:=]\s*[^,;\n]+",
            "[ADDRESS REDACTED]",
            sanitized,
            flags=re.IGNORECASE,
        )
        return sanitized