"""Task E39: the anchored walk-forward harness.

This module is the gatekeeper every later Edge component has to pass, so
the tests here care about two things above all: the folds and the gate
constants are FROZEN (pre-registered before data contact), and no fold
ever evaluates a bar inside its own training window.
"""
import pytest

from swingbot import config
from swingbot.core.backtest_wf import ANCHORED_FOLDS, gate, run_folds


def test_folds_are_frozen():
    assert len(ANCHORED_FOLDS) == 3
    for train_start, train_end, test_start, test_end in ANCHORED_FOLDS:
        assert train_end < test_start          # ISO strings compare correctly
        assert train_start == "2018-01-01"     # anchored, expanding
    assert ANCHORED_FOLDS[0][2].startswith("2021")
    assert ANCHORED_FOLDS[2][3] == "2023-12-31"


def test_the_burned_validation_window_never_appears():
    """2024-2025 is spent exactly once, at the very end of the plan. It
    must not be reachable from any fold, in either window."""
    for window in ANCHORED_FOLDS:
        for date in window:
            assert date < "2024-01-01"


def test_run_folds_no_test_bars_reachable_in_train():
    seen = []

    def spy_run(start, end, overrides):
        seen.append((start, end, bool(overrides)))
        return {"expectancy_r": 0.10, "n": 100}

    run_folds({"X": 1}, run_fn=spy_run)
    # every invocation is a TEST window from the fold table -- never a
    # window that overlaps training years
    for start, end, _ in seen:
        assert (start, end) in {(f[2], f[3]) for f in ANCHORED_FOLDS}
    # baseline + component, once each, per fold -- and the baseline is
    # always run with NO overrides.
    assert len(seen) == 2 * len(ANCHORED_FOLDS)
    assert [has_over for _, _, has_over in seen] == [False, True] * len(ANCHORED_FOLDS)


def test_run_folds_reports_per_fold_deltas_and_pooled():
    scores = {False: 0.10, True: 0.14}
    result = run_folds({"X": 1},
                       run_fn=lambda s, e, o: {"expectancy_r": scores[bool(o)], "n": 80})
    assert [f["test_years"] for f in result["folds"]] == ["2021", "2022", "2023"]
    assert all(f["delta_expectancy_r"] == pytest.approx(0.04) for f in result["folds"])
    assert result["pooled_delta_expectancy_r"] == pytest.approx(0.04)
    assert all(f["n"] == 80 for f in result["folds"])


def test_run_folds_survives_a_window_with_no_trades():
    """An empty window yields expectancy None, which must propagate as an
    un-scoreable fold rather than a zero that reads like 'no effect'."""
    def run(start, end, overrides):
        if start.startswith("2022"):
            return {"expectancy_r": None, "n": 0}
        return {"expectancy_r": 0.10 if overrides else 0.08, "n": 50}

    result = run_folds({"X": 1}, run_fn=run)
    assert result["folds"][1]["delta_expectancy_r"] is None
    assert gate(result) == "FAIL"


def _result(deltas, n=100):
    folds = [{"test_years": f"202{i+1}", "baseline": {"expectancy_r": 0.10, "n": n},
              "component": {"expectancy_r": 0.10 + d, "n": n},
              "delta_expectancy_r": d, "n": n}
             for i, d in enumerate(deltas)]
    pooled = sum(deltas) / len(deltas)
    return {"folds": folds, "pooled_delta_expectancy_r": pooled}


def test_gate_two_of_three_improving_passes():
    assert gate(_result([0.03, 0.02, -0.01])) == "PASS"


def test_gate_fails_on_big_single_fold_degradation():
    assert gate(_result([0.05, 0.05, -0.06])) == "FAIL"   # one fold worse by >0.05R


def test_gate_fails_on_one_of_three():
    assert gate(_result([0.05, -0.01, -0.02])) == "FAIL"


def test_gate_fails_on_thin_folds():
    assert gate(_result([0.03, 0.03, 0.01], n=20)) == "FAIL"


