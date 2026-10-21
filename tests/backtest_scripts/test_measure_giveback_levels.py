"""v178 measurement script: arms, entries, rows (V178-5) and stages (V178-6).

Frame: v176's run-up-and-reversal (tests/planning/test_exit_sim_giveback.py),
entry 100 at bar 0's close, stop 95, TP1 110 touched on bar 1, bar 2 closes
at the best 120, bar 3 trades down to 113, bar 4 to 106. The chandelier is
parked (trail_atr_mult 50). ATR(14) is pinned flat by monkeypatching
indicators.atr (exit_sim imports it at call time), so every level is
hand-derived: R k -> 120 - 2k, S f -> 120 - max(20 f, 2).
"""
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.arms.windows import STAGES, VALIDATION_START
from swingbot.core.market import indicators
from swingbot.core.planning import exit_sim
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import measure_giveback_levels as mgl  # noqa: E402

FLOOR = 100.0 + (2.0 / 3.0) * 10.0
BARS = [100.0, (100.0, 111.0, 99.5, 110.5), (110.5, 121.0, 110.0, 120.0),
        (120.0, 120.5, 113.0, 113.5), (113.5, 114.0, 106.0, 106.5)]
ROW_KEYS = {"ticker", "source", "strategy", "horizon_key", "direction", "signal_date",
            "planned_rr", "risk", "runner_fraction", "regime", "arms"}
ARM_KEYS = {"outcome", "r_net", "runner_r", "entry_index", "exit_index", "exit_date",
            "exit_price", "reason", "stop_source", "tp1_index", "best", "best_index",
            "allowance_pct", "floor_bound", "stop_moves", "gap_r", "new_best_within_10", "shock"}


def _flat(value):
    return lambda df, period=14: pd.Series(value, index=df.index, dtype=float)


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
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "close")
    monkeypatch.setattr(exit_sim, "GIVEBACK_MODE", "pct")
    monkeypatch.setattr(exit_sim, "GIVEBACK_K", 1.0)
    monkeypatch.setattr(exit_sim, "GIVEBACK_F", 0.33)
    monkeypatch.setattr(indicators, "adx", _flat(float("nan")))


@pytest.fixture
def flat_atr(monkeypatch):
    monkeypatch.setattr(indicators, "atr", _flat(2.0))


def _one_entry(monkeypatch, plan=None, *, copies=1, seen=None):
    plan = plan or _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None,
                         trail_atr_mult=50.0)

    def fake_entries(ticker, df, window):
        if seen is not None:
            seen.append((df, window))
        return [("strategy", "2w", 0, plan)] * copies
    monkeypatch.setattr(mgl, "_entries", fake_entries)


def _rows(tmp_path, **kw):
    return mgl.rows_for("AAA", make_ohlcv(BARS, start="2021-01-04"), stage="train",
                        basis="close", earnings_dir=tmp_path, **kw)


def test_arm_settings_sets_each_arm_and_restores():
    with mgl.arm_settings("R0.75"):
        assert (exit_sim.GIVEBACK_MODE, exit_sim.GIVEBACK_K) == ("range", 0.75)
        assert config.RUNNER_GIVEBACK_ENABLED is True
    with mgl.arm_settings("S0.50"):
        assert (exit_sim.GIVEBACK_MODE, exit_sim.GIVEBACK_F) == ("profit_share", 0.50)
    with mgl.arm_settings("B"):
        assert config.RUNNER_GIVEBACK_ENABLED is False
    assert (exit_sim.GIVEBACK_MODE, exit_sim.GIVEBACK_K, exit_sim.GIVEBACK_F) == ("pct", 1.0, 0.33)
    assert config.RUNNER_GIVEBACK_ENABLED is True and config.RUNNER_GIVEBACK_PCT == 5.0
    with pytest.raises(KeyError):
        with mgl.arm_settings("R0.50"):
            pass


def test_windows_come_from_the_arms_stage_table():
    assert mgl.stage_window("pilot") == tuple(STAGES["pilot"].signal_window)
    assert mgl.stage_window("train") == (STAGES["selection"].signal_window[0],
                                         STAGES["walkforward"].signal_window[1])
    assert mgl.stage_window("validation") == tuple(STAGES["validation"].signal_window)
    assert mgl.frame_end("pilot") == mgl.frame_end("train") == STAGES["walkforward"].signal_window[1]
    assert mgl.frame_end("train") < VALIDATION_START
    assert mgl.frame_end("validation") == STAGES["validation"].signal_window[1]
    with pytest.raises(ValueError):
        mgl.stage_window("report")


