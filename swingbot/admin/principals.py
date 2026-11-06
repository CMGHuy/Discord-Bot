"""v207: viewer principals -- the database half of "who is this".

The `.env` admin stays in app.py (`credentials_match`, `_password_hash`) and
is never stored. Every `admin_users` row is a read-only viewer. This module
hashes and checks viewer passwords, validates new usernames and passwords, and
answers the two lookups the admin needs: "do these credentials name a live
viewer" (login) and "is this session's viewer still valid" (every request).

It imports nothing from swingbot.admin: app.py imports it, and the admin test
suite reloads app.py per test. HASH_METHOD is read at call time so that suite
can swap scrypt for a cheap method. Nothing here logs, returns or serialises a
password; only authenticate_viewer returns the stored hash, inside the row the
login code discards.
"""
from __future__ import annotations

import re
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

from swingbot.core.db.repositories import admin_users

HASH_METHOD = "scrypt"
PASSWORD_MIN = 12
USERNAME_RE = re.compile(r"[A-Za-z0-9._-]{3,64}")
USERNAME_RULE = "username must be 3-64 characters: letters, digits, '.', '_' or '-'."
PASSWORD_RULE = f"password must be at least {PASSWORD_MIN} characters."

# One dummy hash per method, made on first use: an unknown username still pays
# for one real check, so response time does not reveal which names exist.
_DUMMY_HASHES: dict[str, str] = {}


def hash_password(password: str) -> str:
    return generate_password_hash(password, method=HASH_METHOD)


def _dummy_hash() -> str:
    method = HASH_METHOD
    if method not in _DUMMY_HASHES:
        _DUMMY_HASHES[method] = generate_password_hash(secrets.token_urlsafe(24),
                                                       method=method)
    return _DUMMY_HASHES[method]


def verify_password(pw_hash: str | None, password: str) -> bool:
    if pw_hash is None:
        check_password_hash(_dummy_hash(), password)
        return False
    return check_password_hash(pw_hash, password)


def validate_username(name) -> str | None:
    if isinstance(name, str) and USERNAME_RE.fullmatch(name):
        return None
    return USERNAME_RULE


def validate_password(password) -> str | None:
    if isinstance(password, str) and len(password) >= PASSWORD_MIN:
        return None
    return PASSWORD_RULE


def authenticate_viewer(username: str, password: str) -> dict | None:
    """The viewer row these credentials name, or None. Unknown, disabled and
    wrong-password cases each run exactly one hash check."""
    repo = admin_users.admin_users_repo()
    row = repo.get_by_username(username) if username else None
    matched = verify_password(row["password_hash"] if row else None, password)
    if row is None or row["disabled"] or not matched:
        return None
    repo.touch_last_login(row["id"])
    return row


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def viewer_principal(user_id, credential_version) -> dict | None:
    """The principal for a viewer session's fields while they are still valid."""
    if not (_is_int(user_id) and _is_int(credential_version)):
        return None
    row = admin_users.admin_users_repo().get_by_id(user_id)
    if row is None or row["disabled"] or row["credential_version"] != credential_version:
        return None
    return {"role": "viewer", "username": row["username"], "user_id": row["id"]}