def test_gate_constants_match_the_pre_registered_rule():
    """Quoted from the plan's Global Constraints: improves in >= 2 of 3
    folds, no fold degrades by more than 0.05R, N >= 30 per fold. Changing
    any of these silently would invalidate every decision already recorded
    against them."""
    from swingbot.core import backtest_wf as wf
    assert wf.GATE_MIN_IMPROVING_FOLDS == 2
    assert wf.GATE_MAX_DEGRADATION_R == 0.05
    assert wf.GATE_MIN_N_PER_FOLD == 30
    # exactly at the boundaries: 0.05 degradation and N=30 are allowed
    assert gate(_result([0.03, 0.03, -0.05], n=30)) == "PASS"


def test_overrides_are_restored_even_when_a_run_raises():
    """A component run that blows up must not leave config mutated -- the
    next component's folds would silently inherit it."""
    from swingbot.core import backtest_wf as wf
    before = config.REGIME_GATES_ENABLED

    def boom(start, end, overrides):
        if overrides:
            raise RuntimeError("backtest exploded")
        return {"expectancy_r": 0.1, "n": 50}

    with pytest.raises(RuntimeError):
        wf.run_folds({"REGIME_GATES_ENABLED": True}, run_fn=wf._guarded(boom))
    assert config.REGIME_GATES_ENABLED == before


def test_default_run_passes_a_horizon_to_the_backtest(monkeypatch):
    """Regression on the plan's own snippet, which called
    run_backtest_daterange(sym, df, strat, start, end) -- the real
    signature is (ticker, df, strategy, HORIZON_KEY, date_from, date_to),
    so those five positionals bound `start` to horizon_key and raised
    TypeError for the missing date_to. It was never callable."""
    import pandas as pd
    from swingbot.core import backtest_wf as wf

    calls = []

    class _Summary:
        trades = []

    def fake_daterange(ticker, df, strategy, horizon_key, date_from, date_to, **kw):
        calls.append((ticker, strategy, horizon_key, date_from, date_to, kw))
        return _Summary()

    monkeypatch.setattr(wf, "_symbols_for_folds", lambda: ["AAA"])
    monkeypatch.setattr(wf, "_frame_for", lambda sym: pd.DataFrame({"Close": [1.0]}))
    monkeypatch.setattr("swingbot.core.universe.liquidity_ok", lambda df, *a, **k: True)
    monkeypatch.setattr("swingbot.core.backtest.run_backtest_daterange", fake_daterange)

    out = wf._default_run("2021-01-01", "2021-12-31", {}, strategies=["RSI"],
                          horizons=["4w"])
    assert out == {"expectancy_r": None, "n": 0}
    assert calls, "the backtest must actually be invoked"
    ticker, strategy, hk, start, end, kw = calls[0]
    assert (ticker, strategy, hk, start, end) == ("AAA", "RSI", "4w",
                                                 "2021-01-01", "2021-12-31")
    # Frictions on, and the SAME exit model the E22 baseline was measured
    # with -- otherwise fold deltas aren't comparable to that baseline.
    assert kw["frictions"] is True
    assert kw["exit_model"] == "v2" and kw["scale_out"] is True
    # tp2_mode="levels" matches the E22 baseline tooling's own default AND
    # is what makes level-sourced components (AVWAP, HVN/LVN) reach the
    # backtest at all -- with "none" build_level_map is never called and
    # those folds would score a meaningless 0.0000 delta. Verified
    # empirically before pinning: flipping AVWAP_LEVELS_ENABLED moves
    # expectancy under "levels" and is bit-identical under "none".
    assert kw["tp2_mode"] == "levels"


