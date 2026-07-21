"""
Pure helper functions for the admin web UI -- .env <-> structured
settings-field conversion, Docker bot-container control (restart/hot
reload), confidence-color formatting, and log-file tailing/clearing.
None of these touch the Flask `app` object or a route decorator, so
they're split out of app.py into their own module rather than adding to
that file's already-long list of routes; app.py imports every one of
these back and calls them exactly as before.
"""
import io
import json
import os
from datetime import datetime, timezone
from itertools import groupby

from dotenv import dotenv_values

from swingbot import config
from swingbot.core.performance import primary_strategy_label as _primary_strategy_label
from swingbot.core.scan_engine import CONFIDENCE_COLORS

try:
    import docker as docker_sdk
except ImportError:
    docker_sdk = None

BOT_CONTAINER_NAME = os.getenv("BOT_CONTAINER_NAME", "swing-bot")

# Single source of truth for the version numbers shown in the sidebar (see
# base.html) -- one file at the project root, {"ui": "x.y.z", "bot": "x.y.z"},
# bumped by 0.0.1 (whichever side actually changed) any time a change is
# made to this codebase. Not read by config.py/FIELDS -- this is a plain
# static file, not an .env-driven runtime setting.
VERSION_PATH = os.path.join(config._PROJECT_ROOT, "VERSION.json")

ENV_PATH = config.ENV_PATH  # same .env config.py itself reads -- single source of truth for the path

FIELDS_BY_SECTION = [(section, list(fields)) for section, fields in groupby(config.FIELDS, key=lambda f: f.section)]
FIELDS_BY_KEY = {f.key: f for f in config.FIELDS}


# ---------------------------------------------------------------------------
# .env <-> structured fields
# ---------------------------------------------------------------------------
def _read_env_values() -> dict:
    """Raw key->value straight from the .env file on disk (not the live,
    possibly-already-reloaded config module) -- what the form should show
    reflects what's actually saved, not necessarily what the bot is
    currently running with."""
    if not os.path.exists(ENV_PATH):
        return {}
    return {k: v for k, v in dotenv_values(ENV_PATH).items() if v is not None}


def _field_display_value(f: config.Field, env_values: dict):
    raw = env_values.get(f.key, f.default)
    if f.type == "checkbox":
        return str(raw).lower() == "true"
    return raw


def _build_env_text(form, existing: dict) -> str:
    """
    Reconstructs the whole .env file: one section-commented block per
    FIELDS group with every known field's new value from the submitted
    form, followed by any keys that existed in the file but aren't
    covered by FIELDS -- so a manually-added custom variable is never
    silently dropped just because the structured UI doesn't know about it.
    """
    known_keys = set(FIELDS_BY_KEY)
    lines = [
        "# Managed by the Swing Bot admin UI.",
        "# Structured fields below are grouped by section; anything else",
        "# found in the previous .env is preserved at the bottom untouched.",
        "",
    ]
    for section, fields in FIELDS_BY_SECTION:
        lines.append(f"# --- {section} ---")
        for f in fields:
            if f.type == "checkbox":
                value = "true" if form.get(f.key) == "on" else "false"
            else:
                value = form.get(f.key, "")
                if value == "" and f.key in existing:
                    # Field was left blank in the form -- for anything
                    # sensitive in particular, treat blank as "no change"
                    # rather than wiping out a real secret by accident.
                    value = existing[f.key]
            lines.append(f"{f.key}={value}")
        lines.append("")

    leftover = {k: v for k, v in existing.items() if k not in known_keys}
    if leftover:
        lines.append("# --- Other / custom variables (not managed by the fields above) ---")
        for k, v in leftover.items():
            lines.append(f"{k}={v}")
        lines.append("")

    return "\n".join(lines)


def _write_env_text(text: str) -> None:
    # Explicit utf-8 on every handle here (matches dotenv_values' own
    # default encoding='utf-8' used throughout this module) -- without it,
    # `open()` falls back to the platform's locale-preferred encoding,
    # which silently mangles a non-ASCII field default (e.g. CURRENCY_SYMBOL
    # = "€") on any host whose locale isn't already UTF-8.
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            backup = f.read()
        with open(ENV_PATH + ".bak", "w", encoding="utf-8") as f:
            f.write(backup)
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(text)


