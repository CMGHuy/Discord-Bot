"""v146 I3: --trades-jsonl with --scenarios -- the row-collecting replay
worker, the SPY task slot, the JSONL writer and the progress file."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.backtesting import scenario_rows
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    """Trend up, then a 60-bar box (the test_backtest_scenarios.py fixture
    family): 16 hits on 4w, all of them closed (measured 2026-10-10)."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


# --- the worker ---------------------------------------------------------------

@pytest.mark.slow
def test_replay_ticker_rows_one_row_per_closed_exit():
    df = _structured_df()
    spy = make_ohlcv([300.0 + 0.1 * k for k in range(500)], start="2023-01-02")
    task = ("AAPL", df, ["4w"], None, None, GATES, True, None, None, None)

    exits, rows, gate_rows = bs._replay_ticker_rows(task + (spy, False))

    assert gate_rows == []                          # v147 record flag off

    assert exits == bs._replay_ticker(task)        # the aggregate's input is untouched
    closed = [r for r in exits["4w"] if r.outcome != "not_triggered"]
    assert closed, "fixture must close at least one trade"
    assert len(rows) == len(closed)
    assert [tuple(row) for row in rows] == [scenario_rows.ROW_KEYS] * len(rows)
    assert [(row["outcome"], row["r_total"]) for row in rows] == [(r.outcome, r.r_total) for r in closed]
    assert {(row["ticker"], row["horizon_key"]) for row in rows} == {("AAPL", "4w")}
    assert all(row["confidence_points"] for row in rows)


def test_replay_ticker_rows_skips_untriggered_exits(monkeypatch):
    class _Exit:
        def __init__(self, outcome):
            self.outcome = outcome

    df = make_ohlcv([100.0, 101.0, 102.0])
    hits = [bs.ReplayHit(0, "p0", "s0", (1, [])), bs.ReplayHit(1, "p1", "s1", (2, []))]
    monkeypatch.setattr(bs, "replay_scenarios_detailed", lambda *a, **k: hits)
    monkeypatch.setattr(bs, "simulate_exit",
                        lambda df, i, plan, scale_out: _Exit("win" if i == 0 else "not_triggered"))
    monkeypatch.setattr(scenario_rows, "scenario_trade_row",
                        lambda ticker, hk, df, hit, result, spy_df: {"i": hit.i, "spy": spy_df})

    exits, rows, _ = bs._replay_ticker_rows(("AAPL", df, ["2w"], None, None, {}, True, None, None, None, "SPY"))

    assert [r.outcome for r in exits["2w"]] == ["win", "not_triggered"]
    assert rows == [{"i": 0, "spy": "SPY"}]


# --- run_scenario_backtest ----------------------------------------------------

def _fake_workers(monkeypatch, seen):
    """Both replay workers faked; each records (len(args), args[10], args[11])."""
    def fake_plain(args):
        seen["plain"] = (len(args), args[10], args[11])
        return {"4w": []}, [{"gate": args[0]}] if args[11] else []

    def fake_rows(args):
        seen["rows"] = (len(args), args[10], args[11])
        return {"4w": []}, [{"ticker": args[0]}], [{"gate": args[0]}] if args[11] else []

    monkeypatch.setattr(bs, "_replay_ticker_gate_rows", fake_plain)
    monkeypatch.setattr(bs, "_replay_ticker_rows", fake_rows)


def test_spy_rides_only_on_the_row_collecting_tasks(monkeypatch):
    seen, calls = {}, []
    _fake_workers(monkeypatch, seen)
    frames = {"AAA": "frame-a", "BBB": "frame-b"}

    plain = bs.run_scenario_backtest(frames, None, None, gates=GATES, horizons=["4w"],
                                     workers=1, spy_df="SPY")
    out = bs.run_scenario_backtest(frames, None, None, gates=GATES, horizons=["4w"], workers=1,
                                   spy_df="SPY", collect_rows=True,
                                   on_ticker_done=lambda done, total: calls.append((done, total)))

    assert "rows" not in plain and seen["plain"] == (12, None, False)   # slot 10 empty, no SPY shipped
    assert seen["rows"] == (12, "SPY", False)
    assert out["rows"] == [{"ticker": "AAA"}, {"ticker": "BBB"}]
    assert "gate_rows" not in out
    assert calls == [(1, 2), (2, 2)]
    assert (out["pooled"], out["by_horizon"]) == (plain["pooled"], plain["by_horizon"])


def test_spy_fills_slot_10_beside_the_v147_record_flag(monkeypatch):
    """Merge with v147: SPY goes INTO main's reserved args[10], never appended
    after record_blocked (args[11]); both row kinds come back from one replay."""
    seen = {}
    _fake_workers(monkeypatch, seen)
    frames = {"AAA": "frame-a", "BBB": "frame-b"}

    out = bs.run_scenario_backtest(frames, None, None, gates=GATES, horizons=["4w"], workers=1,
                                   spy_df="SPY", collect_rows=True, record_blocked=True)

    assert seen["rows"] == (12, "SPY", True)
    assert out["rows"] == [{"ticker": "AAA"}, {"ticker": "BBB"}]
    assert out["gate_rows"] == [{"gate": "AAA"}, {"gate": "BBB"}]


