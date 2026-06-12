import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

PASSWORD_ITERATIONS = 200_000
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7


def now():
    return datetime.now(timezone.utc).isoformat()


def make_salt():
    return secrets.token_hex(16)


def hash_password(password, salt):
    raw_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PASSWORD_ITERATIONS,
    )
    return base64.b64encode(raw_hash).decode("ascii")


def check_password(password, password_hash, salt):
    new_hash = hash_password(password, salt)
    return hmac.compare_digest(new_hash, password_hash)


def make_session_token():
    return secrets.token_urlsafe(32)


def session_expires_at():
    return (datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)).isoformat()