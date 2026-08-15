"""What would each sizing mode have done with the SAME trades?
Run: python scripts/sizing_shadow_report.py"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _walk(trades, risk_key):
    bal, peak, max_dd = 1.0, 1.0, 0.0
    for t in trades:
        risk = (t["shadow_sizing"].get(risk_key) if risk_key != "actual"
                else t.get("risk_pct")) or 0.0
        bal *= 1 + risk / 100.0 * t["r_multiple"]
        peak = max(peak, bal)
        max_dd = max(max_dd, (peak - bal) / peak * 100.0)
    return {"multiple": bal, "max_dd_pct": round(max_dd, 2)}


def sizing_shadow_report(trades: list) -> dict:
    trades = [t for t in trades if t.get("shadow_sizing") and t.get("r_multiple") is not None]
    return {mode: _walk(trades, mode)
            for mode in ("actual", "kelly", "vol_target", "min_of_all")}


if __name__ == "__main__":
    # TradeLog has no all_trades() -- get_trades(limit=None) is the real
    # unbounded accessor (its default limit is 20). Real trade records also
    # don't carry an "r_multiple" key (that's computed on demand, one shared
    # definition in analytics.metrics.r_multiple) -- attached here rather
    # than fabricated on the record. NOTE: per-trade "actual" risk_pct isn't
    # persisted on trade records either (only shares/position_value are), so
    # the "actual" column falls back to 0 via _walk's `or 0.0` -- a real,
    # disclosed gap, not a silently wrong number.
    from swingbot.core.analytics.metrics import r_multiple as _r_multiple
    from swingbot.core.performance import TradeLog

    trades = TradeLog().get_trades(limit=None)
    for t in trades:
        t["r_multiple"] = _r_multiple(t)
    print(json.dumps(sizing_shadow_report(trades), indent=1))
