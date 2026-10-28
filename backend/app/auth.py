"""Authentication: password hashing (bcrypt), access tokens (JWT, HS256),
and the `get_current_user` dependency every protected endpoint uses."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User

# --- Passwords ---------------------------------------------------------------------


def hash_password(plain: str) -> str:
    # bcrypt salts every hash, so the same password never produces the same string.
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# --- Tokens ------------------------------------------------------------------------


def create_access_token(user_id: int) -> str:
    """Signed token proving "this is user <id>" until it expires.

    Only the id goes in: role and name are re-read from the DB on every request,
    so a role change takes effect immediately instead of when the token expires.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),  # JWT spec: "sub" is a string
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Return the user id, or None if the token is forged, malformed or expired."""
    settings = get_settings()
    try:
        # algorithms=[...] is a whitelist: rejects tokens claiming "alg": "none".
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


# --- FastAPI dependency ------------------------------------------------------------

# auto_error=False so a missing header goes through our own 401 below
# (with the consistent error body) instead of FastAPI's default 403.
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve `Authorization: Bearer <jwt>` to a User row, or fail with 401."""
    if credentials is None:
        raise _unauthorized("Not authenticated")
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise _unauthorized("Invalid or expired token")
    user = db.get(User, user_id)
    if user is None:  # token is valid but the account no longer exists
        raise _unauthorized("Invalid or expired token")
    return user
