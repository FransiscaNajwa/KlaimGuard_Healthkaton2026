import json
import random
import sys
from datetime import datetime
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.infrastructure.database import Base, SessionLocal, engine
from app.infrastructure.orm_models import Claim, Feedback, RegulatoryRule


RULES_PATH = BACKEND_DIR / "app" / "rules" / "seed_rules.json"
SAFE_CLAIM_COUNT = 3_575
UPCODING_CLAIM_COUNT = 1_100
UNBUNDLING_CLAIM_COUNT = 825
RANDOM_SEED = 20260930

SAFE_CASES = [
    ("Demam dengue terkonfirmasi; pemantauan trombosit dan terapi cairan sesuai kondisi klinis.", ["A91"]),
    ("Pneumonia bakteri terkonfirmasi melalui pemeriksaan klinis dan radiologi.", ["J18.0"]),
    ("Persalinan normal pervaginam tanpa komplikasi; observasi ibu dan bayi baru lahir.", ["O80"]),
    ("Pasien menjalani kemoterapi terencana sesuai protokol onkologi.", ["Z51.1"]),
    ("Hemodialisa reguler sesuai jadwal; tidak ada prosedur tambahan yang ditagihkan.", ["N18.6", "39.95"]),
    ("Kontrol rutin hipertensi primer dengan tekanan darah stabil dan terapi dilanjutkan.", ["I10"]),
]

UPC0DING_NOTES = {
    "RULE-UPC-001": "Pasien demam dengan diare, pemeriksaan mengarah pada tifoid; terapi diberikan sesuai kondisi klinis.",
    "RULE-UPC-002": "Pasien diabetes tipe 2 kontrol dengan luka kaki; tidak ditemukan gangren pada pemeriksaan.",
    "RULE-UPC-003": "Pasien dengan penyakit jantung koroner stabil; tekanan darah dan perfusi perifer dalam batas stabil.",
    "RULE-UPC-004": "Pasien hipertensi dengan peningkatan kreatinin akut; evaluasi dan terapi gagal ginjal akut dilakukan.",
    "RULE-UPC-005": "Pasien gastritis akut dengan keluhan nyeri ulu hati; tidak ada bukti perdarahan saluran cerna.",
    "RULE-UPC-006": "Batuk pilek ringan selama tiga hari tanpa ronki atau tanda infeksi saluran napas bawah.",
    "RULE-UPC-007": "Mata merah dan iritasi ringan; pemeriksaan tidak menunjukkan katarak dan tidak dilakukan operasi.",
    "RULE-UPC-008": "Anemia ringan ditemukan pada pemeriksaan darah; tidak ada biopsi sumsum tulang.",
}

UNBUNDLING_NOTES = {
    "RULE-UNB-001": "Dilakukan reseksi prostat transuretra (TURP) dalam satu sesi operasi.",
    "RULE-UNB-002": "Dilakukan sectio caesarea dengan anestesi spinal dalam satu tindakan pembedahan.",
    "RULE-UNB-003": "Dilakukan satu sesi hemodialisa rutin sesuai jadwal terapi pasien.",
    "RULE-UNB-004": "Dilakukan kolesistektomi laparoskopik dalam satu sesi operasi.",
    "RULE-UNB-005": "Dilakukan apendektomi melalui akses bedah yang diperlukan untuk mencapai apendiks.",
    "RULE-UNB-006": "Dilakukan reduksi tertutup fraktur dengan imobilisasi pada sesi tindakan yang sama.",
    "RULE-UNB-007": "Dilakukan penilaian ulang sediaan jaringan lama dari fasilitas kesehatan perujuk.",
}


