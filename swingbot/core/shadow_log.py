"""Shadow-mode plan log: one JSONL line per scan item comparing the v2 plan
against the legacy scenario numbers it would replace. Read by
scripts/shadow_parity_report.py; the cutover decision (Task 88) is made on
this file's evidence."""
import json
import os
from datetime import datetime, timezone

from swingbot import config
from swingbot.core.plan_engine import plan_to_dict

MAX_BYTES = 50 * 1024 * 1024


def _default_path() -> str:
    return os.path.join(config.DATA_DIR, "shadow_plans.jsonl")


def append(plan, legacy_scenario_summary: dict, path: str | None = None,
           component: str | None = None, variant: str | None = None) -> None:
    """`component`/`variant` (edge E40) tag a line as belonging to one side
    of a component's shadow forward-gate cohort. They are only written when
    supplied: scripts/shadow_parity_report.py already reads this file for
    the v2 cutover decision, and an untagged line has to stay byte-for-byte
    what it was."""
    path = path or _default_path()
    if os.path.exists(path) and os.path.getsize(path) >= MAX_BYTES:
        os.replace(path, path + ".1")            # single rotation slot
    record = {
        "ts_scan": datetime.now(timezone.utc).isoformat(),
        "ticker": plan.ticker,
        "horizon": plan.horizon_key,
        "plan": plan_to_dict(plan),
        "legacy": legacy_scenario_summary,
    }
    if component is not None:
        record["component"] = component
        record["variant"] = variant
        # Resolved later by backfill_forward_returns once 10 bars exist.
        record["fwd_return_10d"] = None
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")       # one write() call per line


def _forward_return(frame, scan_date, horizon_days: int) -> float | None:
    """Return over `horizon_days` TRADING bars from the first bar at or
    after `scan_date`. None while the window has not matured -- a partial
    window is not a shorter-horizon reading, it is no reading."""
    if frame is None or "Close" not in getattr(frame, "columns", []):
        return None
    positions = [i for i, d in enumerate(frame.index) if d.date() >= scan_date]
    if not positions:
        return None
    start = positions[0]
    end = start + horizon_days
    if end >= len(frame):
        return None
    entry = float(frame["Close"].iloc[start])
    if entry <= 0:
        return None
    return float(frame["Close"].iloc[end] / entry - 1.0)


def backfill_forward_returns(path: str | None = None, price_fn=None,
                             horizon_days: int = 10) -> int:
    """Fill `fwd_return_10d` on every tagged line whose window has matured.
    Returns how many lines were newly resolved.

    Edge E40 assumes this exists -- it did not. Its report compares the two
    cohorts' 10-day forward returns, so without this the gate could never
    reach a verdict other than HOLD, no matter how long the shadow window
    ran. `price_fn(ticker) -> DataFrame|None` is injectable; the default
    reads the same daily cache the rest of the scan uses.

    Rewrites the file in place via a temp file, so a crash mid-write cannot
    truncate the log the v2 cutover evidence also lives in.
    """
    path = path or _default_path()
    if not os.path.exists(path):
        return 0
    if price_fn is None:
        from swingbot.core.data import get_daily_data
        price_fn = get_daily_data

    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    frames, filled = {}, 0
    for row in rows:
        if row.get("component") is None or row.get("fwd_return_10d") is not None:
            continue
        ticker = row.get("ticker")
        if ticker not in frames:
            try:
                frames[ticker] = price_fn(ticker)
            except Exception:
                frames[ticker] = None
        try:
            scan_date = datetime.fromisoformat(row["ts_scan"]).date()
        except Exception:
            continue
        value = _forward_return(frames[ticker], scan_date, horizon_days)
        if value is not None:
            row["fwd_return_10d"] = value
            filled += 1

    if filled:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        os.replace(tmp, path)
    return filled
