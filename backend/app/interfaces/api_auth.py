from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.security.auth import (
    AUTH_COOKIE_NAME,
    COOKIE_SECURE,
    SESSION_TTL_SECONDS,
    authenticate_admin,
    create_session,
)
from app.security.rbac import get_current_user_role


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/login")
def login(request: LoginRequest, response: Response) -> dict[str, str]:
    user = authenticate_admin(request.username.strip(), request.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Username atau password salah")

    response.set_cookie(
        AUTH_COOKIE_NAME,
        create_session(user["user_id"], user["role"]),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return {"user_id": user["user_id"], "role": user["role"]}


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")


@router.get("/me")
def current_user(
    user: dict[str, str] = Depends(get_current_user_role),
) -> dict[str, str]:
    return user
