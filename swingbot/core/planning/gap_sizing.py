"""v183 Part A: the one sizing path for plans and paper trades.

Every site that turns a plan or a paper trade into a share count calls
size_for / size_for_plan / size_for_trade, never compute_position_size
directly (stop_scope.risk_sizing_ok excepted: it runs before the stamp
exists, and a gap cut only lowers shares). The rule in force and the p99
up-gap are stamped on a SHORT plan once, at live creation, from completed
bars; every reader uses that stamp, so a later switch flip or a missing
frame never re-sizes an alerted plan differently. A long never reaches the
gap branch. Sizing and display only -- no filter, score or gate reads this.
"""
from __future__ import annotations

import logging

from swingbot import config
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.planning import account

log = logging.getLogger(__name__)

RULE_GAP = "gap_p99"
RULE_STOP = "stop"
MIN_UP_GAPS = 60
LOOKBACK = 250
_NO_GAP = {"gap_risk_amount": None, "gap_sized": False, "gap_floor_pct": None}


def _rule() -> str:
    return RULE_GAP if config.SHORT_GAP_SIZING else RULE_STOP


def gap_sizing_stamp(df, direction: str) -> dict | None:
    """The stamp for a plan created now from `df` (completed bars only); None for a long."""
    if direction != "bearish":
        return None
    from swingbot.core.edge.gates import gap_stats
    stats = gap_stats(df, lookback=LOOKBACK)
    n_up = int(stats["n_up"])
    p99 = stats["p99_up_gap_pct"] if n_up >= MIN_UP_GAPS else None
    return {"rule": _rule(), "up_gap_p99_pct": p99, "n_up_gaps": n_up}


def stamp_gap_sizing(plan, df) -> None:
    """Set plan.gap_sizing; never raises. A short without a usable p99 logs one line."""
    try:
        plan.gap_sizing = gap_sizing_stamp(df, plan.direction)
    except Exception as exc:
        plan.gap_sizing = ({"rule": _rule(), "up_gap_p99_pct": None, "n_up_gaps": 0}
                           if plan.direction == "bearish" else None)
        swallowed(log, "scan.gap_sizing.stamp", exc,
                  "%s: gap sizing stamp failed (%s) -- sized on the stop", plan.ticker, exc,
                  level=logging.INFO)
        return
    if plan.gap_sizing is not None and plan.gap_sizing["up_gap_p99_pct"] is None:
        log.info("%s: gap sizing p99 n/a (%d up-gaps, need %d) -- sized on the stop",
                 plan.ticker, plan.gap_sizing["n_up_gaps"], MIN_UP_GAPS)


def gap_floor_for(direction: str | None, gap_sizing: dict | None) -> float | None:
    """The p99 floor (percent) to size on, or None: long, no stamp, rule stop, no p99."""
    if direction != "bearish" or not gap_sizing or gap_sizing.get("rule") != RULE_GAP:
        return None
    p99 = gap_sizing.get("up_gap_p99_pct")
    return float(p99) if p99 is not None and p99 > 0 else None


def _stop_only(entry, stop_loss, account_cfg, label=""):
    # Preserve positional call shapes when there is no ticker to report.
    kwargs = {"ticker": label} if label else {}
    if account_cfg is None:
        return account.compute_position_size(entry, stop_loss, **kwargs)
    return account.compute_position_size(entry, stop_loss, account_cfg, **kwargs)


def _with_no_gap(result):
    return None if result is None else {**result, **_NO_GAP}


def size_for(entry, stop_loss, *, direction, gap_sizing, account_cfg=None, label: str = "") -> dict | None:
    """The share count for one plan or trade under its stamped rule."""
    if direction != "bearish" or (gap_sizing or {}).get("rule") == RULE_STOP:
        return _stop_only(entry, stop_loss, account_cfg, label)
    floor = gap_floor_for(direction, gap_sizing)
    if floor is None:
        return _with_no_gap(_stop_only(entry, stop_loss, account_cfg, label))
    try:
        kwargs = {"ticker": label} if label else {}
        return account.compute_position_size(entry, stop_loss, account_cfg, gap_floor_pct=floor, **kwargs)
    except Exception as exc:
        swallowed(log, "scan.gap_sizing.size_fallback", exc,
                  "%s: gap sizing fell back to stop (%s)", label, exc, level=logging.INFO)
        return _with_no_gap(_stop_only(entry, stop_loss, account_cfg, label))


def size_for_plan(plan, entry=None, account_cfg=None) -> dict | None:
    price = entry if entry is not None else (plan.trigger_price or plan.entry_price)
    return size_for(price, plan.stop_loss, direction=getattr(plan, "direction", None),
                    gap_sizing=getattr(plan, "gap_sizing", None), account_cfg=account_cfg,
                    label=getattr(plan, "ticker", ""))


def size_for_trade(trade: dict, entry=None, account_cfg=None) -> dict | None:
    price = entry if entry is not None else trade.get("entry")
    return size_for(price, trade.get("stop_loss"), direction=trade.get("direction"),
                    gap_sizing=trade.get("gap_sizing"), account_cfg=account_cfg,
                    label=trade.get("ticker", ""))


def gap_risk_amount_for(shares, entry, stop_loss, gap_sizing) -> float | None:
    """What a p99 gap would cost an open short of `shares`; None without a usable p99."""
    floor = gap_floor_for("bearish", gap_sizing)
    if floor is None or shares is None or entry is None or stop_loss is None:
        return None
    distance = account._sizing_distance(float(entry), abs(float(entry) - float(stop_loss)), floor)
    return round(float(shares) * distance, 2)
