import threading
import time
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.user import User

_JWKS_TTL_SECONDS = 3600
_jwks_lock = threading.Lock()
_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0


@dataclass(frozen=True)
class Principal:
    """Identity extracted from a verified Clerk JWT, before any DB lookup."""

    auth_user_id: str
    email: str | None = None
    name: str | None = None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _fetch_jwks() -> dict:
    if not settings.clerk_jwks_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured (CLERK_JWKS_URL is empty).",
        )
    response = httpx.get(settings.clerk_jwks_url, timeout=5.0)
    response.raise_for_status()
    return response.json()


def _get_jwks(force_refresh: bool = False) -> dict:
    global _jwks_cache, _jwks_fetched_at
    with _jwks_lock:
        stale = time.monotonic() - _jwks_fetched_at > _JWKS_TTL_SECONDS
        if _jwks_cache is None or stale or force_refresh:
            _jwks_cache = _fetch_jwks()
            _jwks_fetched_at = time.monotonic()
        return _jwks_cache


def _find_key(kid: str | None) -> dict:
    jwks = _get_jwks()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    # Key rotation: refresh once before giving up.
    jwks = _get_jwks(force_refresh=True)
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    raise _unauthorized("Unknown signing key.")


def verify_token(token: str) -> Principal:
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise _unauthorized("Malformed token.")

    key = _find_key(header.get("kid"))
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except JWTError:
        raise _unauthorized("Invalid or expired token.")

    auth_user_id = claims.get("sub")
    if not auth_user_id:
        raise _unauthorized("Token has no subject.")

    name = claims.get("name")
    if not name:
        parts = [claims.get("first_name"), claims.get("last_name")]
        name = " ".join(p for p in parts if p) or None

    return Principal(auth_user_id=auth_user_id, email=claims.get("email"), name=name)


_bearer = HTTPBearer(auto_error=False)


def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if credentials is None:
        raise _unauthorized("Missing bearer token.")
    return verify_token(credentials.credentials)


def get_current_user(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> User:
    user = db.scalar(select(User).where(User.auth_user_id == principal.auth_user_id))
    if user is None:
        raise _unauthorized("User not synced. Call POST /users/sync first.")
    return user