def _changed_non_hot_reloadable_fields(old_values: dict, form) -> list:
    changed = []
    for f in config.FIELDS:
        if f.hot_reloadable:
            continue
        old = old_values.get(f.key, f.default)
        new = form.get(f.key, old) if f.type != "checkbox" else ("true" if form.get(f.key) == "on" else "false")
        if f.type != "checkbox" and new == "" and f.key in old_values:
            new = old  # blank -> "no change", same rule as _build_env_text
        if str(old) != str(new):
            changed.append(f.label)
    return changed


def settings_diff(form, existing: dict) -> list[dict]:
    """[{key, label, old, new, sensitive}] for CHANGED fields only --
    sensitive values masked "•••" on both sides regardless of what they
    actually changed to/from, since this is rendered straight into an
    HTML fragment the browser (and, via /settings/preview, the network)
    sees. Mirrors _build_env_text's own "blank form value == no change"
    rule so the diff and the actual save never disagree about what
    counts as a real change."""
    changed = []
    for f in config.FIELDS:
        if f.type == "checkbox":
            # A real full-form submission always represents every checkbox
            # (present as "on" if checked, silently absent if unchecked), so
            # "not in form" normally does mean "unchecked" -- but if a
            # checkbox is missing from BOTH the submitted form and the
            # existing .env, neither side is actually saying anything about
            # it (e.g. a checkbox still at its default on a brand-new .env
            # that's never been saved), so treat that combination as "no
            # change" rather than manufacturing a false true->false diff.
            if f.key not in existing and f.key not in form:
                continue
            old = existing.get(f.key, f.default)
            new = "true" if form.get(f.key) == "on" else "false"
        else:
            old = existing.get(f.key, f.default)
            new = form.get(f.key, old)
            if new == "" and f.key in existing:
                new = old
        if str(old) == str(new):
            continue
        display_old = "•••" if f.sensitive else old
        display_new = "•••" if f.sensitive else new
        changed.append({"key": f.key, "label": f.label, "old": display_old,
                        "new": display_new, "sensitive": f.sensitive})
    return changed


def _audit_log_path() -> str:
    # Resolved at call time (not module-import time) so tests that
    # monkeypatch config.DATA_DIR per-test are honored -- same reasoning
    # as PlanStore._path() and JobManager's _jobs_path().
    return os.path.join(config.DATA_DIR, "settings_audit.jsonl")


def append_settings_audit(diff: list) -> None:
    if not diff:
        return
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "changes": [{"key": d["key"], "old": d["old"], "new": d["new"]} for d in diff],
    }
    path = _audit_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_settings_audit(n: int = 20) -> list[dict]:
    path = _audit_log_path()
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    rows = []
    for line in lines[-n:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows))


def import_env_text(text: str) -> tuple[int, list[str]]:
    """Parses a pasted/uploaded .env-format text, validates each key
    against FIELDS_BY_KEY, type-checks numerics (a bad numeric value is
    silently skipped rather than corrupting .env), and writes the result
    through the same _write_env_text path save_settings itself uses.
    Sensitive keys ARE applied (a deliberate paste of a real credential is
    a legitimate use case) even though settings_export never emits them.
    Returns (applied_count, unknown_keys)."""
    existing = _read_env_values()
    parsed = dotenv_values(stream=io.StringIO(text))
    applied = 0
    unknown = []
    new_values = dict(existing)
    for key, value in parsed.items():
        if value is None:
            continue
        f = FIELDS_BY_KEY.get(key)
        if f is None:
            unknown.append(key)
            continue
        if f.type in ("number", "float"):
            try:
                float(value)
            except ValueError:
                continue
        new_values[key] = value
        applied += 1

    lines = []
    for section, fields in FIELDS_BY_SECTION:
        lines.append(f"# --- {section} ---")
        for f in fields:
            lines.append(f"{f.key}={new_values.get(f.key, f.default)}")
        lines.append("")
    leftover = {k: v for k, v in new_values.items() if k not in FIELDS_BY_KEY}
    if leftover:
        lines.append("# --- Other / custom variables ---")
        for k, v in leftover.items():
            lines.append(f"{k}={v}")
    _write_env_text("\n".join(lines))
    return applied, unknown


# ---------------------------------------------------------------------------
# Bot container control (Docker socket, optional)
# ---------------------------------------------------------------------------
def _get_bot_container():
    client = docker_sdk.from_env()
    return client.containers.get(BOT_CONTAINER_NAME)


def _restart_bot_container():
    if docker_sdk is None:
        return False, "docker SDK isn't available in this image -- restart manually with `docker compose restart bot`."
    try:
        _get_bot_container().restart()
        return True, f"Restarted container '{BOT_CONTAINER_NAME}'."
    except Exception as e:
        return False, f"Could not restart '{BOT_CONTAINER_NAME}': {e}. Restart it manually with `docker compose restart bot`."


