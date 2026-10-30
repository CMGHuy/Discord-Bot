"""V191-15/16: the v191 funnel on synthetic band rows. Every clause is scored
on the floor-moved stratum alone; Stage -1 reads plans only; Stage 0 is the
paired dExpR MDE; Stage 1 is the plateau selection with the edge-cell rule."""
import pytest

from swingbot import config
from swingbot.core.backtesting import atr_band_funnel as funnel
from swingbot.core.backtesting.backtest_wf import PLATEAU_TOLERANCE_R
from tests.backtesting.acceptance_rows import record

KEYS = ("k0.75", "k1", "k1.5")
N = 200                     # bootstrap resamples: enough for the synthetic signal


def band_record(ticker, date, outcome, r, *, moved="floor", pnl=None, exceeds=False,
                direction="bullish", horizon="4w"):
    rec = record(ticker, date, outcome, r, horizon=horizon)
    return {**rec, "direction": direction, "fill_beyond_ceiling": False, "stop_moved_by": moved,
            "stop_distance_pct": 4.0 if moved else 1.75, "stop_distance_atr": 1.0 if moved else 0.44,
            "early_stop": False, "gap_overshoot_r": None, "regime2_state": None, "shares": 23.46,
            "dollar_pnl": 100.0 * r if pnl is None else pnl, "dollar_exceeds_budget": exceeds}


def band_row(baseline, cells, *, moved=None, d=1.0, atr=4.0):
    """`baseline` and each `cells` value are band_record() dicts or None."""
    anchor = baseline or next(c for c in cells.values() if c is not None)
    return {"arm": "K", "ticker": anchor["ticker"], "horizon_key": anchor["horizon_key"],
            "entry_date": anchor["entry_date"], "signal_index": 30,
            "direction": anchor["direction"], "d": d, "atr_pct": atr, "adv_dollars": 5e7,
            "baseline": baseline, "cells": cells,
            "moved_by": moved if moved is not None else {key: "floor" for key in cells},
            "newly_admitted": {key: baseline is None and cells[key] is not None for key in cells}}


def lifted_band_rows(lifts, *, jitter=0.0, n_tickers=20, per_ticker=4, year=2021,
                     moved="floor"):
    """n_tickers * per_ticker paired rows. The baseline alternates win (+2R)
    and loss (-1R); each cell keeps the outcome and adds lifts[key], plus
    +jitter on even trades and -jitter on odd ones."""
    rows = []
    for t in range(n_tickers):
        for k in range(per_ticker):
            ticker, date = f"T{t:02d}", f"{year}-{k + 1:02d}-15"
            outcome, base_r = ("win", 2.0) if k % 2 == 0 else ("loss", -1.0)
            wobble = jitter if k % 2 == 0 else -jitter
            cells = {key: band_record(ticker, date, outcome, base_r + lift + wobble, moved=moved)
                     for key, lift in lifts.items()}
            rows.append(band_row(band_record(ticker, date, outcome, base_r, moved=None), cells,
                                 moved={key: moved for key in lifts}))
    return rows


def census_row(moved=("floor", "floor", "floor"), *, in_baseline=True, in_cell=(True, True, True),
               newly=(False, False, False), dropped=(None, None, None),
               size_zero=(False, False, False), reversal=None, d=1.0, atr=4.0, ticker="T00",
               date="2021-01-15", life_end="2021-02-22", horizon="4w", direction="bullish"):
    return {"arm": "K", "ticker": ticker, "horizon_key": horizon, "entry_date": date,
            "signal_index": 30, "direction": direction, "d": d, "atr_pct": atr,
            "adv_dollars": 5e7, "in_baseline": in_baseline, "life_end_date": life_end,
            "in_cell": dict(zip(KEYS, in_cell)), "moved_by": dict(zip(KEYS, moved)),
            "newly_admitted": dict(zip(KEYS, newly)), "dropped": dict(zip(KEYS, dropped)),
            "size_zero": dict(zip(KEYS, size_zero)),
            "reversal": None if reversal is None else dict(zip(KEYS, reversal))}


# --- constants and the stratum -----------------------------------------------------------

def test_the_frozen_block():
    assert funnel.FOLD_TRAIN == ("2018-06-01", "2022-12-31")
    assert funnel.VALIDATION == ("2024-01-01", "2025-12-31")
    assert funnel.FOLD_YEARS == (2021, 2022, 2023)
    assert funnel.FOLD_2023 == ("2023-01-01", "2023-12-31")
    assert (funnel.MIN_FOLD_N, funnel.MIN_POSITIVE_FOLDS) == (30, 2)
    assert (funnel.MDE_CEILING_R, funnel.MDE_POWER) == (0.10, 0.80)
    assert (funnel.CLUSTER, funnel.INSTRUMENT, funnel.DATA_SOURCE) == ("week", "v1", "alpaca")
    assert funnel.HOLM_ALPHA == 0.05
    assert PLATEAU_TOLERANCE_R == 0.03          # reused unchanged (index § Global Constraints)


