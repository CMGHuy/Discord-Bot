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