def _hot_reload_bot_container():
    if docker_sdk is None:
        return False, "Settings saved, but hot reload needs the Docker socket mount -- restart the bot manually with `docker compose restart bot` to apply."
    try:
        _get_bot_container().kill(signal="SIGHUP")
        return True, "Settings saved and hot-reloaded -- no restart needed."
    except Exception as e:
        return False, f"Settings saved, but the hot-reload signal failed: {e}. Restart the bot manually with `docker compose restart bot` to apply."


def _confidence_hex(level: int) -> str:
    r, g, b = CONFIDENCE_COLORS.get(level, (150, 150, 150))
    return f"#{r:02x}{g:02x}{b:02x}"


def _sources_str(sources) -> str:
    return ", ".join(dict.fromkeys(sources)) if sources else "n/a"


# _primary_strategy_label is now defined once, in core/performance.py (as
# primary_strategy_label), and imported above under this same historical
# name -- the admin Performance page (get_chart_data / get_detailed_stats)
# needed the exact same "real confirming method, not the fixed placeholder
# t['strategy']" logic this dashboard helper already had, so it moved to
# the shared core layer instead of being duplicated a second time there.

# ---------------------------------------------------------------------------
# Version tracking (sidebar)
# ---------------------------------------------------------------------------
_DEFAULT_VERSIONS = {"ui": "0.0.0", "bot": "0.0.0"}


def get_versions() -> dict:
    """
    Reads {"ui": "x.y.z", "bot": "x.y.z"} from VERSION.json at the project
    root. Falls back to "0.0.0" for either/both fields if the file is
    missing, unreadable, or malformed -- the sidebar should always be able
    to render something rather than error the whole page out over a
    version display.

    Also includes "last_updated" -- VERSION.json's own last-modified time,
    formatted for display. Since this file is bumped by 0.0.1 every time a
    real code change is made (the whole point of it being a version file),
    its mtime doubles as "when was this container's image last actually
    changed" -- there's no separate build-timestamp artifact baked into the
    image to read instead, and this needs no extra plumbing to keep in sync.
    None if the file doesn't exist yet or its mtime can't be read.
    """
    if not os.path.exists(VERSION_PATH):
        return {**_DEFAULT_VERSIONS, "last_updated": None}
    try:
        with open(VERSION_PATH, "r") as f:
            data = json.load(f)
        versions = {
            "ui": str(data.get("ui", _DEFAULT_VERSIONS["ui"])),
            "bot": str(data.get("bot", _DEFAULT_VERSIONS["bot"])),
        }
    except (OSError, json.JSONDecodeError, AttributeError):
        versions = dict(_DEFAULT_VERSIONS)
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(VERSION_PATH), tz=timezone.utc)
        versions["last_updated"] = mtime.strftime("%Y-%m-%d %H:%M UTC")
    except OSError:
        versions["last_updated"] = None
    return versions


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------
def _tail_log(n: int = 500) -> str:
    if not os.path.exists(config.LOG_FILE):
        return "(no log file yet -- nothing has been logged since this file was created)"
    try:
        with open(config.LOG_FILE, "r", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:]) if lines else "(log file is empty)"
    except Exception as e:
        return f"(could not read log file: {e})"


def _tail_admin_log(n: int = 500) -> str:
    if not os.path.exists(config.ADMIN_LOG_FILE):
        return "(no admin log yet — admin UI activity will appear here after the next page interaction)"
    try:
        with open(config.ADMIN_LOG_FILE, "r", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:]) if lines else "(admin log file is empty)"
    except Exception as e:
        return f"(could not read admin log file: {e})"


def _clear_log() -> tuple:
    if not os.path.exists(config.LOG_FILE):
        return False, "Log file doesn't exist yet."
    try:
        with open(config.LOG_FILE, "w") as f:
            f.write("")
        return True, "Log file cleared."
    except Exception as e:
        return False, f"Could not clear log file: {e}"


def _clear_admin_log() -> tuple:
    if not os.path.exists(config.ADMIN_LOG_FILE):
        return False, "Admin log file doesn't exist yet."
    try:
        with open(config.ADMIN_LOG_FILE, "w") as f:
            f.write("")
        return True, "Admin log file cleared."
    except Exception as e:
        return False, f"Could not clear admin log file: {e}"
