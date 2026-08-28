"""Persisted scan-to-scan presentation snapshots."""
import json
import os
from datetime import datetime, timezone

from swingbot import config


_SNAPSHOT_PATH = os.path.join(config.DATA_DIR, "scan_snapshots.json")
def _load_scan_snapshots() -> dict:
    if not os.path.exists(_SNAPSHOT_PATH):
        return {}
    try:
        with open(_SNAPSHOT_PATH, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_scan_snapshots(data: dict) -> None:
    try:
        with open(_SNAPSHOT_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def _format_duration_hms(total_seconds: float) -> str:
    """Day/hour/minute holding-period label, e.g. "1 day 5 hours 32 minutes"
    -- mirrors admin/app.py's _format_duration_hms exactly (duplicated
    rather than imported since admin/ imports FROM core/, not the other way
    around, and this one small formatter isn't worth a shared-module
    detour for)."""
    total_seconds = max(0.0, total_seconds)
    total_minutes = int(total_seconds // 60)
    days, rem = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours or days:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return " ".join(parts)


def _snapshot_and_diff(item) -> str | None:
    """
    Compares this scenario's current entry/stop/target/confidence/R:R
    against the last time this exact ticker + horizon + direction combo was
    posted (by either `!check` or the automatic scan -- they share the same
    store), and returns a short "what changed" summary. Returns None the
    very first time a combo is seen (nothing to diff against yet) or when
    every tracked number is unchanged.

    Always writes the CURRENT numbers back to disk as the new "last seen"
    snapshot before returning, so the NEXT scan/`!check` of this same combo
    diffs against this one -- this call is the update, not just a read.
    """
    result, plan, conf = item.result, item.plan, item.conf
    key = f"{result.ticker}|{result.horizon_key}|{result.trend}"
    snapshots = _load_scan_snapshots()
    prev = snapshots.get(key)

    current = {
        "entry": plan.entry, "stop_loss": plan.stop_loss, "take_profit": plan.take_profit,
        "confidence_level": conf.level, "risk_reward_ratio": plan.risk_reward_ratio,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    snapshots[key] = current
    _save_scan_snapshots(snapshots)

    if prev is None:
        return None

    changes = []
    if abs(prev.get("entry", plan.entry) - plan.entry) > 1e-9:
        pct = ((plan.entry - prev["entry"]) / prev["entry"] * 100) if prev.get("entry") else 0
        changes.append(f"Entry {prev['entry']:.2f} → {plan.entry:.2f} ({pct:+.1f}%)")
    if abs(prev.get("stop_loss", plan.stop_loss) - plan.stop_loss) > 1e-9:
        changes.append(f"Stop {prev['stop_loss']:.2f} → {plan.stop_loss:.2f}")
    if abs(prev.get("take_profit", plan.take_profit) - plan.take_profit) > 1e-9:
        changes.append(f"Target {prev['take_profit']:.2f} → {plan.take_profit:.2f}")
    if prev.get("confidence_level") != conf.level:
        prev_level = prev.get("confidence_level", conf.level)
        arrow = "⬆️" if conf.level > prev_level else "⬇️"
        changes.append(f"Confidence Lv{prev_level} {arrow} Lv{conf.level}")
    if prev.get("risk_reward_ratio") != plan.risk_reward_ratio:
        changes.append(f"R:R {prev.get('risk_reward_ratio', '?')}:1 → {plan.risk_reward_ratio}:1")

    return " · ".join(changes) if changes else None