def test_default_run_ignores_trades_without_an_r_multiple(monkeypatch):
    import pandas as pd
    from swingbot.core import backtest_wf as wf

    class _T:
        def __init__(self, r):
            self.r_multiple = r

    class _Summary:
        trades = [_T(0.5), _T(None), _T(-0.5)]

    monkeypatch.setattr(wf, "_symbols_for_folds", lambda: ["AAA"])
    monkeypatch.setattr(wf, "_frame_for", lambda sym: pd.DataFrame({"Close": [1.0]}))
    monkeypatch.setattr("swingbot.core.universe.liquidity_ok", lambda df, *a, **k: True)
    monkeypatch.setattr("swingbot.core.backtest.run_backtest_daterange",
                        lambda *a, **k: _Summary())
    out = wf._default_run("2021-01-01", "2021-12-31", {}, strategies=["RSI"],
                          horizons=["4w"])
    assert out == {"expectancy_r": pytest.approx(0.0), "n": 2}


def test_run_backtest_daterange_defaults_are_unchanged():
    """The pass-through params added for the harness must not move any
    existing caller's numbers."""
    import inspect
    from swingbot.core.backtest import run_backtest_daterange
    params = inspect.signature(run_backtest_daterange).parameters
    assert params["frictions"].default is True
    assert params["exit_model"].default == "v1"
    assert params["scale_out"].default is False
    assert params["tp2_mode"].default == "none"


def test_folds_read_the_same_cache_the_baseline_was_measured_on(tmp_path, monkeypatch):
    """backtest_cache/, not market_data/. The E22 baseline these folds are
    judged against came from that cache, and market_data/ starts 2018-06 --
    right at the folds' own anchor, so indicators would get no warm-up."""
    import pandas as pd
    from swingbot.core import backtest_wf as wf

    monkeypatch.setattr("swingbot.core.backtest_cache.CACHE_DIR", tmp_path)
    assert wf._frame_for("NOPE") is None

    frame = pd.DataFrame({"Open": [1.0], "High": [1.0], "Low": [1.0],
                          "Close": [1.0], "Volume": [1.0]},
                         index=pd.to_datetime(["2021-01-04"]))
    frame.to_csv(tmp_path / "AAA.csv")
    got = wf._frame_for("AAA")
    assert got is not None and list(got.columns) == ["Open", "High", "Low", "Close", "Volume"]

    def _boom(*a, **k):
        raise ValueError("corrupt csv")

    monkeypatch.setattr("pandas.read_csv", _boom)
    assert wf._frame_for("AAA") is None   # one bad file can't kill a sweep


# --- E40: shadow forward-gate ------------------------------------------------

def _shadow_report():
    """scripts/ is not a package (see tests/scripts/test_run_backtest_range.py
    for the same dance) -- put it on the path and import by module name."""
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "scripts"))
    from shadow_component_report import shadow_component_report
    return shadow_component_report


def _shadow_line(component, variant, fwd):
    return {"ticker": "T", "component": component, "variant": variant,
            "fwd_return_10d": fwd}


def test_shadow_report_compares_cohorts():
    shadow_component_report = _shadow_report()
    lines = ([_shadow_line("rs_min", "on", 0.02)] * 30
             + [_shadow_line("rs_min", "off", 0.01)] * 40
             + [_shadow_line("other", "on", 9.9)] * 5)      # ignored
    rep = shadow_component_report(lines, "rs_min")
    assert rep["on"]["n"] == 30 and rep["off"]["n"] == 40
    assert rep["on"]["fwd_expectancy"] > rep["off"]["fwd_expectancy"]
    assert rep["verdict"] == "PROMOTE"


def test_shadow_report_holds_when_component_underperforms():
    shadow_component_report = _shadow_report()
    lines = ([_shadow_line("rs_min", "on", 0.00)] * 30
             + [_shadow_line("rs_min", "off", 0.02)] * 30)
    assert shadow_component_report(lines, "rs_min")["verdict"] == "HOLD"


