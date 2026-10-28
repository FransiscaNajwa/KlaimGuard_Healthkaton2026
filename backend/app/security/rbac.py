import re
from enum import Enum
from typing import Callable

from fastapi import Cookie, Depends, HTTPException

from app.security.auth import AUTH_COOKIE_NAME, read_session


class UserRole(str, Enum):
    VERIFIKATOR = "verifikator"
    SUPERVISOR_SPI = "supervisor_spi"
    ADMIN_BPJS = "admin_bpjs"
    ADMIN_SISTEM = "admin_sistem"
    PETUGAS_KLAIM_RS = "petugas_klaim_rs"


ROLE_LEVELS = {
    UserRole.VERIFIKATOR: 0,
    UserRole.SUPERVISOR_SPI: 1,
    UserRole.ADMIN_BPJS: 2,
    UserRole.ADMIN_SISTEM: 2,
    UserRole.PETUGAS_KLAIM_RS: 0,
}


def get_current_user_role(
    session_token: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
) -> dict[str, str]:
    if not session_token:
        raise HTTPException(status_code=401, detail="Login diperlukan")
    session = read_session(session_token)
    if session is None:
        raise HTTPException(status_code=401, detail="Sesi login tidak valid atau kedaluwarsa")
    user_id = session["user_id"].strip()
    if not user_id or len(user_id) > 50 or not re.fullmatch(r"[A-Za-z0-9._-]+", user_id):
        raise HTTPException(status_code=401, detail="Invalid verifier identity")
    try:
        role_value = session["role"].strip().lower()
        if role_value == "admin_audit":  # Older sessions map to the unified verifier.
            role_value = UserRole.ADMIN_BPJS.value
        role = UserRole(role_value)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Unknown user role") from exc
    result = {"user_id": user_id, "role": role.value}
    facility_code = session.get("facility_code")
    if facility_code:
        result["facility_code"] = facility_code
    return result


def require_role(required_role: UserRole) -> Callable[..., dict[str, str]]:
    def role_dependency(
        current_user: dict[str, str] = Depends(get_current_user_role),
    ) -> dict[str, str]:
        current_role = UserRole(current_user["role"])
        if ROLE_LEVELS[current_role] < ROLE_LEVELS[required_role]:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{required_role.value}' or higher is required",
            )
        return current_user

    return role_dependency


def require_roles(*allowed_roles: UserRole) -> Callable[..., dict[str, str]]:
    allowed = {role.value for role in allowed_roles}

    def role_dependency(
        current_user: dict[str, str] = Depends(get_current_user_role),
    ) -> dict[str, str]:
        if current_user["role"] not in allowed:
            raise HTTPException(status_code=403, detail="Role tidak memiliki akses")
        return current_user

    return role_dependency
