from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User, UserSettings
from ..schemas import LoginIn, RegisterIn, UserOut
from ..security import COOKIE_NAME, create_token, get_current_user, hash_password, limiter, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(resp: Response, token: str) -> None:
    s = get_settings()
    resp.set_cookie(COOKIE_NAME, token, httponly=True, secure=s.cookie_secure, samesite="lax",
                    max_age=s.jwt_expire_hours * 3600, path="/")


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit(lambda: get_settings().rate_limit_auth)
def register(request: Request, body: RegisterIn, response: Response, db: Session = Depends(get_db)):
    if not get_settings().allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registrasi ditutup oleh admin.")
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email sudah terdaftar.")
    user = User(email=email, display_name=body.display_name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    db.add(UserSettings(user_id=user.id))
    db.commit()
    _set_cookie(response, create_token(user.id))
    return user


@router.post("/login", response_model=UserOut)
@limiter.limit(lambda: get_settings().rate_limit_auth)
def login(request: Request, body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email atau password salah.")
    _set_cookie(response, create_token(user.id))
    return user


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
