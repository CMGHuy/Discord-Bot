"""
Pure helper functions for the admin web UI -- .env <-> structured
settings-field conversion, Docker bot-container control (restart/hot
reload), confidence-color formatting, and log-file tailing/clearing.
None of these touch the Flask `app` object or a route decorator, so
they're split out of app.py into their own module rather than adding to
that file's already-long list of routes; app.py imports every one of
these back and calls them exactly as before.
"""
import json
import os
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
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            backup = f.read()
        with open(ENV_PATH + ".bak", "w") as f:
            f.write(backup)
    with open(ENV_PATH, "w") as f:
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
    """
    if not os.path.exists(VERSION_PATH):
        return dict(_DEFAULT_VERSIONS)
    try:
        with open(VERSION_PATH, "r") as f:
            data = json.load(f)
        return {
            "ui": str(data.get("ui", _DEFAULT_VERSIONS["ui"])),
            "bot": str(data.get("bot", _DEFAULT_VERSIONS["bot"])),
        }
    except (OSError, json.JSONDecodeError, AttributeError):
        return dict(_DEFAULT_VERSIONS)


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
