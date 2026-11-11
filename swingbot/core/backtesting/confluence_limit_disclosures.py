"""v212 disclosures (spec § Pass rule, Disclosures): figures printed beside
the verdict and never read by a gate. One cell at a time; the measure script
(V212-14c) collects the cells and the touch-fill sensitivity, and
`render_disclosures` (V212-14b) prints them as Markdown for the results doc."""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from swingbot.core.backtesting.acceptance import CLOSED, DECIDED

RISK_DOLLARS = 100.0                       # dollar P&L is quoted per $100 of fixed risk
ATR_EDGES = (2.0, 3.0, 4.5)                # ATR14 as % of the signal close
ATR_LABELS = ("<2%", "2-3%", "3-4.5%", ">=4.5%")
SPY_DOWN_PCT = -1.0                        # SPY close below prior close - 1%
DIRECTIONS = ("bullish", "bearish")


def _mean(values) -> float | None:
    return float(np.mean(values)) if values else None


def _share(part, whole) -> float | None:
    return part / whole if whole else None


def _day(value) -> str:
    return str(value or "")[:10]


def _closed(rows) -> list:
    return [r for r in rows if r.get("filled") and r.get("outcome") in CLOSED
            and r.get("r_net") is not None]


def _alert_r(r) -> float:
    return float(r["r_net"]) if _closed([r]) else 0.0


def _stats(rows) -> dict:
    """n, ExpR and WR (percent of decided) -- acceptance.expectancy_r / win_rate."""
    closed = _closed(rows)
    decided = [r for r in closed if r["outcome"] in DECIDED]
    wins = sum(r["outcome"] == "win" for r in decided)
    return {"n": len(closed), "expr": _mean([r["r_net"] for r in closed]),
            "wr": 100.0 * wins / len(decided) if decided else None}


def scope_counts(census_rows, cell) -> dict:
    """Scope, drops, the D range the cell reaches, and how often the TP1
    cancel or the expiry bound (census, outcome-blind)."""
    in_scope = [r for r in census_rows if cell in (r.get("drops") or {})]
    kept = [r for r in in_scope if r["drops"][cell] is None]
    ds = [r["d_pct"] for r in kept]
    states = Counter(r["fill_state"][cell] for r in kept)
    return {"in_scope": len(in_scope), "kept": len(kept),
            "drops": dict(Counter(r["drops"][cell] for r in in_scope if r["drops"][cell])),
            "d_range": [min(ds), max(ds)] if ds else None, "fill_states": dict(states),
            "tp1_cancel_share": _share(states["tp1_cancel"], len(kept)),
            "expiry_share": _share(states["expired"], len(kept))}


def alert_volume_per_day(census_rows, arm_rows) -> float:
    """Orders the cell would send per trading day: its non-dropped alerts over
    the weekdays from the first to the last census signal date, inclusive."""
    dates = sorted({_day(r["entry_date"]) for r in census_rows if r.get("entry_date")})
    if not dates:
        return 0.0
    end = np.datetime64(dates[-1]) + np.timedelta64(1, "D")
    days = int(np.busday_count(np.datetime64(dates[0]), end))
    sent = len({r["key"] for r in arm_rows if r.get("dropped") is None})
    return sent / days if days else 0.0


def paired_delta(arm_rows, ref_rows) -> dict:
    """Per in-scope alert: arm R (0 when dropped or unfilled) minus reference R."""
    arm, ref = {r["key"]: r for r in arm_rows}, {r["key"]: r for r in ref_rows}
    keys = sorted(arm.keys() & ref.keys())
    arm_r = [_alert_r(arm[k]) for k in keys]
    ref_r = [_alert_r(ref[k]) for k in keys]
    deltas = [a - b for a, b in zip(arm_r, ref_r)]
    return {"alerts": len(keys), "mean_delta_r": _mean(deltas),
            "share_positive": _share(sum(x > 0 for x in deltas), len(deltas)),
            "dollar_per_alert_arm": RISK_DOLLARS * _mean(arm_r) if keys else None,
            "dollar_per_alert_ref": RISK_DOLLARS * _mean(ref_r) if keys else None}


