from db.security import (
    SESSION_TTL_SECONDS,
    check_password,
    hash_password,
    make_salt,
    make_session_token,
    now,
    session_expires_at,
)


def test_password_hash_check():
    salt = make_salt()
    password_hash = hash_password("secret-password", salt)

    assert check_password("secret-password", password_hash, salt)
    assert not check_password("wrong-password", password_hash, salt)
    assert password_hash != "secret-password"


def test_session_token_is_random():
    first_token = make_session_token()
    second_token = make_session_token()

    assert first_token != second_token
    assert len(first_token) >= 32


def test_session_expiration_is_in_future():
    expires_at = session_expires_at()

    from datetime import datetime, timedelta, timezone

    now_dt = datetime.fromisoformat(now())
    expires_dt = datetime.fromisoformat(expires_at)

    assert expires_dt > now_dt
    assert expires_dt <= now_dt + timedelta(seconds=SESSION_TTL_SECONDS + 1)