@pytest.mark.parametrize("arm, exit_index, exit_price, source", [
    ("A", 3, 114.0, "giveback"),        # 5% of 120
    ("B", 4, FLOOR, "floor"),           # give-back off: the floor
    ("R0.75", 3, 118.5, "giveback"),    # 120 - 0.75 x 2
    ("R1.00", 3, 118.0, "giveback"),
    ("R1.25", 3, 117.5, "giveback"),
    ("S0.25", 3, 115.0, "giveback"),    # 120 - max(5.0, 2)
    ("S0.33", 3, 113.4, "giveback"),    # 120 - max(6.6, 2); bar 3's low 113 reaches it
    ("S0.50", 4, 110.0, "giveback"),    # 120 - max(10, 2); carried to bar 4
])
def test_every_arm_exits_at_its_hand_derived_level(monkeypatch, tmp_path, flat_atr,
                                                   arm, exit_index, exit_price, source):
    _one_entry(monkeypatch)
    [row] = _rows(tmp_path)
    result = row["arms"][arm]
    assert result["exit_index"] == exit_index
    assert result["exit_price"] == pytest.approx(exit_price)
    assert result["stop_source"] == source
    assert result["outcome"] == "win"


def test_rows_carry_the_contract_fields(monkeypatch, tmp_path, flat_atr):
    _one_entry(monkeypatch)
    [row] = _rows(tmp_path)
    assert set(row) == ROW_KEYS and set(row["arms"]) == set(mgl.ARM_IDS)
    assert all(set(result) == ARM_KEYS for result in row["arms"].values())
    assert (row["source"], row["strategy"], row["horizon_key"]) == ("strategy", "Fibonacci", "2w")
    assert row["signal_date"] == "2021-01-04" and row["regime"] is None
    assert row["risk"] == pytest.approx(5.0) and row["runner_fraction"] == pytest.approx(0.5)
    assert row["planned_rr"] == pytest.approx(2.0)
    a = row["arms"]["A"]
    assert (a["tp1_index"], a["best"], a["best_index"]) == (1, 120.0, 2)
    assert a["allowance_pct"] == pytest.approx(0.05) and a["floor_bound"] is None
    assert a["stop_moves"] == 1 and a["gap_r"] == 0.0           # bar 3 opened at 120 > 114
    assert a["new_best_within_10"] is False                     # 106.5 after the exit
    assert a["shock"] is True                                   # bar 1 TR 11.5 > 2 x ATR 2.0


def test_rows_carry_per_arm_allowances_and_net_r(monkeypatch, tmp_path, flat_atr):
    _one_entry(monkeypatch)
    [row] = _rows(tmp_path)
    a = row["arms"]["A"]
    assert row["arms"]["B"]["allowance_pct"] is None and row["arms"]["B"]["stop_moves"] == 0
    assert row["arms"]["R1.00"]["allowance_pct"] == pytest.approx(2.0 / 120.0)
    assert row["arms"]["S0.25"]["allowance_pct"] == pytest.approx(5.0 / 120.0)
    assert row["arms"]["S0.25"]["floor_bound"] is False
    # net of 5 bps per fill: the entry fill 100.05 re-bases risk to 5.05; leg 1 cancels
    assert a["r_net"] - row["arms"]["B"]["r_net"] == pytest.approx(
        0.5 * (114.0 - FLOOR) * 0.9995 / 5.05)
    assert config.RUNNER_GIVEBACK_ENABLED is True and exit_sim.GIVEBACK_MODE == "pct"


def test_the_floor_binds_on_a_wide_atr(monkeypatch, tmp_path):
    monkeypatch.setattr(indicators, "atr", _flat(10.0))
    _one_entry(monkeypatch)
    [row] = _rows(tmp_path)
    s = row["arms"]["S0.25"]                                    # max(5, 10) = 10 -> 110
    assert s["exit_price"] == pytest.approx(110.0) and s["floor_bound"] is True


