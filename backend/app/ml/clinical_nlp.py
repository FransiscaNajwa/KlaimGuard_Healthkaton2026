import re
from typing import Any


CLINICAL_ONTOLOGY = {
    "A01.0": [
        "demam",
        "tifoid",
        "typhoid",
        "widal",
        "lidah kotor",
        "kloramfenikol",
        "ceftriaxone",
    ],
    "A09": ["diare", "bab cair", "mencret", "dehidrasi", "oralit", "zink"],
    "E11.5": [
        "gangrene",
        "luka diabetik",
        "ulkus",
        "nekrotik",
        "debridement",
        "pus",
    ],
    "R02": [
        "gangrene",
        "luka diabetik",
        "ulkus",
        "nekrotik",
        "debridement",
        "pus",
    ],
    "R57.0": [
        "syok",
        "tensi turun",
        "td < 90",
        "inotropik",
        "dobutamin",
        "dopamin",
        "akral dingin",
    ],
    "13.41": [
        "fakoemulsifikasi",
        "phaco",
        "katarak",
        "lensa intraokular",
        "iol",
        "visus",
    ],
    "60.29": [
        "turp",
        "prostat",
        "bph",
        "reseksi",
        "retensi urin",
        "kateter 3-way",
    ],
}

NEGATION_TOKENS = {
    "bukan",
    "belum",
    "denies",
    "disangkal",
    "tidak",
    "tanpa",
}


def _normalize_code(code: str) -> str:
    return re.sub(r"[.\s]+", "", code).upper()


def _tokenize(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9<>]+", " ", text.lower())
    return cleaned.split()


def _keyword_positions(tokens: list[str], keyword: str) -> list[int]:
    keyword_tokens = _tokenize(keyword)
    if not keyword_tokens:
        return []
    positions = []
    final_start = len(tokens) - len(keyword_tokens) + 1
    for start in range(max(final_start, 0)):
        if tokens[start : start + len(keyword_tokens)] == keyword_tokens:
            positions.append(start)
    return positions


def _is_negated(tokens: list[str], start: int) -> bool:
    context = tokens[max(0, start - 5) : start]
    if any(token in NEGATION_TOKENS for token in context):
        return True
    return any(
        context[index : index + 2] == ["tidak", "ada"]
        for index in range(max(len(context) - 1, 0))
    )


class ClinicalNLPParser:
    def __init__(self):
        self.ontology = CLINICAL_ONTOLOGY

    def verify_clinical_consistency(
        self, doctor_notes: str, billing_codes: list[str]
    ) -> dict[str, Any]:
        tokens = _tokenize(doctor_notes or "")
        tracked_codes = []
        supported_codes = []
        missing_evidence_notes = []
        detected_evidence: dict[str, list[str]] = {}
        ontology_by_normalized_code = {
            _normalize_code(code): (code, keywords)
            for code, keywords in self.ontology.items()
        }

        for billed_code in billing_codes:
            ontology_entry = ontology_by_normalized_code.get(
                _normalize_code(billed_code)
            )
            if ontology_entry is None:
                continue
            canonical_code, keywords = ontology_entry
            tracked_codes.append(billed_code)
            matched_keywords = [
                keyword
                for keyword in keywords
                if any(
                    not _is_negated(tokens, position)
                    for position in _keyword_positions(tokens, keyword)
                )
            ]
            if matched_keywords:
                supported_codes.append(billed_code)
                detected_evidence[canonical_code] = matched_keywords
            else:
                missing_evidence_notes.append(
                    f"{billed_code} tidak didukung bukti klinis yang sesuai dalam resume medis."
                )

        consistency_score = (
            len(supported_codes) / len(tracked_codes) if tracked_codes else 1.0
        )
        return {
            "consistency_score": float(consistency_score),
            "supported_codes": supported_codes,
            "missing_evidence_notes": missing_evidence_notes,
            "detected_evidence": detected_evidence,
        }