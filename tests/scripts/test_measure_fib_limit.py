"""v131 funnel logic -- no market data: synthetic rows and a fake backtest."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_fib_limit as mf  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.market.entry_filters import DEFAULT_PARAMS  # noqa: E402
from swingbot.core.market.strategy_types import FIB_LIMIT, LEGACY_HORIZONS, STRATEGY_GATES, admits  # noqa: E402
from swingbot.core.planning.params import PLAN_SHAPES  # noqa: E402
from tests.helpers import make_ohlcv  # noqa: E402

FAST = dict(n_resamples=200, seed=42)
PREREG = "docs/superpowers/results/2026-10-05-v131-preregistration.md"


# --- fixtures -------------------------------------------------------------------

def _frame():
    """Daily bars 2025-12-01 .. 2026-02-20: straddles the TRAIN / holdout line."""
    return make_ohlcv([100.0] * 60, start="2025-12-01")


def _trade(frame, signal, exit_, *, outcome="win", r=1.5, entry=98.0, stop=97.0, target=100.0):
    return SimpleNamespace(direction="bullish", entry_date=str(frame.index[signal].date()),
                           exit_date=str(frame.index[exit_].date()), outcome=outcome, r_multiple=r,
                           entry=entry, stop_loss=stop, take_profit=target,
                           context={"stop_pct": 2.0, "planned_rr": 1.0, "stop_atr": 9.9, "rsi_14": 40.0})


def _order(frame, signal, fill, status="filled", new_high=False):
    filled = status == "filled"
    return {"signal_date": str(frame.index[signal].date()), "limit_price": 98.0, "cancel_level": 105.0,
            "status": status, "fill_date": str(frame.index[fill].date()) if filled else None,
            "fill_price": 98.0 if filled else None, "same_bar_new_high": new_high if filled else None}


def _fake_run(frame):
    """Two fills (one stopped out on bar fill+2, one in 2026), one expiry, one cancel."""
    trades = [_trade(frame, 5, 9, outcome="loss", r=-1.0), _trade(frame, 30, 40), _trade(frame, 45, 50)]
    orders = [_order(frame, 5, 7), _order(frame, 12, None, "expired"),
              _order(frame, 20, None, "cancelled"), _order(frame, 30, 31, new_high=True),
              _order(frame, 45, 46)]

    def run(ticker, df, strategy, horizon, **kwargs):
        assert kwargs == dict(one_at_a_time=True, exit_model="v2", scale_out=True,
                              tp2_mode="levels", frictions=True, asof=None)
        if strategy == FIB_LIMIT:
            return SimpleNamespace(trades=list(trades), limit_orders=list(orders))
        return SimpleNamespace(trades=[_trade(frame, 5, 6, outcome="loss", r=-1.0, entry=100.0, stop=98.0)],
                               limit_orders=[])
    return run


def _rows(years, per_year, win_share, *, tickers=8, horizon="2w"):
    rows = []
    for year in years:
        wins = round(per_year * win_share)
        for i in range(per_year):
            win = i < wins
            rows.append({"ticker": f"T{i % tickers}", "horizon_key": horizon, "direction": "bullish",
                         "entry_date": f"{year}-06-01", "outcome": "win" if win else "loss",
                         "r_multiple": 1.0 if win else -1.0, "early_stop": False, "cap_bound": True})
    return rows


def _merged(cell_rows, reference, universe_n=74):
    return {"universe_n": universe_n, "reference": reference,
            "cells": {key: {"rows": cell_rows.get(key, []), "orders": {"placed": 0}} for key in mf.CELLS}}


# --- Task V131-06: constants, cells, rows, Stage 0, reproduction --------------------

def test_preregistered_constants():
    assert mf.TRAIN == ("2010-01-01", "2025-12-31") and mf.HOLDOUT_START == "2026-01-01"
    assert mf.REPRO_WINDOW == ("2010-01-01", "2023-12-31")
    assert mf.V103_REFERENCE == {"n": 815, "win_rate": 36.81, "expectancy_r": 0.2219, "universe_n": 73}
    assert mf.FOLD_YEARS == tuple(range(2013, 2026)) and mf.THIN_REOPEN == "2026-12-31"
    assert mf.ALL_HZ == tuple(LEGACY_HORIZONS) and len(mf.ALL_HZ) == 10
    assert mf.CELLS == ("L0.5|N3", "L0.5|N5", "L0.5|N10", "L0.618|N3", "L0.618|N5", "L0.618|N10")
    assert mf.LOOSEST_KEY == "L0.5|N10" and mf.STAGE0_MIN_FILLS == 30
    assert (mf.FILLS_SHARE, mf.WR_SLACK_PP, mf.MIN_HOLDOUT_FILLS) == (0.5, 2.0, 15)
    assert mf.RR_BAND == (1.5, 2.5) and mf.EARLY_STOP_BARS == 3 and mf.TOP2_LINE == 0.8


def test_cell_sets_l_n_expiry_and_unmasks_then_restores():
    before = (dict(DEFAULT_PARAMS[FIB_LIMIT]), PLAN_SHAPES[FIB_LIMIT]["expiry_bars"])
    with mf.cell("L0.5|N10"):
        assert DEFAULT_PARAMS[FIB_LIMIT] == {"L": 0.5, "N": 10}
        assert PLAN_SHAPES[FIB_LIMIT]["expiry_bars"] == 10
        assert admits(FIB_LIMIT, "bullish", "2w") and not admits(FIB_LIMIT, "bearish", "2w")
    assert (DEFAULT_PARAMS[FIB_LIMIT], PLAN_SHAPES[FIB_LIMIT]["expiry_bars"]) == before
    assert STRATEGY_GATES[FIB_LIMIT] == {"directions": ()}


def test_preregistration_must_be_named_and_committed(monkeypatch):
    seen = []
    monkeypatch.setattr(mf, "require_committed", seen.append)
    with pytest.raises(SystemExit):
        mf.require_preregistration("docs/superpowers/results/2026-10-05-v130-preregistration.md")
    mf.require_preregistration(PREREG)
    assert seen == [PREREG]


def test_frozen_config_is_enforced(monkeypatch):
    mf.require_frozen_config()
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 3.0)
    with pytest.raises(SystemExit):
        mf.require_frozen_config()


def test_cell_rows_score_fills_and_count_orders_inside_the_window():
    frame = _frame()
    out = mf.cell_rows("L0.5|N10", {"T": frame}, {}, "2w", mf.TRAIN, run_fn=_fake_run(frame))
    [row] = out["rows"]                         # the two 2026 fills are outside TRAIN
    assert (row["entry_date"], row["fill_date"]) == (str(frame.index[5].date()), str(frame.index[7].date()))
    assert (row["signal_index"], row["fill_index"], row["limit_price"], row["fill_price"]) == (5, 7, 98.0, 98.0)
    assert row["early_stop"] is True             # a loss 2 bars after the fill
    assert row["risk_pct"] == pytest.approx(1 / 98 * 100, abs=1e-4)
    assert row["cap_bound"] is False             # 1.02% risk, 2% ceiling
    assert row["context"]["stop_pct"] == pytest.approx(1 / 98 * 100, abs=1e-6)
    assert row["context"]["planned_rr"] == pytest.approx(2.0)
    assert row["context"]["rsi_14"] == 40.0      # every other feature kept as recorded
    assert out["orders"] == {"placed": 3, "filled": 1, "expired": 1, "cancelled": 1, "same_bar_new_high": 0}


def test_holdout_dated_rows_never_reach_a_train_collect():
    frame = _frame()
    collected = mf.collect_horizon({"T": frame}, {}, "2w", mf.TRAIN, run_fn=_fake_run(frame))
    dates = [row["entry_date"] for arm in collected["cells"].values() for row in arm["rows"]]
    dates += [row["entry_date"] for row in collected["reference"]["rows"]]
    assert dates and max(dates) <= mf.TRAIN[1]


def test_the_collect_command_has_no_window_argument():
    with pytest.raises(SystemExit):
        mf._parser().parse_args(["collect", "--out", "x", "--preregistration", PREREG,
                                 "--horizon", "2w", "--window", "2026-01-01"])


def test_reference_rows_use_the_close_and_the_entry_bar():
    frame = _frame()
    [row] = mf.reference_rows({"T": frame}, {}, "2w", mf.TRAIN, run_fn=_fake_run(frame))
    assert row["early_stop"] is True and row["cap_bound"] is True       # 2.0% risk on 2% ceiling
    assert row["risk_pct"] == pytest.approx(2.0)


def _payload(horizon, cell_rows=(), ref_rows=(), universe_n=74):
    return {"horizon": horizon, "universe_n": universe_n, "reference": {"rows": list(ref_rows)},
            "cells": {key: {"rows": list(cell_rows) if key == mf.LOOSEST_KEY else [],
                            "orders": {"placed": len(cell_rows), "filled": len(cell_rows)}}
                      for key in mf.CELLS}}


def _write_collects(tmp_path, per_horizon_rows=0, skip=None):
    paths = []
    for horizon in mf.ALL_HZ:
        if horizon == skip:
            continue
        path = tmp_path / f"{horizon}.json"
        rows = _rows((2015,), per_horizon_rows, 0.5, horizon=horizon)
        path.write_text(json.dumps(_payload(horizon, rows, rows)), encoding="utf-8")
        paths.append(path)
    return paths


def test_load_collects_needs_every_horizon_exactly_once(tmp_path):
    with pytest.raises(SystemExit):
        mf.load_collects(_write_collects(tmp_path, skip="9m"))
    merged = mf.load_collects(_write_collects(tmp_path, per_horizon_rows=3))
    assert len(merged["cells"][mf.LOOSEST_KEY]["rows"]) == 30
    assert merged["cells"][mf.LOOSEST_KEY]["orders"] == {"placed": 30, "filled": 30}


@pytest.mark.parametrize("fills, passes", [(29, False), (30, True)])
def test_stage0_reads_only_the_loosest_cell(fills, passes):
    merged = _merged({mf.LOOSEST_KEY: _rows((2015,), fills, 0.5), "L0.618|N3": _rows((2015,), 500, 1.0)}, [])
    verdict = mf.stage0_verdict(merged)
    assert verdict == {"cell": "L0.5|N10", "fills": fills, "min_fills": 30, "passes": passes}


def test_reproduction_compares_the_2010_2023_slice_with_v103():
    reference = _rows((2015,), 10, 0.5) + _rows((2024, 2025), 50, 1.0)
    out = mf.reproduction(_merged({}, reference, universe_n=73))
    assert out["got"] == {"n": 10, "universe_n": 73, "win_rate": 50.0, "expectancy_r": 0.0}
    assert out["matches"] is False and sum(out["by_ticker"].values()) == 10


def test_disclosures():
    rows = _rows((2015,), 4, 0.5, horizon="2w") + _rows((2015,), 3, 0.5, horizon="4w") \
        + _rows((2015,), 3, 0.5, horizon="2m")
    rows[0]["early_stop"] = True
    out = mf.disclosures(rows, {"placed": 20, "filled": 10})
    assert out["fills"] == 10 and out["fill_rate"] == 0.5
    assert out["early_stop_share"] == 0.1 and out["cap_bind_share"] == 1.0
    assert out["horizon_concentration"]["top2_share"] == 0.7
    assert out["horizon_concentration"]["over_line"] is False
    assert out["total_r"] == sum(row["r_multiple"] for row in rows)


# --- Task V131-07: Stages 1-3 ---------------------------------------------------------

def test_neighbours_are_one_axis_apart():
    assert sorted(mf.neighbours("L0.5|N5")) == ["L0.5|N10", "L0.5|N3", "L0.618|N5"]
    assert sorted(mf.neighbours("L0.618|N10")) == ["L0.5|N10", "L0.618|N5"]


def test_plateau_needs_every_neighbour():
    passes = {key: True for key in mf.CELLS}
    passes["L0.618|N3"] = False
    assert mf.plateau(passes) == ["L0.5|N5", "L0.5|N10", "L0.618|N10"]


# Hand-labelled: reference N(trades)=100, WR 40.0%, ExpR +0.20.
REF = {"win_rate": 40.0, "expectancy_r": 0.20}


@pytest.mark.parametrize("stats, fills, expected", [
    ({"win_rate": 38.0, "expectancy_r": 0.21}, 50, (True, True, True)),     # every edge exactly met
    ({"win_rate": 37.99, "expectancy_r": 0.21}, 50, (True, True, False)),   # WR 2.01pp below
    ({"win_rate": 45.0, "expectancy_r": 0.20}, 80, (False, True, True)),    # ExpR equal is not above
    ({"win_rate": 45.0, "expectancy_r": 0.30}, 49, (True, False, True)),    # 49 < 50% of 100
    ({"win_rate": None, "expectancy_r": None}, 0, (False, False, False)),
])
def test_profit_clause_arithmetic(stats, fills, expected):
    clauses = mf.profit_clauses(stats, fills, REF, 100)
    assert (clauses["a_expr_beats_reference"], clauses["b_fills_half_of_reference"],
            clauses["c_wr_within_2pp"]) == expected


def test_stage1_winner_is_the_highest_expr_tier1_plateau_cell_and_must_beat_the_reference():
    years = (2015, 2016, 2017)
    strong = {key: _rows(years, 20, 0.6) for key in mf.CELLS}            # WR 60, ExpR +0.2
    strong["L0.618|N10"] = _rows(years, 20, 0.7)                         # WR 70, ExpR +0.4
    reference = _rows(years, 20, 0.55)                                   # WR 55, ExpR +0.1
    first = mf.stage1(_merged(strong, reference), **FAST)
    assert (first["winner"], first["winner_tier"]) == ("L0.618|N10", 1)
    assert first["passes"] is True
    better_reference = _rows(years, 20, 0.75)                            # ExpR +0.5 beats every cell
    assert mf.stage1(_merged(strong, better_reference), **FAST)["passes"] is False


def test_stage1_without_a_plateau_has_no_winner():
    cells = {"L0.5|N10": _rows((2015, 2016), 20, 0.7)}                   # one strong cell, no neighbours
    first = mf.stage1(_merged(cells, _rows((2015,), 20, 0.5)), **FAST)
    assert first["winner"] is None and first["passes"] is False and first["profit_clauses"] is None


def test_stage2_reselects_on_prior_years_per_fold():
    years = tuple(range(2010, 2026))
    cells = {key: _rows(years, 40, 0.6) for key in mf.CELLS}
    second = mf.stage2(_merged(cells, []))
    assert [fold["test_year"] for fold in second["folds"]] == list(range(2013, 2026))
    assert all(fold["tol"] in mf.CELLS for fold in second["folds"])
    assert second["verdict"]["clears"] is True and second["verdict"]["qualifying"] == 13


def test_evaluate_closes_at_stage1_and_never_runs_stage2_then():
    out = mf.evaluate(_merged({}, _rows((2015,), 20, 0.5)), **FAST)
    assert (out["closed_at"], out["stage2"], out["proceed_to_holdout"], out["winner"]) == (
        "stage1", None, False, None)
    assert set(out["disclosures"]) == set(mf.CELLS)


def test_evaluate_proceeds_with_the_winner_and_its_tier():
    years = tuple(range(2010, 2026))
    cells = {key: _rows(years, 40, 0.6) for key in mf.CELLS}
    out = mf.evaluate(_merged(cells, _rows(years, 40, 0.55)), **FAST)
    assert out["proceed_to_holdout"] is True and out["closed_at"] is None
    assert out["winner"] in mf.CELLS and out["tier"] == 1


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setattr(mf, "RESULTS", tmp_path)
    return tmp_path


def test_holdout_out_path_must_be_the_ledger(results, tmp_path):
    with pytest.raises(SystemExit):
        mf.check_shot_allowed(tmp_path / "elsewhere.json")
    mf.check_shot_allowed(results / "2026-10-20-v131-holdout.json")


def test_a_scored_shot_is_spent_forever(results):
    (results / "2026-10-20-v131-holdout.json").write_text(json.dumps({"status": "scored"}))
    with pytest.raises(SystemExit):
        mf.check_shot_allowed(results / "2027-06-01-v131-holdout.json", cache_end="2027-05-30")


def test_a_sealed_thin_shot_retries_once_after_the_reopen_date(results):
    (results / "2026-10-20-v131-holdout.json").write_text(json.dumps({"status": "sealed-thin"}))
    with pytest.raises(SystemExit):
        mf.check_shot_allowed(results / "2026-11-20-v131-holdout.json", cache_end="2026-11-19")
    mf.check_shot_allowed(results / "2027-01-05-v131-holdout.json", cache_end="2026-12-31")
    (results / "2027-01-05-v131-holdout.json").write_text(json.dumps({"status": "sealed-thin"}))
    with pytest.raises(SystemExit):
        mf.check_shot_allowed(results / "2027-06-01-v131-holdout.json", cache_end="2027-05-30")


def test_holdout_verdict_sealed_thin_below_15_fills():
    assert mf.holdout_verdict(_rows((2026,), 14, 1.0), [], 1, **FAST) == {"status": "sealed-thin", "fills": 14}


def test_holdout_verdict_tier1_pass_is_validated_tier2_pass_is_weak():
    rows, reference = _rows((2026,), 20, 0.7), _rows((2026,), 20, 0.5)
    tier1 = mf.holdout_verdict(rows, reference, 1, **FAST)
    assert (tier1["status"], tier1["passes"], tier1["badge"]) == ("scored", True, "VALIDATED")
    tier2 = mf.holdout_verdict(rows, reference, 2, **FAST)
    assert (tier2["passes"], tier2["badge"]) == (True, "WEAK")


def test_holdout_verdict_fails_when_the_reference_does_better():
    rows, reference = _rows((2026,), 20, 0.7), _rows((2026,), 20, 0.9)
    out = mf.holdout_verdict(rows, reference, 1, **FAST)
    assert out["clauses"]["a_expr_beats_reference"] is False
    assert (out["passes"], out["badge"]) == (False, None)


def _args(**kw):
    return SimpleNamespace(**kw)


def _json(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


@pytest.fixture
def committed(monkeypatch):
    seen = []
    monkeypatch.setattr(mf, "require_committed", seen.append)
    return seen


def test_evaluate_refuses_a_volume_dead_stage0(tmp_path, committed):
    args = _args(preregistration=PREREG, stage0=_json(tmp_path, "s0.json", {"passes": False}),
                 reproduction=_json(tmp_path, "r.json", {"matches": True}), reproduction_note=None,
                 rows=[], out=str(tmp_path / "e.json"))
    with pytest.raises(SystemExit):
        mf._cmd_evaluate(args)


def test_evaluate_refuses_an_unexplained_reproduction_gap(tmp_path, committed):
    args = _args(preregistration=PREREG, stage0=_json(tmp_path, "s0.json", {"passes": True}),
                 reproduction=_json(tmp_path, "r.json", {"matches": False}), reproduction_note=None,
                 rows=[], out=str(tmp_path / "e.json"))
    with pytest.raises(SystemExit, match="reproduction-note"):
        mf._cmd_evaluate(args)


def test_holdout_refuses_a_mechanism_that_did_not_proceed(tmp_path, committed):
    args = _args(preregistration=PREREG, evaluate=_json(tmp_path, "e.json", {"proceed_to_holdout": False}))
    with pytest.raises(SystemExit):
        mf._holdout_target(args)


def test_emit_writes_one_row_only_for_a_passing_shot(tmp_path, committed):
    registry = tmp_path / "registry.json"
    passing = {"status": "scored", "passes": True, "badge": "WEAK", "preregistration": PREREG,
               "window": ["2026-01-01", "2026-09-28"],
               "stats": {"n": 40, "win_rate": 45.0, "expectancy_r": 0.31}}
    mf._cmd_emit(_args(holdout_json=_json(tmp_path, "h.json", passing), registry=str(registry),
                       run_date="2026-10-20"))
    [row] = json.loads(registry.read_text(encoding="utf-8"))
    assert row == {"source": "strategy", "strategy": FIB_LIMIT, "horizon": None, "status": "WEAK",
                   "n": 40, "win_rate": 45.0, "expectancy_r": 0.31,
                   "window": "2026-01-01..2026-09-28", "run_date": "2026-10-20"}
    for bad in ({"status": "sealed-thin"}, {**passing, "passes": False}):
        with pytest.raises(SystemExit):
            mf._cmd_emit(_args(holdout_json=_json(tmp_path, "bad.json", bad), registry=str(registry),
                               run_date="2026-10-20"))


def test_features_records_every_fill_with_its_context_and_nothing_else(tmp_path, committed):
    import gzip
    paths = _write_collects(tmp_path, per_horizon_rows=0)
    frame = _frame()
    one = mf.cell_rows("L0.5|N10", {"T": frame}, {}, "2w", mf.TRAIN, run_fn=_fake_run(frame))
    payload = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    payload["cells"]["L0.5|N10"]["rows"] = one["rows"]
    Path(paths[0]).write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "fills.json.gz"
    mf._cmd_features(_args(preregistration=PREREG, rows=paths, out=str(out)))
    with gzip.open(out, "rt", encoding="utf-8") as handle:
        written = json.load(handle)
    [row] = written["cells"]["L0.5|N10"]
    assert set(row) == set(mf.FEATURE_ROW_KEYS)
    assert (row["fill_index"], row["fill_price"], row["outcome"]) == (7, 98.0, "loss")
    assert row["context"]["stop_pct"] == pytest.approx(1 / 98 * 100, abs=1e-6)
    assert set(written) == {"window", "universe_n", "cells"}