def test_no_atr_means_no_term_so_an_adaptive_arm_rides_like_control_b(monkeypatch, tmp_path):
    _one_entry(monkeypatch)                                     # 5 bars: ATR(14) is NaN
    [row] = _rows(tmp_path)
    for arm in ("R1.00", "S0.33"):
        assert row["arms"][arm]["exit_index"] == row["arms"]["B"]["exit_index"] == 4
        assert row["arms"][arm]["exit_price"] == pytest.approx(FLOOR)
        assert row["arms"][arm]["allowance_pct"] is None


@pytest.mark.parametrize("adx, expected", [(25.0, "trend"), (20.0, "trend"), (15.0, "chop")])
def test_regime_reads_adx_at_the_signal_bar(monkeypatch, tmp_path, flat_atr, adx, expected):
    monkeypatch.setattr(indicators, "adx", _flat(adx))
    _one_entry(monkeypatch)
    [row] = _rows(tmp_path)
    assert row["regime"] == expected


def test_shock_reads_earnings_bars_and_true_range_against_the_previous_atr():
    calm = {"reactions": [], "atr": np.array([2.0] * 6), "tr": np.array([1.0] * 6)}
    assert mgl.shock(calm, 1, 4) is False
    assert mgl.shock(dict(calm, reactions=[3]), 1, 4) is True
    assert mgl.shock(dict(calm, reactions=[5]), 1, 4) is False   # after the exit bar
    spike = dict(calm, tr=np.array([1.0, 1.0, 4.5, 1.0, 1.0, 1.0]))
    assert mgl.shock(spike, 1, 4) is True                         # 4.5 > 2.0 x 2.0


@pytest.mark.parametrize("timing, expected", [("before_open", [1]), ("after_close", [2])])
def test_reaction_indices_map_reports_to_frame_bars(tmp_path, timing, expected):
    (tmp_path / "AAA.csv").write_text(
        f"report_date,timing,report_ts_et\n2021-01-05,{timing},\n", encoding="utf-8")
    df = make_ohlcv(BARS, start="2021-01-04")
    assert mgl.reaction_indices("AAA", df, tmp_path) == expected


def test_an_entry_control_a_never_filled_is_dropped(monkeypatch, tmp_path, flat_atr):
    _one_entry(monkeypatch, _plan(entry_type="stop_entry", trigger_price=200.0, stop_loss=95.0,
                                  tp1=110.0, tp2=None, trail_atr_mult=50.0))
    assert _rows(tmp_path) == []


def test_duplicate_pairing_keys_get_a_suffix(monkeypatch, tmp_path, flat_atr):
    _one_entry(monkeypatch, copies=3)
    rows = _rows(tmp_path)
    assert [r["strategy"] for r in rows] == ["Fibonacci", "Fibonacci#2", "Fibonacci#3"]


def test_no_bar_on_or_after_validation_start_reaches_a_train_row(monkeypatch, tmp_path):
    seen = []
    _one_entry(monkeypatch, seen=seen)
    mgl.rows_for("AAA", make_ohlcv(BARS * 3, start="2023-12-20"), stage="train",
                 basis="close", earnings_dir=tmp_path)
    df, window = seen[0]
    assert str(df.index[-1].date()) <= mgl.frame_end("train") < VALIDATION_START
    assert window == mgl.stage_window("train")


def test_rows_refuse_an_unknown_basis_and_arms_without_control_a(tmp_path):
    df = make_ohlcv(BARS, start="2021-01-04")
    with pytest.raises(ValueError, match="basis"):
        mgl.rows_for("AAA", df, stage="train", basis="open", earnings_dir=tmp_path)
    with pytest.raises(ValueError, match="control A"):
        mgl.rows_for("AAA", df, stage="train", basis="close", arms=("B", "R1.00"),
                     earnings_dir=tmp_path)


def test_rows_round_trip_gzipped(tmp_path):
    rows = [{"ticker": "AAA", "arms": {"A": {"r_net": 1.25}}}]
    path = mgl.write_rows(tmp_path / "sub" / "rows-train-close.json.gz", rows)
    assert mgl.read_rows(path) == rows
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert json.load(handle) == rows
    assert not list(path.parent.glob("*.tmp"))