def test_floor_moved_keeps_only_the_floor_stratum():
    rows = (lifted_band_rows({"k1": 0.3}, n_tickers=2, moved="floor")
            + lifted_band_rows({"k1": 0.3}, n_tickers=2, moved="untouched")
            + lifted_band_rows({"k1": 0.3}, n_tickers=2, moved="ceiling"))
    assert len(funnel.floor_moved(rows, "k1")) == 8
    assert all(r["moved_by"]["k1"] == "floor" for r in funnel.floor_moved(rows, "k1"))


# --- Stage -1 ------------------------------------------------------------------------------

def test_stage_minus1_reachable_cells_and_counts():
    rows = [census_row(("floor", "floor", "floor"), ticker="T01"),
            census_row(("untouched", "floor", "floor"), ticker="T02", d=3.5),
            census_row(("untouched", "untouched", "floor"), ticker="T03", d=4.5),
            census_row(("floor", "floor", "floor"), in_baseline=False, newly=(True, True, True),
                       ticker="T04", d=0.8),
            census_row(("floor", "floor", "floor"), in_cell=(False, False, False),
                       dropped=("band_rr_drop",) * 3, ticker="T05", d=1.5),
            census_row(("ceiling", "ceiling", "untouched"), ticker="T06", d=9.0),
            census_row((None, None, None), ticker="T07", reversal=(False, True, True))]
    out = funnel.stage_minus1(rows, "K")
    assert out["verdict"] == "REACHABLE" and out["reachable_cells"] == [0.75, 1.0, 1.5]
    k1 = out["totals"]["cells"]["k1"]
    assert (k1["floor"], k1["ceiling"], k1["untouched"]) == (3, 1, 1)
    assert (k1["newly_admitted"], k1["band_rr_drop"], k1["band_no_target"]) == (1, 1, 0)
    assert k1["removed"] == 1 and k1["reversal"] == 1 and k1["baseline_stop_exits"] == 1
    assert out["totals"]["plans_today"] == 6
    assert out["totals"]["arm_s_overlap"] == 2          # 2% < d <= 2 x 4%: T02 (3.5) and T03 (4.5)
    assert out["totals"]["atr_buckets"] == {"4.0-4.5": 7}
    assert set(out["by_stratum"]) == {"4w/bullish"}


def test_a_cell_with_no_floor_moved_plan_is_refused():
    rows = [census_row(("untouched", "floor", "floor")), census_row(("ceiling", "floor", "floor"))]
    out = funnel.stage_minus1(rows, "R")
    assert out["cell_verdicts"]["k0.75"] == "refused:zero-diff"
    assert out["reachable_cells"] == [1.0, 1.5]
    assert out["identical_adjacent"] == [["k1", "k1.5"]]


def test_zero_floor_moved_anywhere_closes_the_arm():
    out = funnel.stage_minus1([census_row(("untouched",) * 3)], "K")
    assert out["verdict"] == "refused:zero-diff" and out["reachable_cells"] == []


