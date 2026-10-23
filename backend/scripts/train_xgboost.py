import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
import joblib
from sqlalchemy import select


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.infrastructure.database import SessionLocal
from app.infrastructure.orm_models import Claim
from app.ml.xgboost_scorer import FEATURE_NAMES, XGBoostRiskScorer


MODEL_PATH = BACKEND_DIR / "ml_models" / "xgboost_risk.pkl"


def _parse_codes(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return [value] if value else []
    if not isinstance(parsed, list):
        return []
    return [str(code) for code in parsed]


def load_training_data() -> tuple[np.ndarray, np.ndarray]:
    statement = select(
        Claim.length_of_stay,
        Claim.total_charge,
        Claim.approved_tariff,
        Claim.admin_billing_code,
        Claim.is_fraud,
    ).order_by(Claim.id.asc())
    with SessionLocal() as db:
        rows = db.execute(statement).all()

    if not rows:
        raise RuntimeError("No claims were found in the jkn_fraud.db database.")

    feature_rows = [
        XGBoostRiskScorer.build_features(
            length_of_stay,
            total_charge,
            approved_tariff,
            _parse_codes(admin_billing_code),
        )[0]
        for length_of_stay, total_charge, approved_tariff, admin_billing_code, _ in rows
    ]
    features = np.vstack(feature_rows)
    labels = np.asarray([int(row.is_fraud) for row in rows], dtype=np.int64)
    return features, labels


def main() -> None:
    features, labels = load_training_data()
    if len(np.unique(labels)) < 2:
        raise RuntimeError("Training requires both safe and fraud claim labels.")

    x_train, x_test, y_train, y_test = train_test_split(
        features,
        labels,
        test_size=0.2,
        stratify=labels,
        random_state=42,
    )
    model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)

    predictions = model.predict(x_test)
    fraud_probabilities = model.predict_proba(x_test)[:, 1]
    precision = precision_score(y_test, predictions, zero_division=0)
    recall = recall_score(y_test, predictions, zero_division=0)
    f1 = f1_score(y_test, predictions, zero_division=0)
    roc_auc = roc_auc_score(y_test, fraud_probabilities)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)

    print(f"Training rows: {len(x_train):,}")
    print(f"Test rows: {len(x_test):,}")
    print(f"Features ({len(FEATURE_NAMES)}): {', '.join(FEATURE_NAMES)}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1-score:  {f1:.4f}")
    print(f"ROC-AUC:   {roc_auc:.4f}")
    print("Classification report:")
    print(classification_report(y_test, predictions, zero_division=0))
    print(f"Model saved to: {MODEL_PATH}")


if __name__ == "__main__":
    main()