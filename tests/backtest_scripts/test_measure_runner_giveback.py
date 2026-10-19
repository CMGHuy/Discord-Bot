"""v176 TRAIN paired measurement: pairing, frictions, the TRAIN cut, the verdict rule.

Frame: part 2's run-up-and-reversal (tests/planning/test_exit_sim_giveback.py),
dated in TRAIN. Flag off, the runner rides to the floor 106.667 on bar 4; on,
bar 2's close 120 sets a 114 give-back that bar 3 hits.
"""
import json
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.planning import exit_sim
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import measure_runner_giveback as mrg  # noqa: E402

FLOOR = 100.0 + (2.0 / 3.0) * 10.0
BARS = [100.0, (100.0, 111.0, 99.5, 110.5), (110.5, 121.0, 110.0, 120.0),
        (120.0, 120.5, 113.0, 113.5), (113.5, 114.0, 106.0, 106.5)]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0)
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "close")   # restored after paired_trades sets it


def _one_entry(monkeypatch, seen=None):
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None, trail_atr_mult=50.0)

    def fake_entries(ticker, df):
        if seen is not None:
            seen.append(df)
        return [("strategy", "2w", 0, plan)]
    monkeypatch.setattr(mrg, "_entries", fake_entries)


def test_the_same_entry_is_simulated_off_and_on_with_frictions(monkeypatch):
    _one_entry(monkeypatch)
    [row] = mrg.paired_trades("AAA", make_ohlcv(BARS, start="2021-01-04"), basis="close")
    assert row["off"]["reason"] == "runner_be" and row["off"]["stop_source"] == "floor"
    assert row["on"]["reason"] == "runner_trail" and row["on"]["stop_source"] == "giveback"
    assert row["off"]["exit_price"] == pytest.approx(FLOOR)
    assert row["on"]["exit_price"] == pytest.approx(114.0)
    assert row["changed"] is True
    # net of 5 bps per fill: the entry fill 100.05 re-bases risk to 5.05; leg 1 cancels
    assert row["on"]["r_net"] - row["off"]["r_net"] == pytest.approx(
        0.5 * (114.0 - FLOOR) * 0.9995 / 5.05)
    assert config.RUNNER_GIVEBACK_ENABLED is True            # each arm restores the flag


def test_runner_context_uses_the_off_arms_window(monkeypatch):
    _one_entry(monkeypatch)
    [row] = mrg.paired_trades("AAA", make_ohlcv(BARS, start="2021-01-04"), basis="close")
    assert row["tp1_index"] == 1
    assert row["mfe_off_r"] == pytest.approx(4.0)            # best close 120 over [1, 4)
    assert row["gb_r"] == pytest.approx(0.05 * 120.0 / 5.0)
    assert (row["days_off"], row["days_on"]) == (3, 2)
    assert row["shakeout"] is False                           # 106.5 after exit < 120
    assert row["gap_worse_r"] == 0.0                          # bar 3 opened at 120 > 114


def test_high_low_basis_takes_e_from_the_bar_high(monkeypatch):
    _one_entry(monkeypatch)
    [row] = mrg.paired_trades("AAA", make_ohlcv(BARS, start="2021-01-04"), basis="high_low")
    assert exit_sim.GIVEBACK_EXTREME_BASIS == "high_low"
    assert row["on"]["exit_price"] == pytest.approx(exit_sim.giveback_stop(121.0, 5.0, "bullish"))


def test_no_bar_after_train_end_reaches_the_entries_or_the_exits(monkeypatch):
    seen = []
    _one_entry(monkeypatch, seen)
    mrg.paired_trades("AAA", make_ohlcv(BARS * 3, start="2023-12-20"), basis="close")
    assert str(seen[0].index[-1].date()) <= "2023-12-31"


def test_an_unknown_basis_is_refused():
    with pytest.raises(ValueError, match="basis"):
        mrg.paired_trades("AAA", make_ohlcv(BARS, start="2021-01-04"), basis="open")


@pytest.mark.parametrize("lo,hi,expected", [(0.01, 0.2, "PASS"), (-0.2, -0.01, "FAIL"),
                                            (-0.1, 0.1, "NO-LIFT"), (0.0, 0.1, "NO-LIFT"),
                                            (None, None, "UNMEASURABLE")])