def build_claim_data(
    rules: list[dict], rule_ids: dict[str, int], rng: random.Random
) -> list[dict]:
    claims: list[dict] = []
    upcoding_rules = [rule for rule in rules if rule["category"] == "UPCODING"]
    unbundling_rules = [rule for rule in rules if rule["category"] == "UNBUNDLING"]

    for index in range(1, SAFE_CLAIM_COUNT + 1):
        doctor_notes, billing_codes = SAFE_CASES[(index - 1) % len(SAFE_CASES)]
        tariff = float(rng.randint(800_000, 9_500_000))
        claims.append(
            {
                "claim_id": f"CLM-{index:05d}",
                "sep_number": f"0001R0010926V{index:06d}",
                "doctor_notes": doctor_notes,
                "admin_billing_code": json.dumps(billing_codes),
                "length_of_stay": rng.randint(1, 8),
                "total_charge": tariff,
                "approved_tariff": tariff,
                "potential_saving": 0.0,
                "is_fraud": False,
                "fraud_type": None,
                "regulatory_rule_id": None,
                "audit_notes": None,
                "created_at": datetime.utcnow(),
            }
        )

    for offset in range(UPCODING_CLAIM_COUNT):
        index = SAFE_CLAIM_COUNT + offset + 1
        rule = upcoding_rules[offset % len(upcoding_rules)]
        approved_tariff = float(rng.randint(2_000_000, 6_000_000))
        total_charge = float(rng.randint(7_500_000, 22_000_000))
        claims.append(
            {
                "claim_id": f"CLM-{index:05d}",
                "sep_number": f"0001R0010926V{index:06d}",
                "doctor_notes": UPC0DING_NOTES[rule["rule_code"]],
                "admin_billing_code": json.dumps(
                    [rule["primary_code"], rule["conflicting_code"]]
                ),
                "length_of_stay": rng.randint(1, 10),
                "total_charge": total_charge,
                "approved_tariff": approved_tariff,
                "potential_saving": total_charge - approved_tariff,
                "is_fraud": True,
                "fraud_type": "upcoding",
                "regulatory_rule_id": rule_ids[rule["rule_code"]],
                "audit_notes": rule["recommendation"],
                "created_at": datetime.utcnow(),
            }
        )

    for offset in range(UNBUNDLING_CLAIM_COUNT):
        index = SAFE_CLAIM_COUNT + UPCODING_CLAIM_COUNT + offset + 1
        rule = unbundling_rules[offset % len(unbundling_rules)]
        approved_tariff = float(rng.randint(2_000_000, 6_000_000))
        total_charge = float(rng.randint(7_500_000, 22_000_000))
        claims.append(
            {
                "claim_id": f"CLM-{index:05d}",
                "sep_number": f"0001R0010926V{index:06d}",
                "doctor_notes": UNBUNDLING_NOTES[rule["rule_code"]],
                "admin_billing_code": json.dumps(
                    [rule["primary_code"], rule["conflicting_code"]]
                ),
                "length_of_stay": rng.randint(1, 14),
                "total_charge": total_charge,
                "approved_tariff": approved_tariff,
                "potential_saving": total_charge - approved_tariff,
                "is_fraud": True,
                "fraud_type": "unbundling",
                "regulatory_rule_id": rule_ids[rule["rule_code"]],
                "audit_notes": rule["recommendation"],
                "created_at": datetime.utcnow(),
            }
        )

    return claims


def build_feedback_data(claims: list[dict], rng: random.Random) -> list[dict]:
    feedback_data = []
    for claim in rng.sample(claims, 100):
        disputed = claim["is_fraud"] and rng.random() < 0.15
        if disputed:
            decision = "DISPUTE_TO_RS"
            is_fraud = False
            notes = "Verifikator meminta klarifikasi dan dokumen pendukung dari rumah sakit."
        elif claim["is_fraud"]:
            decision = "CONFIRMED_FRAUD"
            is_fraud = True
            notes = "Ketidaksesuaian koding terkonfirmasi setelah telaah resume medis."
        else:
            decision = "APPROVED_SAFE"
            is_fraud = False
            notes = "Koding dan tarif sesuai dengan dokumentasi klinis."

        feedback_data.append(
            {
                "claim_id": claim["claim_id"],
                "verifier_id": f"VERIF-MEDIS-{rng.randint(1, 12):02d}",
                "is_fraud": is_fraud,
                "decision": decision,
                "notes": notes,
                "created_at": datetime.utcnow(),
            }
        )
    return feedback_data


def main() -> None:
    rng = random.Random(RANDOM_SEED)
    with RULES_PATH.open("r", encoding="utf-8") as rules_file:
        rules = json.load(rules_file)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        db.add_all([RegulatoryRule(**rule) for rule in rules])
        db.flush()
        rule_ids = {
            rule.rule_code: rule.id
            for rule in db.query(RegulatoryRule).all()
        }

        claim_data = build_claim_data(rules, rule_ids, rng)
        feedback_data = build_feedback_data(claim_data, rng)
        db.bulk_insert_mappings(Claim, claim_data)
        db.bulk_insert_mappings(Feedback, feedback_data)
        db.commit()

    total_savings = sum(claim["potential_saving"] for claim in claim_data)
    print(f"Regulatory Rules terdaftar: {len(rules)}")
    print(
        "Klaim dibuat: Total 5.500, Safe 3.575, "
        "Upcoding 1.100, Unbundling 825"
    )
    print(f"Total Potensi Penyelamatan Dana JKN: Rp {total_savings:,.0f}")


if __name__ == "__main__":
    main()