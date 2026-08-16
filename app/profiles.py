"""Profile persistence for SchemeGPT.

Low-traffic MVP capability: a profile is identified by an opaque, randomly
generated ``profile_id`` plus a one-time-issued random bearer token. Only the
SHA-256 hash of the token is stored; the raw token is returned exactly once
(on create) and is never logged or persisted. Token checks use a constant-time
hash comparison. Real account authentication (passwords, sessions, OAuth) is
intentionally out of scope for this iteration and will come later.

The ``user_profiles`` table is created lazily and idempotently
(``CREATE TABLE IF NOT EXISTS``) through the existing SQLAlchemy engine, using
PostgreSQL JSONB for the profile payload. Nothing here calls Groq, the vector
store, or any external service.
"""

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db import get_engine

TABLE_NAME = "user_profiles"

_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    profile_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    profile JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def init_table(engine: Engine | None = None) -> None:
    """Create the profiles table if it does not already exist (idempotent)."""
    eng = engine or get_engine()
    with eng.begin() as conn:
        conn.execute(text(_CREATE_TABLE_SQL))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _tokens_match(stored_hash: str, raw_token: str) -> bool:
    return secrets.compare_digest(stored_hash, _hash_token(raw_token))


def _row_to_dict(row) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "profile_id": row["profile_id"],
        "profile": row["profile"],
        "created_at": row["created_at"].isoformat(timespec="seconds"),
        "updated_at": row["updated_at"].isoformat(timespec="seconds"),
    }


def create_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Create a profile row and return the one-time raw access token.

    The returned dict contains ``profile_id``, ``access_token`` (raw, shown to
    the citizen exactly once), ``profile``, ``created_at`` and ``updated_at``.
    Only the SHA-256 hash of the token is stored in the database.
    """
    profile_id = secrets.token_urlsafe(16)
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now = _now_iso()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {TABLE_NAME} "
                "(profile_id, token_hash, profile, created_at, updated_at) "
                "VALUES (:profile_id, :token_hash, :profile, :created_at, :updated_at)"
            ),
            {
                "profile_id": profile_id,
                "token_hash": token_hash,
                "profile": json.dumps(profile),
                "created_at": now,
                "updated_at": now,
            },
        )
    return {
        "profile_id": profile_id,
        "access_token": raw_token,
        "profile": profile,
        "created_at": now,
        "updated_at": now,
    }


def _fetch_profile_row(engine: Engine, profile_id: str):
    with engine.connect() as conn:
        return (
            conn.execute(
                text(
                    f"SELECT profile_id, token_hash, profile, created_at, updated_at "
                    f"FROM {TABLE_NAME} WHERE profile_id = :profile_id"
                ),
                {"profile_id": profile_id},
            )
            .mappings()
            .first()
        )


def _authenticate(engine: Engine, profile_id: str, raw_token: str):
    """Return the stored row only when the token matches (constant-time compare)."""
    row = _fetch_profile_row(engine, profile_id)
    if row is None or not _tokens_match(row["token_hash"], raw_token):
        return None
    return row


def get_profile(profile_id: str, raw_token: str) -> dict[str, Any] | None:
    """Return the profile row or ``None`` when the id/token pair is invalid."""
    row = _authenticate(get_engine(), profile_id, raw_token)
    return _row_to_dict(row)


def update_profile(
    profile_id: str, raw_token: str, profile: dict[str, Any]
) -> dict[str, Any] | None:
    """Replace the stored profile payload; returns the updated row or ``None``."""
    engine = get_engine()
    row = _authenticate(engine, profile_id, raw_token)
    if row is None:
        return None
    now = _now_iso()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"UPDATE {TABLE_NAME} SET profile = :profile, updated_at = :updated_at "
                f"WHERE profile_id = :profile_id"
            ),
            {
                "profile": json.dumps(profile),
                "updated_at": now,
                "profile_id": profile_id,
            },
        )
    return {
        "profile_id": profile_id,
        "profile": profile,
        "created_at": row["created_at"].isoformat(timespec="seconds"),
        "updated_at": now,
    }


def delete_profile(profile_id: str, raw_token: str) -> bool:
    """Delete the profile; returns ``True`` only when id/token validated."""
    engine = get_engine()
    row = _authenticate(engine, profile_id, raw_token)
    if row is None:
        return False
    with engine.begin() as conn:
        conn.execute(
            text(f"DELETE FROM {TABLE_NAME} WHERE profile_id = :profile_id"),
            {"profile_id": profile_id},
        )
    return True
