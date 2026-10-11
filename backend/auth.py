"""Small prototype authentication helpers. Use HTTPS and persistent sessions for production."""
import hashlib
import hmac
import secrets
import time
from threading import Lock

from fastapi import Header, HTTPException
from db import Guard, SessionLocal

# Opaque bearer tokens live in memory; server restart logs guards out. Never persist plaintext passwords.
_SESSIONS = {}
_LOCK = Lock()
SESSION_TTL_SECONDS = 8 * 60 * 60


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, salt_hex, digest_hex = encoded.split("$", 2)
        if algo != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with _LOCK:
        _SESSIONS[token] = (username, time.time() + SESSION_TTL_SECONDS)
    return token


def destroy_session(token: str):
    with _LOCK:
        _SESSIONS.pop(token, None)


def get_guard(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Guard login required")
    token = authorization[7:].strip()
    with _LOCK:
        item = _SESSIONS.get(token)
        if item and item[1] <= time.time():
            _SESSIONS.pop(token, None)
            item = None
    if not item:
        raise HTTPException(status_code=401, detail="Session expired; log in again")
    username = item[0]
    with SessionLocal() as db:
        guard = db.query(Guard).filter_by(username=username, active=1).first()
        if not guard:
            destroy_session(token)
            raise HTTPException(status_code=401, detail="Guard account is inactive")
        return {"id": guard.id, "username": guard.username}
