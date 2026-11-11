"""v212 disclosures (spec § Pass rule, Disclosures): figures printed beside
the verdict and never read by a gate. One cell at a time; the measure script
(V212-14c) collects the cells and the touch-fill sensitivity, and
`render_disclosures` (V212-14b) prints them as Markdown for the results doc."""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from swingbot import config
from swingbot.core.analytics.risk_metrics import max_drawdown_r
from swingbot.core.backtesting.acceptance import CLOSED, DECIDED
from swingbot.core.edge import ruin

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


# --- portfolio pass, risk and ruin --------------------------------------------

CAP_REASONS = ("heat", "sector", "cluster", "max_open")
RUIN_RUNS = {"n_trades": 1000, "n_paths": 2000, "seed": 42}


def cap_skips(result) -> dict:
    """The portfolio pass's notional cuts and the fills a cap cancelled at
    fill (heat, sector, cluster, max open -- spec rule 8)."""
    reasons = dict(result.get("skip_reasons") or {})
    submitted = result.get("trades_taken", 0) + result.get("trades_skipped", 0)
    capped = result.get("notional_capped", 0)
    return {"submitted": submitted, "taken": result.get("trades_taken", 0),
            "notional_capped": capped, "notional_capped_share": _share(capped, submitted),
            "heat_at_fill": sum(reasons.get(k, 0) for k in CAP_REASONS),
            "skip_reasons": reasons, "max_dd_pct": result.get("max_dd_pct")}


def per_direction(arm, ref) -> list:
    return [{"direction": d, "arm": _stats([r for r in arm if r["direction"] == d]),
             "ref": _stats([r for r in ref if r["direction"] == d])} for d in DIRECTIONS]


def _max_open(rows) -> int:
    """Most positions open at one open: filled on or before the day and
    exiting on or after it."""
    spans = [(_day(r["fill_date"]), _day(r["exit_date"])) for r in rows]
    return max((sum(f <= day <= e for f, e in spans) for day, _ in spans), default=0)


def risk_and_ruin(kept, risk_pct) -> dict:
    closed = sorted(_closed(kept), key=lambda r: (_day(r["exit_date"]), r["key"]))
    rs = [float(r["r_net"]) for r in closed]
    by_day = defaultdict(float)
    for r in closed:
        by_day[_day(r["exit_date"])] += float(r["r_net"])
    sim = ruin.simulate(rs, risk_pct=risk_pct, **RUIN_RUNS) if rs else {}
    most = _max_open(closed)
    return {"n": len(rs), "worst_day_r": min(by_day.values(), default=None),
            "max_open_positions": most, "max_open_risk_pct": most * risk_pct,
            "max_drawdown_r": max_drawdown_r(rs), "p_ruin": sim.get("p_ruin"),
            "max_dd_p95": sim.get("max_dd_p95")}


def disclosures(arm_rows, ref_rows, census_rows, *, spy, earnings, portfolio) -> dict:
    """Every spec disclosure for one cell. Printed, never gating."""
    risk_pct = float(getattr(config, "RISK_PER_TRADE_PCT", 1.0))
    cell = next((r["arm"] for r in arm_rows), None)
    sides = ("arm", "ref")
    return {"cell": cell, "scope": scope_counts(census_rows, cell),
            "alert_volume_per_day": alert_volume_per_day(census_rows, arm_rows),
            "paired": paired_delta(arm_rows, ref_rows), "filled_dollars": filled_dollars(arm_rows),
            "adverse": adverse(arm_rows), "atr": by_atr(arm_rows),
            "spy": spy_days(arm_rows, spy), "earnings": earnings_share(arm_rows, earnings),
            "portfolio": {s: cap_skips(portfolio.get(f"{s}_result") or {}) for s in sides},
            "per_direction": per_direction(portfolio.get("arm", []), portfolio.get("ref", [])),
            "risk": {s: risk_and_ruin(portfolio.get(s, []), risk_pct) for s in sides}}


# --- render ----------------------------------------------------------------------

RISK_ROWS = (("Worst day R", "worst_day_r", "+.3f"),
             ("Max open positions", "max_open_positions", "d"),
             ("Max open risk % (upper bound: notional cuts carry less)", "max_open_risk_pct", ".2f"),
             ("Max drawdown R", "max_drawdown_r", ".3f"), ("P(ruin)", "p_ruin", ".4f"),
             ("Drawdown p95 (bootstrap)", "max_dd_p95", ".3f"))


def _f(value, spec=".3f", suffix="") -> str:
    return "n/a" if value is None else f"{value:{spec}}{suffix}"


def _pct(share) -> str:
    return "n/a" if share is None else f"{100.0 * share:.1f}%"


