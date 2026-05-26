from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from app.services import metadata_db
from app.utils import workspace


@dataclass
class StoredUser:
    name: str
    email: str
    password_hash: str
    salt: str
    created_at: str


@dataclass
class ResetTokenRecord:
    email: str
    token: str
    created_at: str
    expires_at: str


# --- legacy json paths -----------------------------------------------------

def _auth_root() -> str:
    return workspace.state_dir("auth", create=True)


def _users_path() -> str:
    return os.path.join(_auth_root(), "users.json")


def _sessions_path() -> str:
    return os.path.join(_auth_root(), "sessions.json")


def _reset_tokens_path() -> str:
    return os.path.join(_auth_root(), "reset_tokens.json")


# --- small utils -----------------------------------------------------------

def _read_json(path: str) -> Dict[str, Dict]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return {}


def _hash_password(password: str, salt: bytes) -> str:
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return base64.b64encode(hashed).decode("utf-8")


def _encode_salt(raw: bytes) -> str:
    return base64.b64encode(raw).decode("utf-8")


def _decode_salt(encoded: str) -> bytes:
    return base64.b64decode(encoded.encode("utf-8"))


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _hash_token(token: str) -> str:
    """Return the stable database key for a bearer token.

    Raw session tokens are only returned to the client once. The database stores
    a one-way hash so a leaked SQLite file cannot immediately be used as a
    bearer credential. Existing legacy/plaintext rows are still accepted once
    and migrated on access.
    """
    value = str(token or "").strip()
    if value.startswith("sha256:"):
        return value
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _session_lookup_keys(token: str) -> tuple[str, str]:
    raw = str(token or "").strip()
    return _hash_token(raw), raw


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _session_ttl_seconds() -> int:
    raw = str(os.getenv("AIVIDEO_SESSION_TTL_SECONDS", "") or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            return 7 * 24 * 60 * 60
    raw_hours = str(os.getenv("AIVIDEO_SESSION_TTL_HOURS", "168") or "168").strip()
    try:
        return max(0, int(float(raw_hours) * 3600))
    except ValueError:
        return 7 * 24 * 60 * 60


def _is_session_expired(last_seen: str, created_at: str = "") -> bool:
    ttl = _session_ttl_seconds()
    if ttl <= 0:
        return False
    base = _parse_iso(last_seen) or _parse_iso(created_at)
    if base is None:
        return True
    return (_utc_now() - base).total_seconds() > ttl


# --- legacy import ---------------------------------------------------------

def _legacy_users() -> Dict[str, StoredUser]:
    data = _read_json(_users_path())
    users: Dict[str, StoredUser] = {}
    for email, payload in data.items():
        normalized = _normalize_email(email)
        users[normalized] = StoredUser(
            name=payload.get("name", normalized.split("@")[0]),
            email=normalized,
            password_hash=payload.get("password_hash", ""),
            salt=payload.get("salt", ""),
            created_at=payload.get("created_at", ""),
        )
    return users


def _legacy_sessions() -> Dict[str, Dict[str, str]]:
    return _read_json(_sessions_path())


def _legacy_reset_tokens() -> Dict[str, ResetTokenRecord]:
    data = _read_json(_reset_tokens_path())
    records: Dict[str, ResetTokenRecord] = {}
    for token, payload in data.items():
        records[token] = ResetTokenRecord(
            email=_normalize_email(payload.get("email", "")),
            token=token,
            created_at=payload.get("created_at", ""),
            expires_at=payload.get("expires_at", ""),
        )
    return records


def _import_legacy_if_needed() -> None:
    existing = metadata_db.fetch_one("SELECT COUNT(*) AS cnt FROM users")
    if existing and int(existing["cnt"] or 0) > 0:
        return

    users = _legacy_users()
    sessions = _legacy_sessions()
    reset_tokens = _legacy_reset_tokens()
    if not users and not sessions and not reset_tokens:
        return

    with metadata_db.connect() as conn:
        for email, user in users.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO users(email, name, password_hash, salt, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (email, user.name, user.password_hash, user.salt, user.created_at or _utc_now().isoformat()),
            )
        for token, payload in sessions.items():
            email = _normalize_email(payload.get("email", ""))
            if not email:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO user_sessions(token, email, created_at, last_seen)
                VALUES (?, ?, ?, ?)
                """,
                (
                    _hash_token(token),
                    email,
                    payload.get("created_at") or _utc_now().isoformat(),
                    payload.get("last_seen") or payload.get("created_at") or _utc_now().isoformat(),
                ),
            )
        for token, record in reset_tokens.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO password_reset_tokens(token, email, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, record.email, record.created_at or _utc_now().isoformat(), record.expires_at or _utc_now().isoformat()),
            )


# --- DB loaders ------------------------------------------------------------

def _row_to_user(row) -> StoredUser:
    return StoredUser(
        name=str(row["name"]),
        email=_normalize_email(row["email"]),
        password_hash=str(row["password_hash"]),
        salt=str(row["salt"]),
        created_at=str(row["created_at"]),
    )


def _load_users() -> Dict[str, StoredUser]:
    _import_legacy_if_needed()
    rows = metadata_db.fetch_all(
        "SELECT email, name, password_hash, salt, created_at FROM users ORDER BY created_at ASC"
    )
    return {_normalize_email(row["email"]): _row_to_user(row) for row in rows}


def _load_sessions() -> Dict[str, Dict[str, str]]:
    _import_legacy_if_needed()
    rows = metadata_db.fetch_all(
        "SELECT token, email, created_at, last_seen FROM user_sessions ORDER BY created_at DESC"
    )
    return {
        str(row["token"]): {
            "email": _normalize_email(row["email"]),
            "created_at": str(row["created_at"]),
            "last_seen": str(row["last_seen"]),
        }
        for row in rows
    }


def _load_reset_tokens() -> Dict[str, ResetTokenRecord]:
    _import_legacy_if_needed()
    rows = metadata_db.fetch_all(
        "SELECT token, email, created_at, expires_at FROM password_reset_tokens ORDER BY created_at DESC"
    )
    return {
        str(row["token"]): ResetTokenRecord(
            email=_normalize_email(row["email"]),
            token=str(row["token"]),
            created_at=str(row["created_at"]),
            expires_at=str(row["expires_at"]),
        )
        for row in rows
    }


def _save_user(user: StoredUser) -> None:
    metadata_db.execute(
        """
        INSERT OR REPLACE INTO users(email, name, password_hash, salt, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user.email, user.name, user.password_hash, user.salt, user.created_at),
    )