def test_parse_args_refuses_instrument_v2():
    with pytest.raises(SystemExit, match="not wired"):
        mgl.parse_args(["--stage", "pilot", "--instrument", "v2"])


# --- V178-6: stages, refusals, report, validation file ----------------------

DELTAS = (0.001, 0.004, 0.002, -0.001, 0.003, 0.0)          # R0.75 .. S0.50


def _arm(r, *, moved=False):
    return {"outcome": "win", "r_net": r, "runner_r": r, "entry_index": 0,
            "exit_index": 6 if moved else 5, "exit_date": "2019-03-08",
            "exit_price": 1.5 if moved else 1.0, "reason": "runner_trail",
            "stop_source": "giveback", "tp1_index": 1, "best": 2.0, "best_index": 2,
            "allowance_pct": 0.05, "floor_bound": None, "stop_moves": 1, "gap_r": 0.0,
            "new_best_within_10": False, "shock": False}


def _row(ticker, *, moved=(), lift=0.0, arms=None):
    return {"ticker": ticker, "source": "strategy", "strategy": "Fibonacci", "horizon_key": "2w",
            "direction": "bullish", "signal_date": "2019-03-01", "planned_rr": 2.0, "risk": 5.0,
            "runner_fraction": 0.5, "regime": "trend",
            "arms": {a: _arm(1.0 + (lift if a in moved else 0.0), moved=a in moved)
                     for a in (arms or mgl.ARM_IDS)}}


def _funnel(*, resolvable=(), stage3=None):
    stage0 = {a: {"delta_r": d, "p": 0.3, "n": 10, "changed": 3,
                  "verdict": "RESOLVABLE" if a in resolvable else "REFUSED"}
              for a, d in zip(mgl.funnel.CANDIDATES, DELTAS)}
    return {"stage0": stage0, "stage1": {}, "stage2": {}, "stage3_arm": stage3,
            "stopped_at": None if stage3 else "stage0",
            "holm": dict.fromkeys(mgl.funnel.CANDIDATES, 1.0), "week_interval": {}}


def _put(path, blob):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob), encoding="utf-8")


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    out, rows, earnings = tmp_path / "out", tmp_path / "rows", tmp_path / "earnings"
    earnings.mkdir()
    (earnings / "AAA.csv").write_text("report_date,timing,report_ts_et\n", encoding="utf-8")
    monkeypatch.setattr(mgl.training_data, "select", lambda name=None: name)
    monkeypatch.setattr(mgl.training_data, "write_provenance", lambda path: path)
    return out, rows, earnings


def _main(dirs, *argv):
    out, rows, earnings = dirs
    return mgl.main([*argv, "--out-dir", str(out), "--rows-dir", str(rows),
                     "--earnings-dir", str(earnings)])


def _pilot(dirs, survivors=mgl.funnel.CANDIDATES):
    _put(dirs[0] / "pilot-close.json", {"survivors": list(survivors)})


def test_main_refuses_zero_frictions(dirs, monkeypatch, capsys):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 0.0)
    assert _main(dirs, "--stage", "pilot") == 1
    assert "refused:zero-frictions" in capsys.readouterr().err


def test_main_refuses_a_smoke_run_into_the_committed_directories(capsys):
    assert mgl.main(["--stage", "pilot", "--tickers", "AAA"]) == 1
    assert "refused:smoke-run" in capsys.readouterr().err


def test_main_refuses_an_empty_earnings_directory(tmp_path, capsys):
    assert mgl.main(["--stage", "pilot", "--out-dir", str(tmp_path / "o"), "--rows-dir",
                     str(tmp_path / "r"), "--earnings-dir", str(tmp_path)]) == 1
    assert "refused:no-earnings" in capsys.readouterr().err


def test_pilot_reports_reachability_per_candidate_and_is_one_look(dirs, monkeypatch, capsys):
    rows = [_row(t, moved=("R0.75",), lift=0.1) for t in "ABC"]
    monkeypatch.setattr(mgl, "build_rows", lambda stage, basis, **kw: rows)
    assert _main(dirs, "--stage", "pilot") == 0
    blob = json.loads((dirs[0] / "pilot-close.json").read_text(encoding="utf-8"))
    assert blob["arms"]["R0.75"] == {"changed": 3, "verdict": "REACHABLE"}
    assert blob["arms"]["S0.50"] == {"changed": 0, "verdict": "refused:zero-diff"}
    assert blob["survivors"] == ["R0.75"] and blob["frozen"]["window"] == list(mgl.stage_window("pilot"))
    assert mgl.read_rows(dirs[1] / "rows-pilot-close.json.gz") == rows
    assert _main(dirs, "--stage", "pilot") == 1
    assert "refused:one-look" in capsys.readouterr().err