def _table(header, rows) -> list:
    return ["", "| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(row) + " |" for row in rows)]


def _render_head(d) -> list:
    s, p, fd = d["scope"], d["paired"], d["filled_dollars"]
    lo_hi = "n/a" if s["d_range"] is None else f"{s['d_range'][0]:.2f}%-{s['d_range'][1]:.2f}%"
    risk = f"${RISK_DOLLARS:.0f}"
    return [f"### Cell {d['cell']}", "",
            f"- Scope: {s['in_scope']} in scope, drops {s['drops'] or 'none'}, {s['kept']} kept;"
            f" D range {lo_hi}",
            f"- Alert volume: {d['alert_volume_per_day']:.2f} orders per trading day",
            f"- Paired per-alert ΔR (unfilled and dropped = 0R): mean "
            f"{_f(p['mean_delta_r'], '+.3f')} over {p['alerts']} alerts, "
            f"{_pct(p['share_positive'])} positive",
            f"- Dollar P&L per alert at {risk} risk: arm {_f(p['dollar_per_alert_arm'], '+.2f')},"
            f" reference {_f(p['dollar_per_alert_ref'], '+.2f')}",
            f"- Filled trades at {risk} fixed risk: {fd['fills']} fills, total "
            f"{_f(fd['total'], '+.2f')}, per fill {_f(fd['per_fill'], '+.2f')}"]


def _render_adverse(d) -> list:
    a, s, e = d["adverse"], d["scope"], d["earnings"]
    return [f"- Effective stop from M on fills: {_f(a['effective_stop_from_m_pct'], '.2f', '%')};"
            f" stopped within 3 bars: {_pct(a['early_stop_share'])}; TP1 cancel binds "
            f"{_pct(s['tp1_cancel_share'])}, expiry binds {_pct(s['expiry_share'])}",
            f"- Gap-through-stop fills: {a['gap_stops']}, mean R {_f(a['gap_stop_mean_r'], '+.3f')},"
            f" worst R {_f(a['gap_stop_worst_r'], '+.3f')}; from L (pessimistic): mean "
            f"{_f(a['gap_stop_mean_r_from_limit'], '+.3f')}, worst "
            f"{_f(a['gap_stop_worst_r_from_limit'], '+.3f')}; most on one day "
            f"{a['gap_stop_max_per_day']}",
            f"- Stop-run: {_pct(a['wick_through_share'])} of stopped fills wicked through and "
            "closed back (never grounds to widen the buffer)",
            f"- Earnings inside the 3-bar window: {e['with_earnings']} of {e['fills']} fills "
            f"({_pct(e['share'])}); {e['tickers_without_calendar']} tickers without a calendar"]


def _render_caps(d) -> list:
    lines = []
    for side, label in (("arm", "arm"), ("ref", "reference")):
        c = d["portfolio"][side]
        reasons = ", ".join(f"{k} {c['skip_reasons'].get(k, 0)}" for k in CAP_REASONS)
        lines.append(f"- Notional cap cut ({label}): {c['notional_capped']} of {c['submitted']}"
                     f" ({_pct(c['notional_capped_share'])}); cancelled at fill by caps: "
                     f"{c['heat_at_fill']} ({reasons})")
    return lines


def _stat_cells(st) -> tuple:
    return str(st["n"]), _f(st["expr"], "+.3f"), _f(st["wr"], ".1f")


def _render_tables(d) -> list:
    atr = [(b["bucket"], str(b["alerts"]), str(b["fills"]), _pct(b["fill_rate"]),
            _f(b["expr"], "+.3f")) for b in d["atr"]]
    spy = [(name, *_stat_cells(d["spy"][key]))
           for key, name in (("down", "SPY down day (< -1%)"), ("other", "other days"))]
    dirs = [(x["direction"], *_stat_cells(x["arm"]), *_stat_cells(x["ref"]))
            for x in d["per_direction"]]
    return [*_table(("ATR14%", "alerts", "fills", "fill rate", "ExpR"), atr),
            *_table(("SPY day", "fills", "ExpR", "WR"), spy), "",
            f"Distinct fill days: {d['spy']['distinct_fill_days']} "
            f"(SPY missing on {d['spy']['spy_missing']} fills)",
            *_table(("direction", "arm n", "arm ExpR", "arm WR", "ref n", "ref ExpR", "ref WR"),
                    dirs)]


def _render_risk(d) -> list:
    arm, ref = d["risk"]["arm"], d["risk"]["ref"]
    rows = [(label, _f(arm[key], spec), _f(ref[key], spec)) for label, key, spec in RISK_ROWS]
    return _table(("risk and ruin", "arm", "reference"), rows)


def _render_touch(touch) -> list:
    rows = [(t["cell"], str(t["n"]), str(t["ref_n"]), _f(t["expr"], "+.3f"),
             _f(t["ref_expr"], "+.3f"), _f(t["wr"], ".1f"), _f(t["ref_wr"], ".1f"),
             "yes" if t["passes"] else "no") for t in touch]
    return ["", "### Touch-fill sensitivity (same clauses, never gating)",
            *_table(("cell", "n", "ref n", "ExpR", "ref ExpR", "WR", "ref WR", "passes"), rows)]


def render_disclosures(d: dict) -> str:
    """Markdown for the results doc: one cell's dict, or the stage blob."""
    blob = d if "cells" in d else {"cells": [d]}
    lines = [f"## Disclosures ({blob.get('window', 'window not named')}; printed, never gating)",
             ""]
    for cell in blob["cells"]:
        lines += [*_render_head(cell), *_render_adverse(cell), *_render_caps(cell),
                  *_render_tables(cell), *_render_risk(cell), ""]
    if blob.get("touch"):
        lines += _render_touch(blob["touch"])
    return "\n".join(lines) + "\n"
