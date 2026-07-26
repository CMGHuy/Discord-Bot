# tests/test_wf_portfolio.py
import pytest

from swingbot.core import backtest_wf
from swingbot.core.backtest import BacktestSummary, BacktestTrade
from swingbot.core.backtest_wf import collect_portfolio_signals, portfolio_replay


def _sig(date, ticker, r, exit_date, sector="Tech"):
    return {"date": date, "ticker": ticker, "sector": sector,
            "r_multiple": r, "exit_date": exit_date}


def _trade(entry_date, exit_date, entry, stop_loss, take_profit, r_multiple,
           direction="long"):
    return BacktestTrade(entry_date=entry_date, exit_date=exit_date, direction=direction,
                         entry=entry, stop_loss=stop_loss, take_profit=take_profit,
                         outcome="win", exit_price=take_profit, return_pct=1.0,
                         r_multiple=r_multiple, holding_days=5)


def _summary(ticker, strategy, horizon_key, trades):
    return BacktestSummary(ticker=ticker, strategy=strategy, horizon_key=horizon_key,
                           total_signals=len(trades), evaluated=len(trades), wins=0,
                           losses=0, timeouts=0, scratches=0, win_rate=None,
                           avg_return_pct=None, avg_r_multiple=None, expectancy_r=None,
                           max_drawdown_pct=None, avg_holding_days=None, trades=trades)


def test_heat_cap_forces_skips_deterministically():
    # 8 simultaneous signals at 1% risk each, 6% heat cap -> 6 taken, 2 skipped
    sigs = [_sig("2021-01-04", f"T{i}", 0.4, "2021-02-01") for i in range(8)]
    out = portfolio_replay(sigs, heat_cap_pct=6.0, sector_cap_pct=100.0)
    assert out["trades_taken"] == 6
    assert out["trades_skipped"] == 2
    # r_multiples_taken tracks only opened trades -- one entry per taken
    # trade, none for the 2 skipped by the heat cap.
    assert len(out["r_multiples_taken"]) == 6
    assert out["r_multiples_taken"] == [0.4] * 6


def test_r_multiples_taken_excludes_skipped_and_preserves_order():
    # LATE only opens once an early exit frees heat; its r must still show
    # up in r_multiples_taken, appended after the 6 that opened first.
    sigs = ([_sig("2021-01-04", f"A{i}", 0.4, "2021-01-10") for i in range(6)]
            + [_sig("2021-01-11", "LATE", -0.7, "2021-02-01")])
    out = portfolio_replay(sigs, heat_cap_pct=6.0, sector_cap_pct=100.0)
    assert out["trades_taken"] == 7
    assert out["r_multiples_taken"] == [0.4] * 6 + [-0.7]


def test_heat_frees_on_exit():
    sigs = ([_sig("2021-01-04", f"A{i}", 0.4, "2021-01-10") for i in range(6)]
            + [_sig("2021-01-11", "LATE", 0.4, "2021-02-01")])
    out = portfolio_replay(sigs, heat_cap_pct=6.0, sector_cap_pct=100.0)
    assert out["trades_taken"] == 7            # early exits freed heat for LATE


def test_equity_compounds_and_dd_measured():
    sigs = [_sig(f"2021-0{m}-04", f"T{m}", r, f"2021-0{m}-20")
            for m, r in [(1, 1.0), (2, -1.0), (3, 1.0)]]
    out = portfolio_replay(sigs, heat_cap_pct=6.0, sector_cap_pct=100.0)
    assert out["final_multiple"] == pytest.approx(1.01 * 0.99 * 1.01, rel=1e-6)
    assert out["max_dd_pct"] > 0
    assert out["trades_per_month"] > 0


def test_collect_portfolio_signals_dedupes_similar_same_ticker(monkeypatch):
    # Mirrors performance.py's has_open_trade/has_similar_open_trade guard
    # that engine.py's scan loop enforces (~line 1025-1039): the live
    # account never holds two near-identical setups on the same ticker at
    # once, no matter which strategy/horizon found each one.
    monkeypatch.setattr(backtest_wf, "_symbols_for_folds", lambda: ["FAKE"])
    monkeypatch.setattr(backtest_wf, "_frame_for", lambda sym: object())
    monkeypatch.setattr("swingbot.core.universe.liquidity_ok", lambda df: True)
    monkeypatch.setattr("swingbot.core.universe.sector_map", lambda universe: {"FAKE": "Tech"})

    # StratA opens a setup 2021-01-04, still open (exits 2021-01-20) when:
    #  - StratB's "dup" trade opens 2021-01-10 with entry/stop/target all
    #    within DEDUP_TOLERANCE_PCT (2%) of StratA's -- must be DROPPED.
    #  - StratB's "diff" trade opens 2021-01-12 at totally different price
    #    levels -- the live account permits a genuinely distinct concurrent
    #    setup on the same ticker, so this must be KEPT.
    strat_a = _trade("2021-01-04", "2021-01-20", 100.0, 95.0, 110.0, 1.5)
    strat_b_dup = _trade("2021-01-10", "2021-02-01", 100.5, 95.2, 110.3, 0.8)
    strat_b_diff = _trade("2021-01-12", "2021-02-05", 50.0, 45.0, 60.0, 1.0)

    def fake_run_backtest_daterange(ticker, df, strategy, horizon_key, date_from, date_to, **kwargs):
        trades = {"StratA": [strat_a], "StratB": [strat_b_dup, strat_b_diff]}[strategy]
        return _summary(ticker, strategy, horizon_key, trades)

    monkeypatch.setattr("swingbot.core.backtest.run_backtest_daterange",
                        fake_run_backtest_daterange)

    signals = collect_portfolio_signals("2021-01-01", "2021-12-31",
                                        strategies=["StratA", "StratB"],
                                        horizons=["2w"])

    assert len(signals) == 2
    assert sorted(s["date"] for s in signals) == ["2021-01-04", "2021-01-12"]


def test_collect_portfolio_signals_keeps_non_overlapping_similar_trades(monkeypatch):
    # Same near-identical price levels, but StratA's trade has already
    # CLOSED (exit_date 2021-01-08) before StratB's opens (2021-01-10) --
    # the live account's guard only blocks while a similar trade is still
    # open, so both must be kept once they no longer overlap in time.
    monkeypatch.setattr(backtest_wf, "_symbols_for_folds", lambda: ["FAKE"])
    monkeypatch.setattr(backtest_wf, "_frame_for", lambda sym: object())
    monkeypatch.setattr("swingbot.core.universe.liquidity_ok", lambda df: True)
    monkeypatch.setattr("swingbot.core.universe.sector_map", lambda universe: {"FAKE": "Tech"})

    strat_a = _trade("2021-01-04", "2021-01-08", 100.0, 95.0, 110.0, 1.5)
    strat_b = _trade("2021-01-10", "2021-02-01", 100.5, 95.2, 110.3, 0.8)

    def fake_run_backtest_daterange(ticker, df, strategy, horizon_key, date_from, date_to, **kwargs):
        trades = {"StratA": [strat_a], "StratB": [strat_b]}[strategy]
        return _summary(ticker, strategy, horizon_key, trades)

    monkeypatch.setattr("swingbot.core.backtest.run_backtest_daterange",
                        fake_run_backtest_daterange)

    signals = collect_portfolio_signals("2021-01-01", "2021-12-31",
                                        strategies=["StratA", "StratB"],
                                        horizons=["2w"])

    assert len(signals) == 2
    assert sorted(s["date"] for s in signals) == ["2021-01-04", "2021-01-10"]