def test_concurrency_counts_open_band_plans_per_business_day(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_HEAT_CAP_PCT", 1.0)        # one 1% slot
    rows = [census_row(ticker="A", date="2021-01-04", life_end="2021-01-06"),
            census_row(ticker="B", date="2021-01-05", life_end="2021-01-07"),
            census_row(ticker="C", date="2021-01-05", life_end="2021-01-05",
                       moved=(None, None, None))]
    conc = funnel.stage_minus1(rows, "K")["totals"]["cells"]["k1"]["concurrency"]
    assert conc["max"] == 2                              # Jan 5 and 6: A and B
    assert conc["heat_slots"] == 1.0 and conc["days_over_heat_slots"] == 2


# --- Stage 0 -------------------------------------------------------------------------------

def test_stage0_powered_cells_and_the_disclosed_unpaired_count():
    rows = lifted_band_rows({key: 0.3 for key in KEYS})
    rows.append(band_row(None, {key: band_record("T99", "2021-06-15", "win", 2.0)
                                for key in KEYS}))
    out = funnel.stage0(rows, "K")
    assert out["verdict"] == "POWERED" and out["powered_cells"] == [0.75, 1.0, 1.5]
    cell = out["cells"][1]
    assert (cell["cell"], cell["paired_n"], cell["newly_admitted_n"]) == ("k1", 80, 1)
    assert cell["mde_r"] == pytest.approx(0.0, abs=1e-9)   # a constant lift has no spread


def test_stage0_refuses_a_cell_over_the_mde_ceiling_but_keeps_the_others():
    rows = lifted_band_rows({"k0.75": 0.3, "k1": 0.3, "k1.5": 0.3})
    for r in rows:
        r["cells"]["k1.5"]["r_multiple"] += 6.0 if r["entry_date"][5:7] in ("01", "03") else -6.0
    out = funnel.stage0(rows, "K")
    assert out["powered_cells"] == [0.75, 1.0]
    assert out["verdict"] == "POWERED"


def test_stage0_with_nothing_paired_is_underpowered():
    rows = [band_row(None, {key: band_record("T01", "2021-02-15", "win", 2.0) for key in KEYS})]
    out = funnel.stage0(rows, "K")
    assert out["verdict"] == "UNDERPOWERED" and out["powered_cells"] == []


def test_stage0_reads_only_the_floor_moved_stratum():
    rows = lifted_band_rows({key: 0.3 for key in KEYS}, moved="untouched")
    assert funnel.stage0(rows, "K")["verdict"] == "UNDERPOWERED"


# --- Stage 1 -------------------------------------------------------------------------------

def _stage1(lifts, **kw):
    return funnel.stage1(lifted_band_rows(lifts), "K", n_resamples=N, **kw)


def test_stage1_picks_the_highest_plateau_cell():
    out = _stage1({"k0.75": 0.30, "k1": 0.31, "k1.5": 0.29})
    assert out["verdict"] == "SELECTED" and out["selected"] == {"cell": "k1", "k": 1.0}


def test_stage1_an_edge_cell_is_adoptable_with_its_one_neighbour():
    out = _stage1({"k0.75": 0.30, "k1": 0.32, "k1.5": 0.20})
    # k1 is not a plateau (k1.5 is 0.12 away); k0.75's only neighbour is 0.02 away
    assert out["selected"] == {"cell": "k0.75", "k": 0.75}


def test_stage1_a_spike_does_not_proceed():
    out = _stage1({"k0.75": 0.10, "k1": 0.50, "k1.5": 0.10})
    assert out["verdict"] == "NO_ELIGIBLE_CELL" and out["selected"] is None


def test_stage1_a_cell_failing_a_clause_is_not_selectable():
    out = _stage1({"k0.75": -0.30, "k1": -0.31, "k1.5": -0.29})
    assert out["verdict"] == "NO_ELIGIBLE_CELL"
    assert not any(cell["eligible"] for cell in out["cells"])


def test_stage1_only_powered_cells_are_candidates_but_all_cells_are_neighbours():
    out = _stage1({"k0.75": 0.30, "k1": 0.31, "k1.5": 0.29}, cells=(0.75, 1.5))
    assert out["selected"] == {"cell": "k0.75", "k": 0.75}
    assert [c["candidate"] for c in out["cells"]] == [True, False, True]


def test_stage1_a_tie_goes_to_the_smaller_floor():
    out = _stage1({"k0.75": 0.30, "k1": 0.30, "k1.5": 0.30})
    assert out["selected"] == {"cell": "k0.75", "k": 0.75}


def test_stage1_ignores_rows_outside_the_floor_stratum():
    rows = (lifted_band_rows({"k0.75": 0.30, "k1": 0.31, "k1.5": 0.29})
            + lifted_band_rows({"k0.75": -3.0, "k1": -3.0, "k1.5": -3.0}, year=2022,
                               moved="untouched"))
    out = funnel.stage1(rows, "K", n_resamples=N)
    assert out["selected"] == {"cell": "k1", "k": 1.0}


def test_empty_census_refuses_all_cells_and_reports_zero_concurrency():
    out = funnel.stage_minus1([], "K")
    assert out["verdict"] == "refused:zero-diff"
    assert out["reachable_cells"] == [] and out["by_stratum"] == {}
    assert out["totals"]["plans_today"] == 0
    assert all(c["plans"] == 0 and c["concurrency"]["max"] == 0
               for c in out["totals"]["cells"].values())


def test_stage1_missing_neighbour_expectancy_prevents_selection():
    rows = lifted_band_rows({"k0.75": 0.30})
    out = funnel.stage1(rows, "K", cells=(0.75,), n_resamples=N)
    assert out["selected"] is None and out["verdict"] == "NO_ELIGIBLE_CELL"
    assert out["cells"][0]["eligible"] and not out["cells"][0]["plateau"]