def test_shadow_report_holds_on_a_thin_or_unresolved_cohort():
    """Two ways a window can fail to decide anything, both of which must
    read HOLD rather than PROMOTE: too few on-cohort entries, and entries
    whose 10-day forward return has not been filled in yet."""
    shadow_component_report = _shadow_report()
    thin = ([_shadow_line("c", "on", 0.05)] * 19
            + [_shadow_line("c", "off", 0.00)] * 30)
    assert shadow_component_report(thin, "c")["verdict"] == "HOLD"

    unresolved = ([_shadow_line("c", "on", None)] * 30
                  + [_shadow_line("c", "off", 0.00)] * 30)
    rep = shadow_component_report(unresolved, "c")
    assert rep["on"]["n"] == 0 and rep["verdict"] == "HOLD"

    assert shadow_component_report([], "c")["verdict"] == "HOLD"


def test_shadow_report_promotes_on_an_exact_tie():
    """The pre-registered bar is >=, not >. Recorded explicitly so nobody
    'tightens' it later without a new pre-registration."""
    shadow_component_report = _shadow_report()
    tied = ([_shadow_line("c", "on", 0.01)] * 25
            + [_shadow_line("c", "off", 0.01)] * 25)
    assert shadow_component_report(tied, "c")["verdict"] == "PROMOTE"


def test_shadow_logger_accepts_component_and_variant_tags(tmp_path):
    import json
    from swingbot.core import shadow_log
    from swingbot.core.plan_engine import PlanStatus, TradePlanV2

    plan = TradePlanV2(
        plan_id="p", ticker="AAA", created_at="2026-01-01", source="strategy",
        strategy="RSI", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=100.0,
        expiry_bars=5, stop_loss=98.0, tp1=101.0, tp1_fraction=0.5, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
        quality_breakdown=[], tier="C", badge="WEAK", badge_stats={},
        status=PlanStatus.ACTIVE)
    path = str(tmp_path / "shadow.jsonl")

    shadow_log.append(plan, {"entry": 100.0}, path=path)            # untagged
    shadow_log.append(plan, {"entry": 100.0}, path=path,
                      component="AVWAP_LEVELS_ENABLED", variant="on")

    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    assert len(rows) == 2
    # An untagged line must stay exactly as before -- shadow_parity_report.py
    # already reads this file and must not see new keys it doesn't expect.
    assert "component" not in rows[0] and "variant" not in rows[0]
    assert rows[1]["component"] == "AVWAP_LEVELS_ENABLED"
    assert rows[1]["variant"] == "on"
    assert rows[1]["fwd_return_10d"] is None      # filled later by the backfill


def test_forward_return_backfill_only_resolves_matured_entries(tmp_path):
    """The gate compares 10-day forward returns, and nothing in this repo
    produced them before this task. The backfill fills a line only once 10
    trading bars exist after its scan date -- an immature line stays None
    rather than being scored on a partial window."""
    import json
    import pandas as pd
    from swingbot.core import shadow_log

    path = tmp_path / "shadow.jsonl"
    rows = [
        {"ts_scan": "2026-01-05T12:00:00+00:00", "ticker": "AAA",
         "plan": {"trigger_price": 100.0}, "component": "c", "variant": "on",
         "fwd_return_10d": None},
        {"ts_scan": "2026-03-02T12:00:00+00:00", "ticker": "AAA",
         "plan": {"trigger_price": 100.0}, "component": "c", "variant": "off",
         "fwd_return_10d": None},
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    idx = pd.bdate_range("2026-01-01", periods=40)
    frame = pd.DataFrame({"Close": [100.0 + i for i in range(40)]}, index=idx)

    filled = shadow_log.backfill_forward_returns(
        str(path), price_fn=lambda t: frame, horizon_days=10)
    assert filled == 1

    out = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    # 2026-01-05 is business-day bar 2 (close 102); ten TRADING bars later
    # is bar 12 (close 112). The entry leg is the bar at/after the scan
    # date, not the frame's first bar.
    assert out[0]["fwd_return_10d"] == pytest.approx(112 / 102 - 1)
    assert out[1]["fwd_return_10d"] is None       # not matured yet
    # Idempotent: a second pass resolves nothing new.
    assert shadow_log.backfill_forward_returns(
        str(path), price_fn=lambda t: frame, horizon_days=10) == 0
