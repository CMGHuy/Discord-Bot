"""v102: Fibonacci x Rolling S/R confluence funnel (pure logic + collection shape)."""
import sys
from pathlib import Path
from types import SimpleNamespace as T

import pytest

from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))


def _m():
    import measure_fib_confluence as m
    return m


def _rows(direction, n_win, n_loss, year="2015", win_r=2.0, horizon="3m"):
    rows = [{"ticker": "AAA", "horizon_key": horizon, "direction": direction,
             "entry_date": f"{year}-06-01", "outcome": "win", "r_multiple": win_r} for _ in range(n_win)]
    rows += [{"ticker": "AAA", "horizon_key": horizon, "direction": direction,
              "entry_date": f"{year}-06-01", "outcome": "loss", "r_multiple": -1.0} for _ in range(n_loss)]
    return rows


def test_tol_key_is_stable():
    m = _m()
    assert [m.tol_key(t) for t in (0.0, 0.25, 0.5, 1.0)] == ["0", "0.25", "0.5", "1"]


def test_badge_verdict_needs_every_clause():
    m = _m()
    ok = m.pooled(_rows("bullish", 20, 10))
    assert m.badge_verdict(ok, 30)["clears"] is True
    assert m.badge_verdict(ok, 31)["clears"] is False                 # N
    low = m.pooled(_rows("bullish", 14, 16))
    assert m.badge_verdict(low, 30)["clauses"]["wr"] is False          # WR 46.7
    neg = m.pooled(_rows("bullish", 16, 14, win_r=0.5))
    assert m.badge_verdict(neg, 30)["clauses"]["exp_r"] is False       # ExpR < 0


def _by_tol(passing_tols, direction="bullish"):
    m = _m()
    out = {m.tol_key(m.BASELINE_TOL): _rows(direction, 10, 25)}
    for tol in m.GRID:
        wins = 25 if tol in passing_tols else 10
        out[m.tol_key(tol)] = _rows(direction, wins, 15, win_r=2.0 + tol)
    return out


def test_stage1_requires_plateau_and_picks_highest_expr():
    m = _m()
    out = m.stage1(_by_tol({0.5, 0.75, 1.0}), "bullish")
    # 0.5's neighbour 0.25 fails -> not plateau; 0.75 and 1.0 plateau; 1.0 has higher ExpR
    assert out["plateau_passing"] == [0.75, 1.0] and out["winner"] == 1.0


def test_stage1_isolated_spike_has_no_winner():
    m = _m()
    assert m.stage1(_by_tol({0.5}), "bullish")["winner"] is None


def test_fold_pick_uses_only_the_train_span():
    m = _m()
    rows = {m.tol_key(t): [] for t in (m.BASELINE_TOL, *m.GRID)}
    rows[m.tol_key(0.25)] = _rows("bullish", 20, 15, year="2011") + _rows("bullish", 0, 40, year="2016")
    rows[m.tol_key(0.5)] = _rows("bullish", 5, 30, year="2011") + _rows("bullish", 40, 0, year="2016")
    assert m.fold_pick(rows, "bullish", 2013) == 0.25       # 2016 rows are invisible to the 2013 fold
    assert m.fold_pick(rows, "bullish", 2011) is None       # train span 2010 only: no cell has N >= 30
    assert m.fold_pick(rows, "bullish", 2017) == 0.5        # 2011 + 2016 both visible: 0.5 now leads


def test_fold_verdict_two_thirds_and_minimum_three():
    m = _m()
    good = {"n": 20, "expectancy_r": 0.2}
    bad = {"n": 20, "expectancy_r": -0.1}
    thin = {"n": 5, "expectancy_r": 1.0}
    folds = [{"tol": 0.5, "stats": s} for s in (good, good, bad, thin)]
    assert m.fold_verdict(folds)["clears"] is True           # 2 of 3 qualifying positive
    folds = [{"tol": 0.5, "stats": s} for s in (good, bad, bad)]
    assert m.fold_verdict(folds)["clears"] is False
    folds = [{"tol": 0.5, "stats": good}, {"tol": 0.5, "stats": good}, {"tol": None, "stats": None}]
    v = m.fold_verdict(folds)
    assert v["clears"] is False and v["unselected"] == 1     # only 2 qualifying


