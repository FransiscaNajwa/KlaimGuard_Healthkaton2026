import hashlib
import hmac
import os
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from json import dumps, loads

from app.infrastructure.orm_models import HospitalAccount


AUTH_COOKIE_NAME = "klaimguard_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
AUTH_SECRET = os.getenv(
    "KLAIMGUARD_AUTH_SECRET", "development-only-change-this-secret"
).encode()
ADMIN_BPJS_USERNAME = os.getenv("ADMIN_BPJS_USERNAME", "admin.bpjs")
ADMIN_BPJS_PASSWORD = os.getenv("ADMIN_BPJS_PASSWORD", "admin123!")
RS_DEMO_USERNAME = os.getenv("RS_DEMO_USERNAME", "petugas.rs")
RS_DEMO_PASSWORD = os.getenv("RS_DEMO_PASSWORD", "rsdemo123!")
RS_DEMO_FACILITY_CODE = os.getenv("RS_DEMO_FACILITY_CODE", "RS-DEMO-001")
COOKIE_SECURE = os.getenv("KLAIMGUARD_COOKIE_SECURE", "false").lower() == "true"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$", maxsplit=3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def authenticate_admin(username: str, password: str, db=None) -> dict[str, str] | None:
    if hmac.compare_digest(username, ADMIN_BPJS_USERNAME) and hmac.compare_digest(password, ADMIN_BPJS_PASSWORD):
        return {"user_id": ADMIN_BPJS_USERNAME, "role": "admin_bpjs"}
    if db is not None:
        hospital_account = db.query(HospitalAccount).filter_by(username=username).first()
        if (
            hospital_account
            and hospital_account.is_active
            and verify_password(password, hospital_account.password_hash)
        ):
            return {
                "user_id": hospital_account.username,
                "role": "petugas_klaim_rs",
                "facility_code": hospital_account.facility.facility_code,
            }
    if hmac.compare_digest(username, RS_DEMO_USERNAME) and hmac.compare_digest(password, RS_DEMO_PASSWORD):
        return {"user_id": RS_DEMO_USERNAME, "role": "petugas_klaim_rs", "facility_code": RS_DEMO_FACILITY_CODE}
    return None


def create_session(user_id: str, role: str, facility_code: str | None = None) -> str:
    session_data = {"user_id": user_id, "role": role, "expires_at": int(time.time()) + SESSION_TTL_SECONDS}
    if facility_code:
        session_data["facility_code"] = facility_code
    payload = dumps(
        session_data,
        separators=(",", ":"),
    ).encode()
    encoded_payload = urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(AUTH_SECRET, encoded_payload.encode(), hashlib.sha256).digest()
    encoded_signature = urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{encoded_payload}.{encoded_signature}"


def read_session(token: str) -> dict[str, str] | None:
    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        expected_signature = hmac.new(
            AUTH_SECRET, encoded_payload.encode(), hashlib.sha256
        ).digest()
        signature = urlsafe_b64decode(encoded_signature + "===")
        if not hmac.compare_digest(signature, expected_signature):
            return None
        payload = loads(urlsafe_b64decode(encoded_payload + "==="))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None

    if not isinstance(payload, dict) or payload.get("expires_at", 0) < int(time.time()):
        return None
    if not isinstance(payload.get("user_id"), str) or not isinstance(
        payload.get("role"), str
    ):
        return None
    result = {"user_id": payload["user_id"], "role": payload["role"]}
    if isinstance(payload.get("facility_code"), str):
        result["facility_code"] = payload["facility_code"]
    return result


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
