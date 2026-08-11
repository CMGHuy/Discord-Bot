"""GET/PUT /api/v1/system/settings and friends — the .env editor.

**The highest-risk endpoint in the REST phase.** A bad write here takes the
bot down, and unlike a wrong number on a dashboard it does so silently: the
container hot-reloads whatever landed in .env. Three properties matter more
than convenience, and each is pinned by a test.

*Schema and values travel together, generated from `config.FIELDS`.* Spec
v14 Decision 8: the form renders from the schema and the SPA hardcodes no
field list, so a new `Field` in config.py appears in the UI with zero
frontend change. That is a property the Jinja UI has today and the rebuild
must not lose -- `test_a_new_field_appears_with_no_endpoint_change` is what
notices if this endpoint ever grows an explicit list.

*Omitted keys mean "unchanged", not "clear".* This is the one place the v1
convention of rejecting anything unrecognised is inverted, deliberately.
`_build_env_text` rewrites the WHOLE file from the mapping it is handed, so
a partial body run through it straight would write `KEY=` for every field
the client did not mention -- a config-wiping write dressed as an edit. The
submitted keys are therefore overlaid onto the values already on disk, which
also fixes the checkbox asymmetry: a browser form posts an unchecked box by
omitting it, so absence cannot mean false here.

*A masked value is never written.* Sensitive fields read back as `•••`, and
a client that echoes the object it was given would otherwise save the mask
as the Discord token. `•••` on a sensitive field is treated as "no change",
exactly as blank already is.

Nothing about .env parsing, diffing or writing is reimplemented here: this
module adapts JSON to the mapping shape `helpers.py` already expects and
calls the same `settings_diff` / `_build_env_text` / `import_env_text` the
Jinja routes call. A second definition of "blank means no change" would let
the diff a user approves differ from the write they get.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from flask import Response, jsonify, request

from swingbot import config

from . import api_v1, error
from .auth import require_auth

# The literal helpers.settings_diff already masks with. Same string, so the
# UI never shows two different "hidden" markers for the same reason.
MASK = "•••"

_TRUTHY = frozenset({"true", "on", "1", "yes"})


def _fields_by_key() -> dict:
    from swingbot.admin.helpers import FIELDS_BY_KEY
    return FIELDS_BY_KEY


def _truthy(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in _TRUTHY


def _field_json(f: config.Field, raw_value: Any) -> dict:
    """One Field as schema + value. Sensitive values never leave as themselves."""
    if f.type == "checkbox":
        value: Any = _truthy(raw_value)
    elif f.sensitive:
        # Masked even when empty would be harmless: whether a secret is SET is
        # itself worth not broadcasting, and a client cannot tell the two
        # apart anyway because it may not write either back.
        value = MASK
    else:
        value = raw_value

    return {
        "key": f.key,
        "label": f.label,
        "type": f.type,
        "value": value,
        "default": f.default,
        "help": f.help,
        "min": f.min,
        "max": f.max,
        "step": f.step,
        "options": [{"value": v, "label": lbl} for v, lbl in f.options],
        "sensitive": f.sensitive,
        "hot_reloadable": f.hot_reloadable,
    }


def _settings_document() -> dict:
    from swingbot.admin.app import _SECTION_META, docker_sdk
    from swingbot.admin.helpers import (FIELDS_BY_SECTION, _read_env_values,
                                        read_settings_audit)

    env_values = _read_env_values()
    return {
        "sections": [
            {
                "name": section,
                "icon": _SECTION_META.get(section, ("", ""))[0],
                "description": _SECTION_META.get(section, ("", ""))[1],
                "fields": [
                    _field_json(f, env_values.get(f.key, f.default)) for f in fields
                ],
            }
            for section, fields in FIELDS_BY_SECTION
        ],
        # Already masked: append_settings_audit writes settings_diff's output,
        # whose sensitive entries are •••  on both sides.
        "audit": read_settings_audit(20),
        "restart_available": docker_sdk is not None,
    }


def _submitted(payload: Mapping) -> dict | None:
    """The `settings` object from a request body, or None if it is not one."""
    values = payload.get("settings")
    return values if isinstance(values, Mapping) else None


def _validate(values: Mapping) -> tuple[str, str] | None:
    """(code, message) for the first problem found, or None.

    Rejects rather than skips. `import_env_text` silently drops a bad numeric
    because it processes a pasted file where partial success is the point;
    here the client built the object field by field, so a value it cannot
    write back is a client bug, and a silent skip would report success for a
    setting that never changed.
    """
    fields = _fields_by_key()
    unknown = [k for k in values if k not in fields]
    if unknown:
        return ("invalid",
                f"unknown setting(s): {', '.join(sorted(unknown)[:10])}")

    for key, raw in values.items():
        f = fields[key]
        if f.type in ("number", "float") and not (raw is None or raw == ""):
            try:
                number = float(raw)
            except (TypeError, ValueError):
                return ("invalid", f"{f.label} must be a number, got {raw!r}")
            if f.min is not None and number < f.min:
                return ("invalid", f"{f.label} must be at least {f.min}")
            if f.max is not None and number > f.max:
                return ("invalid", f"{f.label} must be at most {f.max}")
        if f.type == "select" and f.options and raw not in [v for v, _ in f.options]:
            return ("invalid",
                    f"{f.label} must be one of {[v for v, _ in f.options]}")
    return None


def _effective_form(values: Mapping) -> dict:
    """Submitted keys overlaid on what is already on disk, in form shape.

    Every field appears, so `_build_env_text` and `settings_diff` see the
    full-form submission they were written for. See this module's docstring
    for why a partial body cannot be handed to them directly.
    """
    from swingbot.admin.helpers import _read_env_values

    existing = _read_env_values()
    form: dict[str, str] = {}
    for f in config.FIELDS:
        current = existing.get(f.key, f.default)
        if f.key in values:
            raw = values[f.key]
            # A sensitive field echoed back as the mask means "leave it",
            # exactly as blank already does. Writing ••• as a real token is
            # the failure this prevents.
            if f.sensitive and (raw == MASK or raw is None or raw == ""):
                raw = current
        else:
            raw = current

        if f.type == "checkbox":
            # Unchecked is ABSENT, which is how a browser posts it and what
            # every helper here reads.
            if _truthy(raw):
                form[f.key] = "on"
        else:
            form[f.key] = "" if raw is None else str(raw)
    return form


def _diff_for(values: Mapping) -> tuple[list, list]:
    from swingbot.admin.helpers import (_changed_non_hot_reloadable_fields,
                                        _read_env_values, settings_diff)

    existing = _read_env_values()
    form = _effective_form(values)
    return settings_diff(form, existing), _changed_non_hot_reloadable_fields(existing, form)


@api_v1.route("/system/settings", methods=["GET"])
@require_auth
def get_settings():
    return jsonify(_settings_document())


@api_v1.route("/system/settings/preview", methods=["POST"])
@require_auth
def preview_settings():
    """The diff a user approves. Produced by the same `settings_diff` the
    save path runs, over the same effective form -- so what is shown and
    what is written cannot disagree."""
    values = _submitted(request.get_json(silent=True) or {})
    if values is None:
        return error("invalid", "Body must contain a 'settings' object.", 400)
    problem = _validate(values)
    if problem:
        return error(problem[0], problem[1], 400)

    diff, restart_required = _diff_for(values)
    return jsonify({"diff": diff, "restart_required": restart_required})


@api_v1.route("/system/settings", methods=["PUT"])
@require_auth
def save_settings():
    from swingbot.admin.helpers import (_build_env_text, _hot_reload_bot_container,
                                        _read_env_values, _write_env_text,
                                        append_settings_audit)

    values = _submitted(request.get_json(silent=True) or {})
    if values is None:
        return error("invalid", "Body must contain a 'settings' object.", 400)
    problem = _validate(values)
    if problem:
        return error(problem[0], problem[1], 400)

    existing = _read_env_values()
    form = _effective_form(values)
    diff, restart_required = _diff_for(values)

    _write_env_text(_build_env_text(form, existing))
    append_settings_audit(diff)

    ok, message = _hot_reload_bot_container()
    return jsonify({
        "diff": diff,
        "restart_required": restart_required,
        # Not an error: the write SUCCEEDED and the file on disk is correct.
        # Only the signal telling the bot to re-read it failed, which is
        # routine outside Docker -- reporting 500 here would tell the user
        # their settings did not save when they did.
        "hot_reload": {"ok": ok, "message": message},
    })


@api_v1.route("/system/settings/export", methods=["GET"])
@require_auth
def export_settings():
    """Stays a file download (spec v11). Body from the same
    `build_settings_export_text` the Jinja route uses, so the two exports are
    byte-identical -- which is what makes sub-project 6's comparison
    meaningful."""
    from swingbot.admin.helpers import build_settings_export_text

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        build_settings_export_text(),
        mimetype="text/plain",
        headers={"Content-Disposition":
                 f"attachment; filename=swingbot-settings-{today}.env"},
    )


@api_v1.route("/system/settings/import", methods=["POST"])
@require_auth
def import_settings():
    """Applies recognised keys and names the ones it skipped.

    Lenient where PUT is strict, and the asymmetry is the point: this body is
    a file someone pasted, quite possibly an export from an older build, and
    refusing the whole thing over one retired key would make every upgrade
    path a manual edit. PUT's body was assembled field by field from this
    endpoint's own schema, so an unknown key there is a bug worth surfacing.
    """
    from swingbot.admin.helpers import import_env_text

    text = ""
    upload = request.files.get("file") or request.files.get("env_file")
    if upload and upload.filename:
        text = upload.read().decode("utf-8", errors="replace")
    else:
        payload = request.get_json(silent=True) or {}
        text = payload.get("text") or ""
    if not isinstance(text, str) or not text.strip():
        return error("invalid", "Body must contain 'text' or a 'file' upload.", 400)

    applied, unknown = import_env_text(text)
    return jsonify({"applied": applied, "unknown_keys": unknown})
