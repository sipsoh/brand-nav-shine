"""JWT verification tests using a locally generated RSA key pair.

These exercise the real verification path in app.auth (JWKS lookup, RS256
signature check, expiry, claim extraction) without contacting Clerk.
"""

import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jose import jwk
from jose import jwt as jose_jwt

import app.auth as auth_module
from app.auth import verify_token

KID = "test-key-1"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_private_pem = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_public_pem = _private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

_public_jwk = jwk.construct(_public_pem, algorithm="RS256").to_dict()
_public_jwk["kid"] = KID
JWKS = {"keys": [_public_jwk]}


@pytest.fixture(autouse=True)
def _stub_jwks(monkeypatch):
    monkeypatch.setattr(auth_module, "_fetch_jwks", lambda: JWKS)
    monkeypatch.setattr(auth_module, "_jwks_cache", None)
    monkeypatch.setattr(auth_module, "_jwks_fetched_at", 0.0)


def make_token(claims: dict, kid: str = KID) -> str:
    payload = {"exp": int(time.time()) + 300, **claims}
    return jose_jwt.encode(payload, _private_pem, algorithm="RS256", headers={"kid": kid})


def test_valid_token_yields_principal():
    token = make_token({"sub": "user_123", "email": "jane@example.com", "name": "Jane Doe"})
    principal = verify_token(token)
    assert principal.auth_user_id == "user_123"
    assert principal.email == "jane@example.com"
    assert principal.name == "Jane Doe"


def test_name_falls_back_to_first_last():
    token = make_token({"sub": "user_456", "first_name": "Sam", "last_name": "Ortiz"})
    assert verify_token(token).name == "Sam Ortiz"


def test_expired_token_is_rejected():
    token = jose_jwt.encode(
        {"sub": "user_123", "exp": int(time.time()) - 60},
        _private_pem,
        algorithm="RS256",
        headers={"kid": KID},
    )
    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401


def test_token_without_subject_is_rejected():
    with pytest.raises(HTTPException) as exc:
        verify_token(make_token({"email": "nosub@example.com"}))
    assert exc.value.status_code == 401


def test_unknown_signing_key_is_rejected():
    with pytest.raises(HTTPException) as exc:
        verify_token(make_token({"sub": "user_123"}, kid="rogue-key"))
    assert exc.value.status_code == 401


def test_tampered_token_is_rejected():
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    forged = jose_jwt.encode(
        {"sub": "user_123", "exp": int(time.time()) + 300},
        other_pem,
        algorithm="RS256",
        headers={"kid": KID},
    )
    with pytest.raises(HTTPException) as exc:
        verify_token(forged)
    assert exc.value.status_code == 401