def test_verdict_rule(lo, hi, expected):
    assert mrg.verdict(lo, hi) == expected


def _row(ticker, off_r, on_r, *, hk="2w", day="2021-03-01"):
    def arm(r, source):
        return {"r_net": r, "runner_r": r, "stop_source": source, "reason": "runner_trail",
                "exit_date": day, "exit_price": 1.0, "exit_index": 5}
    return {"ticker": ticker, "horizon_key": hk, "signal_date": day, "changed": off_r != on_r,
            "off": arm(off_r, "floor"), "on": arm(on_r, "giveback"), "mfe_off_r": 3.0,
            "gb_r": 1.0, "days_off": 6, "days_on": 3, "shakeout": False, "gap_worse_r": 0.0}


def test_summarise_passes_a_uniform_lift():
    rows = [_row(t, 1.0, 1.1) for t in "ABCDEF"]
    s = mrg.summarise(rows, n_resamples=200)
    assert s["primary"]["delta_exp_r"] == pytest.approx(0.1)
    assert s["primary"]["verdict"] == "PASS"
    assert s["changed"] == 6
    assert s["runner"]["off"]["floor_share"] == 1.0
    assert s["runner"]["on"]["capture_fixed_window"] == pytest.approx(1.1 / 3.0)
    assert s["giveback_exits"]["n"] == 6


def test_summarise_calls_a_mixed_result_no_lift():
    rows = [_row(t, 1.0, 1.2) for t in "ABC"] + [_row(t, 1.0, 0.8) for t in "DEF"]
    s = mrg.summarise(rows, n_resamples=200)
    assert s["primary"]["ci_lo"] < 0 < s["primary"]["ci_hi"]
    assert s["primary"]["verdict"] == "NO-LIFT"
    assert s["cells_looked_at"] == 2 * len(s["per_horizon"]) + 8


def test_book_reports_drawdown_in_r_and_dollars():
    rows = [_row("A", 1.0, 1.0, day="2021-01-04"), _row("B", -2.0, -2.0, day="2021-01-05"),
            _row("C", 0.5, 0.5, day="2021-01-06")]
    book = mrg.summarise(rows, n_resamples=50)["book"]["off"]
    assert book["total_r"] == pytest.approx(-0.5)
    assert book["max_drawdown_r"] == pytest.approx(2.0)
    assert book["max_drawdown_dollars"] == pytest.approx(200.0)


def test_main_refuses_a_second_look(tmp_path, capsys):
    (tmp_path / "train-close.json").write_text("{}", encoding="utf-8")
    assert mrg.main(["--out-dir", str(tmp_path), "--basis", "close"]) == 1
    assert "refused:one-look" in capsys.readouterr().err


def test_main_refuses_zero_frictions(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 0.0)
    assert mrg.main(["--out-dir", str(tmp_path)]) == 1
    assert "refused:zero-frictions" in capsys.readouterr().err


def test_main_refuses_a_smoke_run_into_the_committed_directory(capsys):
    assert mrg.main(["--tickers", "AAA"]) == 1
    assert "refused:smoke-run" in capsys.readouterr().err


def test_main_writes_frozen_block_and_summary(tmp_path, monkeypatch):
    rows = [_row(t, 1.0, 1.1) for t in "ABCD"]
    monkeypatch.setattr(mrg, "build_rows", lambda basis, **kw: rows)
    monkeypatch.setattr(mrg.training_data, "select", lambda name=None: name)
    monkeypatch.setattr(mrg.training_data, "write_provenance", lambda path: path)
    assert mrg.main(["--out-dir", str(tmp_path), "--resamples", "50"]) == 0
    blob = json.loads((tmp_path / "train-close.json").read_text(encoding="utf-8"))
    assert blob["frozen"]["window"] == ["2020-01-01", "2023-12-31"]
    assert blob["frozen"]["data_source"] == "yfinance"
    assert blob["frozen"]["basis"] == "close" and blob["frozen"]["pct"] == 5.0
    assert blob["summary"]["primary"]["verdict"] == "PASS"