def test_a_pilot_without_changed_outcomes_closes_every_candidate(dirs, monkeypatch):
    monkeypatch.setattr(mgl, "build_rows", lambda stage, basis, **kw: [_row("A")])
    assert _main(dirs, "--stage", "pilot") == 1
    assert json.loads((dirs[0] / "pilot-close.json").read_text(encoding="utf-8"))["survivors"] == []


def test_train_needs_a_pilot_survivor(dirs, capsys):
    assert _main(dirs, "--stage", "train") == 1
    assert "refused:no-pilot" in capsys.readouterr().err
    _pilot(dirs, survivors=())
    assert _main(dirs, "--stage", "train") == 1
    assert "refused:pilot-closed-everything" in capsys.readouterr().err


def test_train_writes_the_rows_file_and_nothing_else(dirs, monkeypatch):
    seen, rows = [], [_row("A")]
    monkeypatch.setattr(mgl, "build_rows", lambda stage, basis, **kw: seen.append((stage, basis)) or rows)
    _pilot(dirs)
    assert _main(dirs, "--stage", "train") == 0
    assert seen == [("train", "close")]
    assert mgl.read_rows(dirs[1] / "rows-train-close.json.gz") == rows
    assert not (dirs[0] / "funnel-close.json").exists()


@pytest.mark.parametrize("stage", ["train", "report"])
def test_high_low_is_refused_when_every_arm_was_refused_at_stage_0(dirs, capsys, stage):
    _pilot(dirs)
    _put(dirs[0] / "funnel-close.json", {"funnel": _funnel()})
    mgl.write_rows(dirs[1] / "rows-train-high_low.json.gz", [_row("A")])
    assert _main(dirs, "--stage", stage, "--basis", "high_low") == 1
    assert "refused:no-sensitivity" in capsys.readouterr().err


def test_report_close_runs_the_funnel_and_describes_every_candidate(dirs, monkeypatch):
    _pilot(dirs)
    mgl.write_rows(dirs[1] / "rows-train-close.json.gz", [_row("A")])
    monkeypatch.setattr(mgl.funnel, "run_funnel", lambda rows, n_resamples: _funnel())
    monkeypatch.setattr(mgl.blocks, "describe_arm",
                        lambda rows, arm, risk_dollars: {"1_book": arm, "regime": "dropped"})
    monkeypatch.setattr(mgl.blocks, "regime_split", lambda rows, arm: f"regime-{arm}")
    assert _main(dirs, "--stage", "report", "--resamples", "50") == 0
    blob = json.loads((dirs[0] / "funnel-close.json").read_text(encoding="utf-8"))
    assert list(blob["blocks"]) == list(mgl.funnel.CANDIDATES)
    assert blob["regime_arms"] == ["R1.00", "S0.33"]              # each family's best stage-0 delta
    assert "regime" not in blob["blocks"]["R0.75"]
    assert blob["blocks"]["R1.00"]["regime"] == "regime-R1.00"
    summary = blob["summary"]
    assert (summary["best_arm"], summary["ledger_p"], summary["stopped_at"]) == ("R1.00", 0.3, "stage0")
    assert summary["cells_looked_at"] == mgl.funnel.cells_looked_at()


def test_report_drops_a_stage3_arm_the_pilot_refused(dirs, monkeypatch):
    _pilot(dirs, survivors=("R0.75", "S0.33"))
    mgl.write_rows(dirs[1] / "rows-train-close.json.gz", [_row("A")])
    monkeypatch.setattr(mgl.funnel, "run_funnel", lambda rows, n_resamples: _funnel(stage3="R1.00"))
    monkeypatch.setattr(mgl.blocks, "describe_arm", lambda rows, arm, risk_dollars: {})
    monkeypatch.setattr(mgl.blocks, "regime_split", lambda rows, arm: {})
    assert _main(dirs, "--stage", "report") == 0
    blob = json.loads((dirs[0] / "funnel-close.json").read_text(encoding="utf-8"))
    assert blob["funnel"]["stage3_arm"] is None and "R1.00" in blob["funnel"]["pilot_refused"]


