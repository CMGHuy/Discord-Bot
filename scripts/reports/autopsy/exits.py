"""v161 TS6: autopsy exit cuts, give-back over every trade, stop-cell extras and
the alert-supply tallies (alerts per day, alert hour against the session,
issued-before-the-open, rejected-plan reasons).

The exit bucket is the live book's own rule (``metrics._exit_reason_bucket``),
so the autopsy and ``/stats`` speak one vocabulary."""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from swingbot.core.analytics.metrics import _exit_reason_bucket

from .cells import Tally

STOP_CUTS = frozenset({"exit_reason", "gap_through_stop", "near_stop_reversal"})
STOP_REASONS = frozenset({"loss", "stop"})
RISK_FRACTION = 0.02          # the fixed 2% dollar risk the dollar view is priced at
GAP_THROUGH_R = -1.0          # a stop exit below this (rounded to 0.01 R) gapped through
HOLDING_EDGES = ((2, "le_2d"), (5, "3_5d"), (10, "6_10d"))
HOLDING_TOP = "gt_10d"
ALERTS_PER_DAY_EDGES = ((1, "1"), (3, "2_3"), (6, "4_6"))
ALERTS_PER_DAY_TOP = "7_plus"
REGULAR_OPEN_HOUR = 9         # hour granularity: 09:00-09:29 counts as regular
REGULAR_CLOSE_HOUR = 16
SESSIONS = ("premarket", "regular", "after_close", "unknown")
_NEAR_TP = {"auto (near-tp stall)": "near_tp_stall", "auto (near-tp timeout)": "near_tp_timeout"}


def _reason(row) -> str:
    return (row.close_reason or "").strip().lower()


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def is_stop_exit(row) -> bool:
    """A stop exit: the v2 leg reason ``loss`` (bucket ``stop``), or a legacy
    price-monitor close that lost. Same rule as ``bars._stopped_out``."""
    reason = (row.close_reason or "").lower()
    if reason in STOP_REASONS:
        return True
    return reason.startswith("auto (price monitor)") and row.outcome == "loss"


def _exit_reason(row) -> str | None:
    return _exit_reason_bucket({"close_reason": row.close_reason or ""})


def _near_tp_close(row) -> str | None:
    return _NEAR_TP.get(_reason(row), "other_exit")


def _gap_through_stop(row) -> str | None:
    if row.gross_r is None or not is_stop_exit(row):
        return None
    return "through_stop" if round(row.gross_r, 2) < GAP_THROUGH_R else "at_stop"


def _holding_bucket(row) -> str | None:
    if row.holding_days is None or not row.horizon:
        return None
    for edge, label in HOLDING_EDGES:
        if row.holding_days <= edge:
            return f"{row.horizon}|{label}"
    return f"{row.horizon}|{HOLDING_TOP}"


def exit_cuts() -> tuple:
    """The four exit cuts, in ledger order: (name, key) pairs for ``cells.cut_cells``."""
    return (("exit_reason", _exit_reason), ("near_tp_close", _near_tp_close),
            ("gap_through_stop", _gap_through_stop), ("holding_bucket", _holding_bucket))


def _overshoots(members: list) -> list[float]:
    return [GAP_THROUGH_R - r.gross_r for r in members
            if _gap_through_stop(r) == "through_stop"]


def stop_extra(members: list, balance: float) -> dict:
    """Stop distance in ATR, mean dollar loss at fixed 2% risk, and the gap past -1 R."""
    widths = [r.stop_width_atr for r in members if r.stop_width_atr is not None]
    losses = [r.net_r for r in members if r.net_r is not None and r.net_r < 0]
    loss = _mean(losses)
    return {"mean_stop_atr": _mean(widths),
            "dollar_loss_at_2pct": None if loss is None else round(-loss * RISK_FRACTION * balance, 2),
            "mean_overshoot_r": _mean(_overshoots(members))}


def giveback_summary(trades: list) -> dict:
    """``mfe_r - gross_r`` over every trade that has both -- losers included."""
    values = [r.mfe_r - r.gross_r for r in trades if r.mfe_r is not None and r.gross_r is not None]
    if not values:
        return {"n": 0, "mean": None, "median": None}
    return {"n": len(values), "mean": _mean(values),
            "median": round(statistics.median(values), 4)}


def _per_day_label(n: int) -> str:
    for edge, label in ALERTS_PER_DAY_EDGES:
        if n <= edge:
            return label
    return ALERTS_PER_DAY_TOP


def _alerts_per_day(issued: list) -> list[Tally]:
    per_day = Counter(str(r.plan_date)[:10] for r in issued)
    days: Counter = Counter()
    plans: Counter = Counter()
    for n in per_day.values():
        label = _per_day_label(n)
        days[label] += 1
        plans[label] += n
    labels = [label for _, label in ALERTS_PER_DAY_EDGES] + [ALERTS_PER_DAY_TOP]
    return [Tally(id=f"alerts_per_day={lab}", cut="alerts_per_day", value=lab,
                  count=days[lab], extra={"plans": plans[lab]}) for lab in labels]


def _session_of(hour: int | None) -> str:
    if hour is None:
        return "unknown"
    if hour < REGULAR_OPEN_HOUR:
        return "premarket"
    return "regular" if hour < REGULAR_CLOSE_HOUR else "after_close"


def _hour_tallies(issued: list) -> list[Tally]:
    sessions = Counter(_session_of(r.plan_hour) for r in issued)
    out = [Tally(id=f"alert_hour_session={s}", cut="alert_hour_session", value=s,
                 count=sessions[s]) for s in SESSIONS]
    before = {"yes": sessions["premarket"] + sessions["after_close"],
              "no": sessions["regular"], "unknown": sessions["unknown"]}
    out += [Tally(id=f"actionable_before_open={k}", cut="actionable_before_open", value=k,
                  count=v) for k, v in before.items()]
    return out


def _rejection_tallies(rejections: list) -> list[Tally]:
    counts: Counter = Counter()
    days: defaultdict = defaultdict(set)
    for rej in rejections:
        reason = rej.reason.replace(";", ",")
        counts[reason] += rej.count
        days[reason].add(rej.date)
    ordered = sorted(counts, key=lambda r: (-counts[r], r))
    return [Tally(id=f"rejection_reason={r}", cut="rejection_reason", value=r,
                  count=counts[r], extra={"days": len(days[r])}) for r in ordered]


def alert_supply_tallies(rows: list, rejections: list) -> list[Tally]:
    """Alerts per day, alert hour against the session, issued-before-the-open, rejections."""
    issued = [r for r in rows if r.plan_date]
    return _alerts_per_day(issued) + _hour_tallies(issued) + _rejection_tallies(rejections)