def test_record_blocked_without_spy_keeps_the_plain_path(monkeypatch):
    seen = {}
    _fake_workers(monkeypatch, seen)

    out = bs.run_scenario_backtest({"AAA": "frame-a"}, None, None, gates=GATES, horizons=["4w"],
                                   workers=1, spy_df=None, record_blocked=True)

    assert seen == {"plain": (12, None, True)}
    assert "rows" not in out and out["gate_rows"] == [{"gate": "AAA"}]


# --- the writer and the mode --------------------------------------------------

def test_write_scenario_trades_jsonl_round_trips(tmp_path):
    import run_backtest_range as rr

    rows = [{"ticker": "AAPL", "r_total": np.float64(1.5), "legs": [],
             "entry_context": {"rs_pctile": np.int64(80)}},
            {"ticker": "MSFT", "r_total": -1.0, "legs": [], "entry_context": {}}]
    target = tmp_path / "reports" / "rows.jsonl"            # the directory does not exist yet

    rr.write_scenario_trades_jsonl(rows, target)

    assert [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()] == [
        {"ticker": "AAPL", "r_total": 1.5, "legs": [], "entry_context": {"rs_pctile": 80}},
        {"ticker": "MSFT", "r_total": -1.0, "legs": [], "entry_context": {}}]


def _stub_scenario_mode(monkeypatch, rr, tmp_path, seen):
    """run_scenario_mode with every loader and the replay itself faked."""
    monkeypatch.chdir(tmp_path)                 # it writes backtest_range_summary.txt to cwd
    monkeypatch.setattr(rr, "_tickers_for_run", lambda universe: ["AAA", "BBB"])
    monkeypatch.setattr(rr, "_membership_for_run", lambda universe, tickers: None)
    monkeypatch.setattr(rr, "load_cached", lambda ticker: f"frame-{ticker}")
    monkeypatch.setattr(rr, "_with_context", lambda df, **kw: df)
    monkeypatch.setattr(rr, "_exclusion_reason", lambda df, ticker, pit: None)
    monkeypatch.setattr(rr, "_build_asof_map", lambda tickers, frames, universe: {"AAA": "asof-a"})
    monkeypatch.setattr(rr, "_market_frame", lambda: "SPY")

    def fake_backtest(frames, start, end, **kwargs):
        seen.update(kwargs, frames=frames)
        if kwargs["on_ticker_done"] is not None:
            kwargs["on_ticker_done"](1, 2)
            seen["progress_text"] = (tmp_path / "out" / "rows.jsonl.progress").read_text(encoding="utf-8")
        empty = bs._aggregate([])
        stats = {"pooled": empty, "by_horizon": {hk: empty for hk in LEGACY_HORIZONS}}
        if kwargs["collect_rows"]:
            stats["rows"] = [{"ticker": "AAA"}, {"ticker": "BBB"}]
        return stats

    monkeypatch.setattr(rr, "run_scenario_backtest", fake_backtest)


def test_scenario_mode_writes_rows_and_clears_the_progress_file(monkeypatch, tmp_path):
    import run_backtest_range as rr

    seen = {}
    _stub_scenario_mode(monkeypatch, rr, tmp_path, seen)
    target = tmp_path / "out" / "rows.jsonl"

    rr.run_scenario_mode("2020-01-01", "2023-12-31", 30, "TRAIN", scale_out=True,
                         trades_jsonl=str(target))

    assert seen["collect_rows"] is True and seen["spy_df"] == "SPY"
    assert seen["asof_map"] == {"AAA": "asof-a"}
    assert seen["progress_text"].startswith("50.0% (1/2 tickers)")
    assert [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()] == [
        {"ticker": "AAA"}, {"ticker": "BBB"}]
    assert not Path(str(target) + ".progress").exists()     # deleted on completion


def test_scenario_mode_without_the_flag_collects_nothing(monkeypatch, tmp_path):
    import run_backtest_range as rr

    seen = {}
    _stub_scenario_mode(monkeypatch, rr, tmp_path, seen)

    rr.run_scenario_mode("2020-01-01", "2023-12-31", 30, "TRAIN", scale_out=True)

    assert seen["collect_rows"] is False and seen["spy_df"] is None
    assert seen["on_ticker_done"] is None
    assert seen["asof_map"] == {"AAA": "asof-a"}            # spec I3: built for every scenario run
    assert sorted(p.name for p in tmp_path.iterdir()) == ["backtest_range_summary.txt"]
