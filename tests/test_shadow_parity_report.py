import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "spr", pathlib.Path("scripts/shadow_parity_report.py"))
spr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(spr)


def _rec(entry_v2, entry_legacy, stop_v2=95.0, badge="VALIDATED",
        direction="bullish"):
    return {"ts_scan": "2026-07-12T10:00:00+00:00", "ticker": "AAPL",
            "horizon": "4w",
            "plan": {"trigger_price": entry_v2, "stop_loss": stop_v2,
                     "tp1": entry_v2 + 2.0, "direction": direction,
                     "badge": badge, "tier": "B"},
            "legacy": {"entry": entry_legacy, "stop": 95.0,
                       "tp": entry_legacy + 6.0, "target2": None,
                       "confidence": 4}}


def test_summarize_deltas_and_badges():
    s = spr.summarize([_rec(100.0, 100.0), _rec(101.0, 100.0),
                       _rec(102.0, 100.0, badge="WEAK")])
    assert s["n"] == 3
    assert s["entry_delta_pct"]["median"] == 1.0     # [0, 1, 2]% -> median 1
    assert s["badges"] == {"VALIDATED": 2, "WEAK": 1}
    assert s["invariant_violations"] == 0


def test_invariant_violation_flagged():
    bad = _rec(100.0, 100.0, stop_v2=105.0)           # bullish stop ABOVE entry
    assert spr.summarize([bad])["invariant_violations"] == 1
