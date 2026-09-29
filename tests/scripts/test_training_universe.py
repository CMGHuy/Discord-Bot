"""v112: widening the backtest training universe with a point-in-time mask."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
sys.path.insert(0, str(ROOT / "scripts" / "data"))

import fetch_backtest_data as fbd  # noqa: E402
import run_backtest_range as rbr  # noqa: E402
from swingbot.core.backtesting import backtest_scenarios as bs  # noqa: E402

SPANS = [("2015-01-02", "2021-06-01")]


def _t(day):
    return SimpleNamespace(entry_date=day)


def test_member_trades_masks_by_entry_date():
    kept = rbr.member_trades([_t("2014-12-31"), _t("2020-05-05"), _t("2021-06-01")], SPANS)
    assert [t.entry_date for t in kept] == ["2020-05-05"]


def test_member_trades_unmasked_without_membership():
    trades = [_t("2014-12-31"), _t("2020-05-05")]
    assert rbr.member_trades(trades, None) == trades


def test_spans_for():
    assert rbr._spans_for(None, "AAPL") is None
    assert rbr._spans_for({"AAPL": SPANS}, "ZZZ") == []


def test_pit_run_skips_end_of_history_liquidity_floor(monkeypatch):
    monkeypatch.setattr(rbr, "liquidity_reason", lambda df: "price 1.00 < 5.00 floor")
    monkeypatch.setattr(rbr, "data_quality_issues", lambda df, t: [])
    assert rbr._exclusion_reason(object(), "X", pit=False) == ("illiquid", "price 1.00 < 5.00 floor")
    assert rbr._exclusion_reason(object(), "X", pit=True) is None


def test_pit_run_still_applies_data_quality(monkeypatch):
    monkeypatch.setattr(rbr, "data_quality_issues", lambda df, t: ["gap", "zero volume"])
    assert rbr._exclusion_reason(object(), "X", pit=True) == ("bad data", "gap; zero volume")


def test_signal_scope_combines_window_and_membership():
    assert bs._signal_in_scope("2020-01-02", "2020-01-01", "2023-12-31", None)
    assert bs._signal_in_scope("2020-01-02", None, None, SPANS)
    assert not bs._signal_in_scope("2022-01-03", None, None, SPANS)
    assert not bs._signal_in_scope("2019-12-31", "2020-01-01", None, SPANS)
    assert not bs._signal_in_scope("2020-01-02", None, None, [])


def test_replay_ticker_drops_non_member_signals(monkeypatch):
    import pandas as pd
    idx = pd.to_datetime(["2014-12-30", "2015-06-01", "2022-02-01"])
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=idx)
    monkeypatch.setattr(bs, "replay_scenarios", lambda *a, **k: [(0, "p0"), (1, "p1"), (2, "p2")])
    monkeypatch.setattr(bs, "simulate_exit", lambda df, i, plan, scale_out: plan)
    base = ("T", df, ["2w"], None, None, {}, True, None, None)
    assert bs._replay_ticker(base)["2w"] == ["p0", "p1", "p2"]          # legacy 9-tuple
    assert bs._replay_ticker(base + (None,))["2w"] == ["p0", "p1", "p2"]  # unmasked
    assert bs._replay_ticker(base + (SPANS,))["2w"] == ["p1"]


def test_training_tickers_unions_watchlist_benchmark_and_universe(monkeypatch):
    from swingbot.core.marketdata import universe
    monkeypatch.setattr(universe, "universe_symbols", lambda name: ["MSFT", "AAPL", "OLD"])
    assert fbd.training_tickers(["AAPL", "NVDA"], "SPY", None) == ["AAPL", "NVDA", "SPY"]
    assert fbd.training_tickers(["AAPL"], "SPY", "sp500_pit") == ["AAPL", "MSFT", "OLD", "SPY"]


def test_write_coverage_lists_unavailable_members(monkeypatch, tmp_path):
    import json
    from swingbot.core.marketdata import universe
    monkeypatch.setattr(universe, "universe_symbols", lambda name: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(fbd, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(fbd, "cache_path", lambda t: tmp_path / f"{t}.csv")
    (tmp_path / "AAA.csv").write_text("x")
    out = fbd.write_coverage("sp500_pit", ["AAA", "BBB", "CCC", "SPY"], ["BBB", "CCC", "SPY"])
    data = json.loads(out.read_text())
    assert data["cached"] == 1 and data["members"] == 3
    assert data["missing"] == ["BBB", "CCC"]
