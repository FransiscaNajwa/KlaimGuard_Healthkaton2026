from pathlib import Path
from typing import Sequence

import joblib
import numpy as np


FEATURE_NAMES = (
    "length_of_stay",
    "total_charge",
    "potential_saving",
    "charge_ratio",
    "code_count",
    "daily_charge_intensity",
    "has_surgical_code",
)


class XGBoostRiskScorer:
    def __init__(self, model_path: str = "backend/ml_models/xgboost_risk.pkl"):
        requested_path = Path(model_path)
        if requested_path.is_absolute():
            resolved_path = requested_path
        else:
            working_path = Path.cwd() / requested_path
            backend_path = (
                Path(__file__).resolve().parents[2]
                / "ml_models"
                / requested_path.name
            )
            resolved_path = working_path if working_path.is_file() else backend_path

        self.model_path = resolved_path
        self.model = None
        if self.model_path.is_file():
            try:
                self.model = joblib.load(self.model_path)
            except (OSError, ValueError, EOFError, AttributeError):
                self.model = None

    @staticmethod
    def build_features(
        length_of_stay: int,
        total_charge: float,
        approved_tariff: float,
        billing_codes: Sequence[str],
    ) -> np.ndarray:
        clean_codes = [str(code).strip() for code in billing_codes if str(code).strip()]
        safe_length = max(int(length_of_stay), 1)
        safe_tariff = max(float(approved_tariff) + 1.0, 1.0)
        charge = float(total_charge)
        potential_saving = max(charge - float(approved_tariff), 0.0)
        charge_ratio = charge / safe_tariff
        daily_charge_intensity = charge / safe_length
        has_surgical_code = any(
            len(code) >= 2 and code[:2].isdigit() for code in clean_codes
        )
        return np.asarray(
            [
                safe_length,
                charge,
                potential_saving,
                charge_ratio,
                len(clean_codes),
                daily_charge_intensity,
                float(has_surgical_code),
            ],
            dtype=np.float64,
        ).reshape(1, len(FEATURE_NAMES))

    def extract_features(
        self,
        length_of_stay: int,
        total_charge: float,
        approved_tariff: float,
        billing_codes: list[str],
    ) -> np.ndarray:
        return self.build_features(
            length_of_stay, total_charge, approved_tariff, billing_codes
        )

    def predict_risk(self, features: np.ndarray) -> float:
        if self.model is not None:
            probabilities = self.model.predict_proba(features)
            classes = list(self.model.classes_)
            fraud_index = classes.index(1) if 1 in classes else classes.index(True)
            return float(np.clip(probabilities[0][fraud_index], 0.0, 1.0))

        length_of_stay, total_charge, _, charge_ratio, code_count, daily_charge, has_surgery = (
            features[0]
        )
        ratio_risk = min(max(float(charge_ratio) - 1.0, 0.0) / 4.0, 1.0)
        daily_risk = min(max(float(daily_charge), 0.0) / 10_000_000.0, 1.0)
        code_risk = min(max(float(code_count) - 1.0, 0.0) / 3.0, 1.0)
        surgery_risk = float(has_surgery)
        _ = length_of_stay, total_charge
        score = (
            0.45 * ratio_risk
            + 0.25 * daily_risk
            + 0.15 * code_risk
            + 0.15 * surgery_risk
        )
        return float(np.clip(score, 0.0, 1.0))