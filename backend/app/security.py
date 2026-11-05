import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Project, User

COOKIE_NAME = "nbs_session"
CSRF_HEADER = "x-nbs-request"  # browsers cannot add custom headers to cross-site form posts

_ph = PasswordHasher()


def _client_ip(request: Request) -> str:
    # Behind our reverse proxy (Caddy) the proxy appends the real client IP last;
    # taking the last entry means a client-supplied header cannot spoof it.
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[-1].strip() if fwd else get_remote_address(request)


limiter = Limiter(key_func=_client_ip)


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_token(user_id: uuid.UUID) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(hours=s.jwt_expire_hours)
    return jwt.encode({"sub": str(user_id), "exp": exp}, s.jwt_secret, algorithm="HS256")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    return user


def get_owned_project(project_id: uuid.UUID, user: User, db: Session) -> Project:
    """Ownership check. Returns 404 (not 403) so other users' IDs are not disclosed."""
    p = db.get(Project, project_id)
    if not p or p.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return p
