import hashlib
import hmac
import os
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from json import dumps, loads


AUTH_COOKIE_NAME = "klaimguard_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
AUTH_SECRET = os.getenv(
    "KLAIMGUARD_AUTH_SECRET", "development-only-change-this-secret"
).encode()
ADMIN_BPJS_USERNAME = os.getenv("ADMIN_BPJS_USERNAME", "admin.bpjs")
ADMIN_BPJS_PASSWORD = os.getenv("ADMIN_BPJS_PASSWORD", "admin123!")
ADMIN_AUDIT_USERNAME = os.getenv("ADMIN_AUDIT_USERNAME", "admin.audit")
ADMIN_AUDIT_PASSWORD = os.getenv("ADMIN_AUDIT_PASSWORD", "audit123!")
COOKIE_SECURE = os.getenv("KLAIMGUARD_COOKIE_SECURE", "false").lower() == "true"


def authenticate_admin(username: str, password: str) -> dict[str, str] | None:
    accounts = (
        (ADMIN_BPJS_USERNAME, ADMIN_BPJS_PASSWORD, "admin_bpjs"),
        (ADMIN_AUDIT_USERNAME, ADMIN_AUDIT_PASSWORD, "admin_audit"),
    )
    for account_username, account_password, role in accounts:
        username_matches = hmac.compare_digest(username, account_username)
        password_matches = hmac.compare_digest(password, account_password)
        if username_matches and password_matches:
            return {"user_id": account_username, "role": role}
    return None


def create_session(user_id: str, role: str) -> str:
    payload = dumps(
        {"user_id": user_id, "role": role, "expires_at": int(time.time()) + SESSION_TTL_SECONDS},
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
    return {"user_id": payload["user_id"], "role": payload["role"]}


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
