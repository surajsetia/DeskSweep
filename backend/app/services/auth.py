import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError


bearer_scheme = HTTPBearer(auto_error=False)
PASSWORD_ITERATIONS = 310_000
TOKEN_LIFETIME = timedelta(days=7)


def _jwt_secret():
    secret = os.getenv("JWT_SECRET", "").strip()
    if len(secret) < 32:
        raise HTTPException(
            status_code=503,
            detail="JWT_SECRET must be configured with at least 32 characters.",
        )
    return secret


def hash_password(password: str):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "$".join(
        (
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, password_hash: str):
    try:
        iterations, salt, expected = password_hash.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.urlsafe_b64decode(salt.encode("ascii")),
            int(iterations),
        )
        return hmac.compare_digest(
            base64.urlsafe_b64encode(digest).decode("ascii"), expected
        )
    except (ValueError, TypeError):
        return False


def create_access_token(email: str):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": email,
            "iat": now,
            "exp": now + TOKEN_LIFETIME,
        },
        _jwt_secret(),
        algorithm="HS256",
    )


def get_current_email(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Sign in to continue.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            _jwt_secret(),
            algorithms=["HS256"],
        )
        email = payload.get("sub")
        if not isinstance(email, str) or not email:
            raise PyJWTError("Token subject is missing.")
        return email
    except PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Your session expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