def test_report_high_low_reads_only_the_sensitivity_arms(dirs, monkeypatch):
    _pilot(dirs)
    _put(dirs[0] / "funnel-close.json", {"funnel": _funnel(resolvable=("R1.00",))})
    mgl.write_rows(dirs[1] / "rows-train-high_low.json.gz", [_row("A")])
    seen = []
    monkeypatch.setattr(mgl.funnel, "stage0", lambda rows, arm, n_resamples: seen.append(arm) or {})
    monkeypatch.setattr(mgl.funnel, "stage2", lambda rows, arm: {})
    assert _main(dirs, "--stage", "report", "--basis", "high_low") == 0
    blob = json.loads((dirs[0] / "sensitivity-high_low.json").read_text(encoding="utf-8"))
    assert seen == blob["summary"]["arms"] == ["R0.75", "R1.00", "S0.33"]
    assert blob["summary"]["cells_looked_at"] == mgl.funnel.cells_looked_at(sensitivity=18)


def test_validation_refuses_anything_but_the_stage3_arm_with_a_preregistration(dirs, tmp_path, capsys):
    assert _main(dirs, "--stage", "validation") == 1
    assert "refused:no-arm" in capsys.readouterr().err
    assert _main(dirs, "--stage", "validation", "--arm", "R1.00") == 1
    assert "refused:no-preregistration" in capsys.readouterr().err
    spec = tmp_path / "spec.md"
    spec.write_text("frozen", encoding="utf-8")
    _put(dirs[0] / "funnel-close.json", {"funnel": _funnel(stage3="R1.00")})
    assert _main(dirs, "--stage", "validation", "--arm", "S0.33", "--preregistration", str(spec)) == 1
    assert "refused:not-the-stage3-arm" in capsys.readouterr().err


def test_validation_writes_the_component_file_and_the_fixed_readings(dirs, tmp_path, monkeypatch, capsys):
    import validate_component
    spec = tmp_path / "spec.md"
    spec.write_text("frozen", encoding="utf-8")
    _put(dirs[0] / "funnel-close.json", {"funnel": _funnel(stage3="R1.00")})
    rows = [_row(t, moved=("R1.00",), lift=0.1, arms=("A", "B", "R1.00")) for t in "ABCDEF"]
    seen = []
    monkeypatch.setattr(mgl, "build_rows",
                        lambda stage, basis, arms, **kw: seen.append((stage, arms)) or rows)
    for name in ("seven_blocks", "per_horizon", "concentration", "regime_split", "flips"):
        monkeypatch.setattr(mgl.blocks, name, lambda *a, **k: {})
    argv = ("--stage", "validation", "--arm", "R1.00", "--preregistration", str(spec),
            "--resamples", "50")
    assert _main(dirs, *argv) == 0
    assert seen == [("validation", ("A", "B", "R1.00"))]
    baseline, component = validate_component.load_arms(dirs[1] / "validation-arms.json")
    assert len(baseline) == len(component) == 6
    assert component[0].r_multiple == pytest.approx(1.1)
    blob = json.loads((dirs[1] / "validation-arms.json").read_text(encoding="utf-8"))
    assert blob["provenance"]["bespoke"] == mgl.BESPOKE_REASON
    readings = json.loads((dirs[0] / "validation-readings.json").read_text(encoding="utf-8"))
    assert {"arm_vs_a", "a_vs_b", "arm_vs_b", "week_interval", "permutation_p"} <= set(readings)
    assert readings["changed"] == 6 and readings["frozen"]["window"] == list(mgl.stage_window("validation"))
    assert _main(dirs, *argv) == 1
    assert "refused:one-look" in capsys.readouterr().err


def test_a_ticker_listed_after_the_stage_ends_has_no_rows(tmp_path):
    df = make_ohlcv(BARS, start="2031-01-04")                   # every bar is past the frame end
    assert mgl.rows_for("NEW", df, stage="train", basis="close", earnings_dir=tmp_path) == []