def filled_dollars(arm_rows) -> dict:
    """Dollar P&L at fixed risk on filled trades only."""
    rs = [r["r_net"] for r in _closed(arm_rows)]
    return {"fills": len(rs), "total": RISK_DOLLARS * sum(rs),
            "per_fill": RISK_DOLLARS * _mean(rs) if rs else None}


def _effective_stop_pct(fills) -> float | None:
    return _mean([abs(r["market"] - r["stop_loss"]) / r["market"] * 100.0
                  for r in fills if r.get("market")])


def _gap_stops(fills) -> dict:
    gaps = [r for r in fills if r.get("gap_stopped")]
    rs = [r["r_net"] for r in gaps]
    from_l = [r["gap_stop_r_from_limit"] for r in gaps
              if r.get("gap_stop_r_from_limit") is not None]
    per_day = Counter(_day(r["fill_date"]) for r in gaps)
    return {"gap_stops": len(gaps), "gap_stop_mean_r": _mean(rs),
            "gap_stop_worst_r": min(rs, default=None),
            "gap_stop_mean_r_from_limit": _mean(from_l),
            "gap_stop_worst_r_from_limit": min(from_l, default=None),
            "gap_stop_max_per_day": max(per_day.values(), default=0)}


def adverse(arm_rows) -> dict:
    """v131's adverse-selection diagnostics, the effective stop from M, the
    stop-run share and the gap-through-stop fills."""
    fills = _closed(arm_rows)
    losses = [r for r in fills if r["outcome"] == "loss"]
    return {"fills": len(fills), "effective_stop_from_m_pct": _effective_stop_pct(fills),
            "early_stop_share": _share(sum(bool(r.get("early_stop")) for r in fills), len(fills)),
            "wick_through_share": _share(sum(bool(r.get("wick_through")) for r in losses),
                                         len(losses)),
            **_gap_stops(fills)}


def _atr_bucket(atr) -> str:
    if atr is None:
        return "unknown"
    return ATR_LABELS[int(np.searchsorted(ATR_EDGES, float(atr), side="right"))]


def by_atr(arm_rows) -> list:
    groups = defaultdict(list)
    for r in arm_rows:
        if r.get("dropped") is None:
            groups[_atr_bucket(r.get("atr14_pct"))].append(r)
    out = []
    for label in (*ATR_LABELS, "unknown"):
        rows = groups.get(label)
        if rows:
            fills = len(_closed(rows))
            out.append({"bucket": label, "alerts": len(rows), "fills": fills,
                        "fill_rate": _share(fills, len(rows)), "expr": _stats(rows)["expr"]})
    return out


def spy_changes(frame) -> dict:
    """ISO date -> SPY close-to-close change in percent (the first bar has none)."""
    pct = frame["Close"].astype(float).pct_change() * 100.0
    return {idx.date().isoformat(): float(v) for idx, v in pct.dropna().items()}


def spy_days(arm_rows, spy) -> dict:
    fills = _closed(arm_rows)
    is_down = [spy.get(_day(r["fill_date"]), 0.0) < SPY_DOWN_PCT for r in fills]
    return {"down": _stats([r for r, down in zip(fills, is_down) if down]),
            "other": _stats([r for r, down in zip(fills, is_down) if not down]),
            "distinct_fill_days": len({_day(r["fill_date"]) for r in fills}),
            "spy_missing": sum(_day(r["fill_date"]) not in spy for r in fills)}


def _in_window(r, earnings) -> bool:
    """A report after the signal date and on or before the limit's expiry."""
    start, end = _day(r["entry_date"]), _day(r.get("expiry_date"))
    return bool(end) and any(start < day <= end for day in earnings.get(r["ticker"], ()))


def earnings_share(arm_rows, earnings) -> dict:
    fills = _closed(arm_rows)
    hits = sum(_in_window(r, earnings) for r in fills)
    return {"fills": len(fills), "with_earnings": hits, "share": _share(hits, len(fills)),
            "tickers_without_calendar": len({r["ticker"] for r in fills} - set(earnings))}
