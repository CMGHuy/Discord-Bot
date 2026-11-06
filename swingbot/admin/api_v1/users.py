"""v207: /api/v1/users -- viewer accounts, managed by the .env admin.

Spec: docs/superpowers/specs/2026-11-05-v207-viewer-accounts-design.md
§ Users API. Admin-only by prefix (swingbot.admin.access): the api_v1 access
hook refuses every viewer before these handlers run; @require_auth still
answers 401 when there is no principal at all.

Never returns, logs or serialises a password, a hash or credential_version.
Disable and password reset bump credential_version in the repository, which
is what ends a viewer's live sessions (app.principal_from_session).
"""
from __future__ import annotations

import logging

from flask import jsonify, request

from swingbot.admin import app as _app  # module, not names: tests reload app
from swingbot.admin import principals
from swingbot.core.db.repositories import admin_users

from . import api_v1, error, iso
from .auth import require_auth

log = logging.getLogger(__name__)

TAKEN = "username is already taken."


def user_out(row: dict) -> dict:
    """The one public shape of a viewer row (UserOut)."""
    return {"id": row["id"], "username": row["username"], "role": row["role"],
            "disabled": row["disabled"], "created_at": iso(row["created_at"]),
            "last_login_at": iso(row["last_login_at"])}


def _body() -> dict:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _not_found(user_id: int):
    return error("not_found", f"No user with id {user_id}.", 404)


def _audit(action: str, username: str) -> None:
    log.info("users: %s %s by admin", action, username)


def _create_problem(username, password):
    """The 400/409 answer for a create request, or None when it may proceed."""
    message = principals.validate_username(username) or principals.validate_password(password)
    if message:
        return error("invalid", message, 400)
    if _app.ADMIN_USERNAME.lower() == username.lower():
        return error("conflict", TAKEN, 409)
    return None


@api_v1.route("/users", methods=["GET"])
@require_auth
def list_users():
    return jsonify({"users": [user_out(r) for r in admin_users.admin_users_repo().list_users()]})


@api_v1.route("/users", methods=["POST"])
@require_auth
def create_user():
    body = _body()
    username, password = body.get("username"), body.get("password")
    problem = _create_problem(username, password)
    if problem is not None:
        return problem
    try:
        row = admin_users.admin_users_repo().create_user(
            username, principals.hash_password(password))
    except admin_users.UsernameTaken:
        return error("conflict", TAKEN, 409)
    _audit("create", row["username"])
    return jsonify(user_out(row)), 201


@api_v1.route("/users/<int:user_id>", methods=["PATCH"])
@require_auth
def update_user(user_id: int):
    disabled = _body().get("disabled")
    if not isinstance(disabled, bool):
        return error("invalid", "disabled must be true or false.", 400)
    row = admin_users.admin_users_repo().set_disabled(user_id, disabled)
    if row is None:
        return _not_found(user_id)
    _audit("disable" if disabled else "enable", row["username"])
    return jsonify(user_out(row))


@api_v1.route("/users/<int:user_id>/password", methods=["POST"])
@require_auth
def reset_user_password(user_id: int):
    password = _body().get("password")
    message = principals.validate_password(password)
    if message:
        return error("invalid", message, 400)
    row = admin_users.admin_users_repo().reset_password(
        user_id, principals.hash_password(password))
    if row is None:
        return _not_found(user_id)
    _audit("reset-password", row["username"])
    return "", 204


@api_v1.route("/users/<int:user_id>", methods=["DELETE"])
@require_auth
def delete_user(user_id: int):
    repo = admin_users.admin_users_repo()
    row = repo.get_by_id(user_id)
    if row is None or not repo.delete_user(user_id):
        return _not_found(user_id)
    _audit("delete", row["username"])
    return "", 204