def test_confluence_tol_restores_the_flag():
    m = _m()
    from swingbot import config
    before = getattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0)
    with m.confluence_tol(0.75):
        assert config.FIB_SR_CONFLUENCE_ATR == 0.75
    assert config.FIB_SR_CONFLUENCE_ATR == before


def test_require_ext_cache_refuses_the_shared_cache(monkeypatch, tmp_path):
    m = _m()
    from swingbot.core.marketdata import backtest_cache as bc
    monkeypatch.setattr(bc, "CACHE_DIR", tmp_path / "backtest_cache")
    with pytest.raises(SystemExit):
        m.require_ext_cache()
    monkeypatch.setattr(bc, "CACHE_DIR", tmp_path / m.EXT_CACHE_NAME)
    m.require_ext_cache()


def test_collect_trades_populations_and_window(monkeypatch):
    m = _m()
    frame = make_ohlcv([100.0] * 300, start="2012-01-02")
    seen = []

    def run_fn(ticker, df, strategy, horizon, **kw):
        from swingbot import config
        seen.append((dict(m.STRATEGY_GATES.get(strategy) or {}).get("directions"),
                     config.FIB_SR_CONFLUENCE_ATR))
        return T(trades=[
            T(direction="bullish", entry_date="2012-06-01", outcome="win", r_multiple=2.0, context={}),
            T(direction="bullish", entry_date="2024-06-01", outcome="win", r_multiple=2.0, context={}),
            T(direction="bearish", entry_date="2012-06-01", outcome="loss", r_multiple=-1.0,
              context={"rs_combined": 10.0}),
            T(direction="bearish", entry_date="2012-06-01", outcome="win", r_multiple=2.0,
              context={"rs_combined": 80.0}),
        ])

    progress = T(tick=lambda label: None)
    rows = m.collect_trades({"AAA": frame}, {}, 0.5, m.TRAIN_EXT, horizons=("3m",),
                            run_fn=run_fn, progress=progress)
    assert [(r["direction"], r["entry_date"]) for r in rows] == [("bullish", "2012-06-01"),
                                                                ("bearish", "2012-06-01")]
    assert seen[0] == (("bullish",), 0.5) and seen[1] == (("bullish", "bearish"), 0.5)
    assert set(rows[0]) == {"ticker", "horizon_key", "direction", "entry_date", "outcome", "r_multiple"}


def test_count_signals_by_year(monkeypatch):
    m = _m()
    frame = make_ohlcv([100.0] * 10, start="2012-12-27")
    import pandas as pd

    def fake_entries(strategy, df, horizon):
        s = pd.Series(True, index=df.index)
        return s, s

    monkeypatch.setattr(m, "entries_for", fake_entries)
    out = m.count_signals({"AAA": frame}, (0.0, 0.5), horizons=("3m",))
    assert out["0.5|bullish"] == {"2012": 3, "2013": 7}
    assert set(out) == {"0|bullish", "0|bearish", "0.5|bullish", "0.5|bearish"}


def test_registry_record_status_is_derived_from_the_validation_clauses():
    m = _m()
    rec = m.registry_record(_rows("bullish", 10, 5), "2026-10-01")     # N=15, WR 66.7, ExpR +1.0
    assert rec["source"] == "strategy" and rec["strategy"] == "Fibonacci" and rec["horizon"] is None
    assert rec["status"] == "VALIDATED"
    assert rec["window"] == "2024-01-01..2025-12-31" and rec["run_date"] == "2026-10-01"
    assert m.registry_record(_rows("bullish", 9, 5), "2026-10-01")["status"] == "WEAK"   # N=14


def test_validation_refuses_without_preregistration(tmp_path):
    m = _m()
    with pytest.raises(SystemExit):
        m.main(["validation", "--tol", "0.5", "--direction", "bullish",
                "--preregistration", str(tmp_path / "missing.md"), "--out", str(tmp_path / "v.json")])