def _save_session(token: str, email: str, created_at: str, last_seen: str) -> None:
    metadata_db.execute(
        """
        INSERT OR REPLACE INTO user_sessions(token, email, created_at, last_seen)
        VALUES (?, ?, ?, ?)
        """,
        (_hash_token(token), _normalize_email(email), created_at, last_seen),
    )


def _save_reset_token(record: ResetTokenRecord) -> None:
    metadata_db.execute(
        """
        INSERT OR REPLACE INTO password_reset_tokens(token, email, created_at, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (record.token, record.email, record.created_at, record.expires_at),
    )


def _purge_expired_reset_tokens(records: Optional[Dict[str, ResetTokenRecord]] = None) -> Dict[str, ResetTokenRecord]:
    current = records if records is not None else _load_reset_tokens()
    now = _utc_now()
    active: Dict[str, ResetTokenRecord] = {}
    for token, record in current.items():
        expires_at = _parse_iso(record.expires_at)
        if expires_at is None or expires_at > now:
            active[token] = record
        else:
            metadata_db.execute("DELETE FROM password_reset_tokens WHERE token = ?", (token,))
    return active


# --- public API ------------------------------------------------------------

def _fetch_session_row(token: str):
    hashed, raw = _session_lookup_keys(token)
    row = metadata_db.fetch_one(
        "SELECT token, email, created_at, last_seen FROM user_sessions WHERE token = ?",
        (hashed,),
    )
    if row:
        return row
    if raw and raw != hashed:
        row = metadata_db.fetch_one(
            "SELECT token, email, created_at, last_seen FROM user_sessions WHERE token = ?",
            (raw,),
        )
        if row:
            # One-time migration from old plaintext token rows.
            existing = metadata_db.fetch_one("SELECT token FROM user_sessions WHERE token = ?", (hashed,))
            if existing is None:
                metadata_db.execute("UPDATE user_sessions SET token = ? WHERE token = ?", (hashed, raw))
                row = metadata_db.fetch_one(
                    "SELECT token, email, created_at, last_seen FROM user_sessions WHERE token = ?",
                    (hashed,),
                )
            else:
                metadata_db.execute("DELETE FROM user_sessions WHERE token = ?", (raw,))
                row = metadata_db.fetch_one(
                    "SELECT token, email, created_at, last_seen FROM user_sessions WHERE token = ?",
                    (hashed,),
                )
        return row
    return None


def _bootstrap_defaults() -> tuple[bool, str, str, str]:
    explicit = os.getenv("AIVIDEO_BOOTSTRAP_DEFAULT_LOGIN")
    env_name = str(os.getenv("AIVIDEO_ENV") or os.getenv("ENV") or "").strip().lower()
    default_enabled = "0" if env_name in {"prod", "production"} else "1"
    enabled = str(explicit if explicit is not None else default_enabled).strip().lower() not in {"0", "false", "no"}
    name = str(os.getenv("AIVIDEO_BOOTSTRAP_NAME", "Demo User") or "Demo User").strip() or "Demo User"
    email = _normalize_email(os.getenv("AIVIDEO_BOOTSTRAP_EMAIL", "demo@aivideo.local"))
    password = str(os.getenv("AIVIDEO_BOOTSTRAP_PASSWORD", "12345678") or "12345678")
    return enabled, name, email, password


def ensure_bootstrap_user(created_at: Optional[str] = None) -> Optional[StoredUser]:
    if user_count() > 0:
        users = _load_users()
        return next(iter(users.values())) if users else None
    enabled, name, email, password = _bootstrap_defaults()
    if not enabled or not email or not password:
        return None
    timestamp = created_at or _utc_now().isoformat()
    return register_user(name, email, password, timestamp)


def user_count() -> int:
    _import_legacy_if_needed()
    row = metadata_db.fetch_one("SELECT COUNT(*) AS cnt FROM users")
    return int(row["cnt"] or 0) if row else 0


def get_user_by_email(email: str) -> Optional[StoredUser]:
    normalized = _normalize_email(email)
    row = metadata_db.fetch_one(
        "SELECT email, name, password_hash, salt, created_at FROM users WHERE email = ?",
        (normalized,),
    )
    return _row_to_user(row) if row else None


def register_user(name: str, email: str, password: str, created_at: str) -> StoredUser:
    normalized = _normalize_email(email)
    if get_user_by_email(normalized):
        raise ValueError("email_exists")
    salt = os.urandom(16)
    user = StoredUser(
        name=str(name or "").strip() or normalized.split("@")[0],
        email=normalized,
        password_hash=_hash_password(password, salt),
        salt=_encode_salt(salt),
        created_at=created_at,
    )
    _save_user(user)
    return user


def authenticate(email: str, password: str) -> Optional[StoredUser]:
    user = get_user_by_email(email)
    if not user:
        return None
    salt = _decode_salt(user.salt)
    password_hash = _hash_password(password, salt)
    if password_hash != user.password_hash:
        return None
    return user


def create_session(email: str, created_at: str) -> str:
    token = secrets.token_urlsafe(32)
    _save_session(token, email, created_at, created_at)
    return token


def touch_session(token: str, seen_at: str) -> None:
    row = _fetch_session_row(token)
    if not row:
        return
    stored_token = str(row["token"])
    if _is_session_expired(str(row["last_seen"] or ""), str(row["created_at"] or "")):
        metadata_db.execute("DELETE FROM user_sessions WHERE token = ?", (stored_token,))
        return
    _save_session(token, str(row["email"]), str(row["created_at"]), seen_at)


def get_user_by_token(token: str) -> Optional[StoredUser]:
    session = _fetch_session_row(token)
    if not session:
        return None
    row = metadata_db.fetch_one(
        """
        SELECT
            u.email, u.name, u.password_hash, u.salt, u.created_at,
            s.token AS session_token,
            s.created_at AS session_created_at, s.last_seen AS session_last_seen
        FROM user_sessions s
        JOIN users u ON u.email = s.email
        WHERE s.token = ?
        """,
        (str(session["token"]),),
    )
    if not row:
        return None
    if _is_session_expired(str(row["session_last_seen"] or ""), str(row["session_created_at"] or "")):
        metadata_db.execute("DELETE FROM user_sessions WHERE token = ?", (str(row["session_token"]),))
        return None
    return _row_to_user(row)


def revoke_token(token: str) -> bool:
    existing = _fetch_session_row(token)
    if not existing:
        return False
    metadata_db.execute("DELETE FROM user_sessions WHERE token = ?", (str(existing["token"]),))
    return True


def revoke_user_sessions(email: str) -> int:
    normalized = _normalize_email(email)
    row = metadata_db.fetch_one("SELECT COUNT(*) AS cnt FROM user_sessions WHERE email = ?", (normalized,))
    removed = int(row["cnt"] or 0) if row else 0
    metadata_db.execute("DELETE FROM user_sessions WHERE email = ?", (normalized,))
    return removed


def issue_password_reset(email: str, created_at: str, *, expires_minutes: int = 30) -> Optional[ResetTokenRecord]:
    user = get_user_by_email(email)
    if not user:
        return None
    current = _purge_expired_reset_tokens(_load_reset_tokens())
    normalized = _normalize_email(email)
    for token, record in list(current.items()):
        if record.email == normalized:
            metadata_db.execute("DELETE FROM password_reset_tokens WHERE token = ?", (token,))
            current.pop(token, None)
    created_dt = _parse_iso(created_at) or _utc_now()
    record = ResetTokenRecord(
        email=normalized,
        token=secrets.token_urlsafe(32),
        created_at=created_dt.isoformat(),
        expires_at=(created_dt + timedelta(minutes=expires_minutes)).isoformat(),
    )
    _save_reset_token(record)
    return record


def consume_password_reset(token: str, new_password: str) -> Optional[StoredUser]:
    current = _purge_expired_reset_tokens(_load_reset_tokens())
    lookup = str(token or "").strip()
    record = current.get(lookup)
    if not record:
        return None
    user = get_user_by_email(record.email)
    if not user:
        metadata_db.execute("DELETE FROM password_reset_tokens WHERE token = ?", (lookup,))
        return None
    salt = os.urandom(16)
    user.password_hash = _hash_password(new_password, salt)
    user.salt = _encode_salt(salt)
    _save_user(user)
    metadata_db.execute("DELETE FROM password_reset_tokens WHERE token = ?", (lookup,))
    revoke_user_sessions(user.email)
    return user


def change_password(email: str, current_password: str, new_password: str) -> StoredUser:
    user = authenticate(email, current_password)
    if not user:
        raise ValueError("invalid_credentials")
    salt = os.urandom(16)
    user.password_hash = _hash_password(new_password, salt)
    user.salt = _encode_salt(salt)
    _save_user(user)
    revoke_user_sessions(user.email)
    return user
