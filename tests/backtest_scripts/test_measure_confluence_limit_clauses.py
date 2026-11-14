"""V212-13b: populations, the three clauses, plateau, thin seal and the
portfolio pass of the v212 measure script. Rows are hand-built; V212-13c's
stage tests import `row` from here."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_confluence_limit as mcl  # noqa: E402

from swingbot import config
from tests.helpers import make_ohlcv


def row(arm, n, r, *, direction="bullish", year=2021, dropped=None, filled=True, ticker=None):
    """One replay row; `n` makes the alert key, so a ref and an arm row pair."""
    ticker = ticker or f"T{n:03d}"
    day = f"{year}-03-{(n % 27) + 1:02d}"
    outcome = "dropped" if dropped else ("not_triggered" if not filled else
                                         ("win" if r > 0 else "loss"))
    return {"key": f"{ticker}|4w|{day}|{direction}", "arm": arm, "ticker": ticker,
            "horizon_key": "4w", "strategy": "S/R Confluence", "direction": direction,
            "entry_date": day, "fill_date": day, "exit_date": f"{year}-04-{(n % 27) + 1:02d}",
            "filled": filled and not dropped, "dropped": dropped, "outcome": outcome,
            "r_net": r if filled and not dropped else None, "planned_rr": 2.0,
            "stop_pct": 1.5, "entry": 100.0, "stop_loss": 98.5}


def census(i, drops=None, filled=True, direction="bullish"):
    drops = drops or {}
    return {"key": f"T{i}|4w|2021-03-01|{direction}", "direction": direction, "d_pct": 2.5 + i,
            "drops": {cell: drops.get(cell) for cell in ("f0.333", "f0.5", "f0.667")},
            "fill_state": {cell: None if drops.get(cell) else ("filled" if filled else "expired")
                           for cell in ("f0.333", "f0.5", "f0.667")},
            "filled": {cell: filled and not drops.get(cell) for cell in ("f0.333", "f0.5", "f0.667")}}


def test_stage_minus1_counts_scope_drops_fills_and_d_range():
    rows = [census(0, {"f0.333": "limit_stop_beyond_cap"}), census(1), census(2, filled=False),
            census(3, direction="bearish")]
    out = mcl.stage_minus1(rows)
    third, half = out["cells"][0], out["cells"][1]
    assert (out["verdict"], out["alerts"]) == ("REACHABLE", 4)
    assert (third["in_scope"], third["kept"], third["drops"]) == (4, 3, {"limit_stop_beyond_cap": 1})
    assert (half["observed_n"], half["d_range"]) == (3, [2.5, 5.5])
    assert half["filled_by_direction"] == {"bullish": 2, "bearish": 1}
    assert half["fill_states"] == {"filled": 3, "expired": 1}


def test_a_census_without_fills_is_zero_diff():
    assert mcl.stage_minus1([census(0, filled=False)])["verdict"] == "refused:zero-diff"
    assert mcl.stage_minus1([])["cells"][0]["d_range"] is None


def _res(passes, expr):
    return {"passes": passes, "expr": expr}


def test_neighbours_and_plateau():
    assert mcl.neighbours("f0.333") == ["f0.5"]
    assert mcl.neighbours("f0.5") == ["f0.333", "f0.667"]
    assert mcl.neighbours("f0.667") == ["f0.5"]
    assert mcl.plateau({"f0.333": _res(True, .30), "f0.5": _res(True, .31),
                        "f0.667": _res(True, .29)}) == "f0.5"
    assert mcl.plateau({"f0.333": _res(True, .40), "f0.5": _res(False, .50),
                        "f0.667": _res(True, .45)}) is None   # no cell has passing neighbours
    assert mcl.plateau({"f0.333": _res(True, .30), "f0.5": _res(True, .30),
                        "f0.667": _res(False, .1)}) == "f0.333"   # tie -> smaller f
    assert mcl.plateau({"f0.333": _res(False, .3), "f0.5": _res(True, .2),
                        "f0.667": _res(True, .4)}) == "f0.667"    # an edge cell, one neighbour


def test_clauses_score_all_three():
    ref = [row("ref", n, 1.0 if n < 5 else -1.0) for n in range(10)]      # ExpR 0, WR 50
    arm = [row("f0.5", n, 1.5 if n < 3 else -1.0) for n in range(6)]       # ExpR 0.25, WR 50
    out = mcl.clauses(arm, ref)
    assert (out["n"], out["ref_n"]) == (6, 10)
    assert out["expr"] == pytest.approx(0.25) and out["ref_expr"] == pytest.approx(0.0)
    assert out["expr_beats_reference"] and out["fills_half_of_reference"] and out["wr_within_2pp"]
    assert out["passes"] is True


def test_clauses_fail_short_and_empty_samples():
    ref = [row("ref", n, 1.0 if n < 5 else -1.0) for n in range(10)]
    arm = [row("f0.5", n, 1.5 if n < 3 else -1.0) for n in range(6)]
    assert mcl.clauses(arm[:4], ref)["fills_half_of_reference"] is False   # 4 < 5
    assert mcl.clauses([], [])["passes"] is False
    assert mcl.clauses(arm, [])["fills_half_of_reference"] is False        # empty reference


def test_the_win_rate_clause_allows_exactly_two_points():
    ref = [row("ref", n, 1.0 if n < 50 else -1.0) for n in range(100)]     # 50.0%
    arm = [row("f0.5", n, 3.0 if n < 48 else -1.0) for n in range(100)]    # 48.0%
    assert mcl.clauses(arm, ref)["wr_within_2pp"] is True
    arm[47] = row("f0.5", 47, -1.0)                                         # 47.0%
    assert mcl.clauses(arm, ref)["wr_within_2pp"] is False


def test_populations_follow_the_cells_kept_alerts():
    rows = [row("ref", 1, 1.0), row("ref", 2, -1.0), row("ref", 3, None, filled=False),
            row("f0.5", 1, 1.0), row("f0.5", 2, None, dropped="limit_stop_beyond_cap"),
            row("f0.5", 3, None, filled=False)]
    assert mcl.cell_keys(rows, "f0.5") == {rows[0]["key"], rows[2]["key"]}
    assert [r["key"] for r in mcl.reference_rows(rows, "f0.5")] == [rows[0]["key"]]
    assert [r["key"] for r in mcl.closed(rows, "f0.5")] == [rows[3]["key"]]
    trade = mcl.to_trade(rows[3])
    assert (trade.r_multiple, trade.entry_date, trade.source) == (1.0, rows[3]["entry_date"],
                                                                  "confluence")


def test_thin_needs_thirty_per_direction():
    bulls = [row("f0.5", n, 1.0) for n in range(30)]
    bears = [row("f0.5", n, 1.0, direction="bearish") for n in range(30)]
    assert mcl.thin(bulls + bears) is False
    assert mcl.thin(bulls + bears[:29]) is True
    assert mcl.thin(bulls) is True


@pytest.fixture
def caps(monkeypatch):
    for attr, value in (("RISK_PER_TRADE_PCT", 1.0), ("PORTFOLIO_HEAT_CAP_PCT", 6.0),
                        ("SECTOR_HEAT_CAP_PCT", 3.0), ("MAX_OPEN_POSITIONS", 30),
                        ("MAX_POSITION_SIZE_PCT", 100.0), ("MAX_POSITION_VALUE_ABSOLUTE", 0.0)):
        monkeypatch.setattr(config, attr, value, raising=False)
    return monkeypatch


def _same_day(n):
    rows = [row("f0.5", i, 1.0, ticker=f"T{i}") for i in range(n)]
    for r in rows:
        r["fill_date"], r["exit_date"] = "2021-03-01", "2021-03-10"
    return rows


def test_portfolio_pass_keeps_what_the_caps_allow(caps):
    rows = _same_day(3)
    assert len(mcl.portfolio_pass(rows, "f0.5", sectors={}, cluster_fn=None)) == 3
    caps.setattr(config, "MAX_OPEN_POSITIONS", 1)
    kept, result = mcl.run_portfolio(rows, sectors={}, cluster_fn=None)
    assert [r["key"] for r in kept] == [rows[0]["key"]]
    assert result["skip_reasons"] == {"max_open": 2}


def test_a_notional_cap_cuts_risk_not_trades(caps):
    caps.setattr(config, "MAX_POSITION_VALUE_ABSOLUTE", 1000.0)
    kept, result = mcl.run_portfolio(_same_day(3), sectors={}, cluster_fn=None)
    assert (len(kept), result["notional_capped"]) == (3, 3)
    assert result["r_multiples_taken"] == [1.0, 1.0, 1.0]       # R stays on the plan's stop


def test_cluster_fn_reads_frames_before_the_fill_bar(monkeypatch):
    monkeypatch.setattr(config, "CORRELATED_HEAT_CAP_PCT", 3.0, raising=False)
    closes = list(100 + np.cumsum(np.random.default_rng(7).normal(0, 1, 150)))
    frames = {"AAA": make_ohlcv(closes), "BBB": make_ohlcv(closes)}
    fill_day = str(frames["AAA"].index[140].date())
    cluster_fn = mcl.make_cluster_fn(frames, {})
    sig = {"ticker": "AAA", "date": fill_day}
    held = lambda risk: [{"ticker": "BBB", "risk_pct": risk, "sector": None}]   # noqa: E731
    assert cluster_fn(held(2.5), sig, 1.0) is True          # 2.5 + 1.0 > 3.0, corr 1.0
    assert cluster_fn(held(1.0), sig, 1.0) is False
    assert cluster_fn([], sig, 1.0) is False


# --- boundary pins (mutation-checked: each fails if its clause comparison flips)

def test_equal_expectancy_does_not_beat_the_reference():
    ref = [row("ref", n, 1.0 if n < 5 else -1.0) for n in range(10)]       # ExpR 0
    arm = [row("f0.5", n, 1.0 if n < 3 else -1.0) for n in range(6)]       # ExpR 0
    assert mcl.clauses(arm, ref)["expr_beats_reference"] is False


def test_exactly_half_the_reference_trades_is_enough():
    ref = [row("ref", n, 1.0 if n < 5 else -1.0) for n in range(10)]
    arm = [row("f0.5", n, 1.5 if n < 2 else -1.0) for n in range(5)]       # 5 of 10
    assert mcl.clauses(arm, ref)["fills_half_of_reference"] is True


def test_one_failing_clause_fails_the_cell():
    ref = [row("ref", n, 1.0 if n < 5 else -1.0) for n in range(10)]
    arm = [row("f0.5", n, 1.5 if n < 3 else -1.0) for n in range(4)]       # 4 < 5 trades
    out = mcl.clauses(arm, ref)
    assert out["expr_beats_reference"] and out["wr_within_2pp"]
    assert out["passes"] is False


def test_plateau_needs_every_neighbour_of_the_winner_to_pass():
    # f0.5 is the best passing cell but f0.333 fails: no plateau, even though
    # f0.667 passes with a passing neighbour (the runner-up never steps in).
    assert mcl.plateau({"f0.333": _res(False, .3), "f0.5": _res(True, .5),
                        "f0.667": _res(True, .4)}) is None


def test_plateau_returns_the_winner_when_its_neighbours_pass():
    assert mcl.plateau({"f0.333": _res(True, .1), "f0.5": _res(True, .6),
                        "f0.667": _res(True, .2)}) == "f0.5"


def test_an_edge_winner_needs_only_its_one_neighbour():
    assert mcl.plateau({"f0.333": _res(True, .5), "f0.5": _res(True, .2),
                        "f0.667": _res(False, .9)}) == "f0.333"
    assert mcl.plateau({"f0.333": _res(False, .9), "f0.5": _res(True, .2),
                        "f0.667": _res(True, .5)}) == "f0.667"


def test_no_passing_cell_is_no_plateau():
    assert mcl.plateau({"f0.333": _res(False, .5), "f0.5": _res(False, .6),
                        "f0.667": _res(False, .7)}) is None


def test_plateau_tie_between_edge_cells_keeps_the_smaller_f():
    assert mcl.plateau({"f0.333": _res(True, .3), "f0.5": _res(True, .2),
                        "f0.667": _res(True, .3)}) == "f0.333"


def test_closed_skips_open_and_unfilled_rows():
    still_open = {**row("f0.5", 1, 1.0), "outcome": "open"}
    unfilled = {**row("f0.5", 2, 1.0), "filled": False}
    done = row("f0.5", 3, 1.0)
    assert [r["key"] for r in mcl.closed([still_open, unfilled, done], "f0.5")] == [done["key"]]


def test_one_filled_cell_makes_the_census_reachable():
    rows = [census(0, {"f0.333": "limit_stop_beyond_cap", "f0.667": "limit_stop_beyond_cap"})]
    out = mcl.stage_minus1(rows)
    assert [c["observed_n"] for c in out["cells"]] == [0, 1, 0]
    assert out["verdict"] == "REACHABLE"


def test_signals_are_dated_at_the_fill_so_pending_limits_reserve_nothing(caps):
    caps.setattr(config, "MAX_OPEN_POSITIONS", 1)
    first = {**row("f0.5", 1, 1.0, ticker="AAA"), "entry_date": "2021-03-01",
             "fill_date": "2021-03-01", "exit_date": "2021-03-05"}
    second = {**row("f0.5", 2, 1.0, ticker="BBB"), "entry_date": "2021-03-02",
              "fill_date": "2021-03-10", "exit_date": "2021-03-20"}
    kept, _ = mcl.run_portfolio([first, second], sectors={}, cluster_fn=None)
    assert len(kept) == 2      # BBB's limit waited unfilled while AAA was open


def test_run_portfolio_reads_live_caps_without_throttles(caps):
    for attr, value in (("RISK_PER_TRADE_PCT", 0.75), ("PORTFOLIO_HEAT_CAP_PCT", 5.0),
                        ("SECTOR_HEAT_CAP_PCT", 2.5), ("MAX_OPEN_POSITIONS", 7),
                        ("MAX_POSITION_SIZE_PCT", 20.0), ("MAX_POSITION_VALUE_ABSOLUTE", 900.0)):
        caps.setattr(config, attr, value)
    seen = {}
    real = mcl.portfolio_replay

    def spy(signals, **kwargs):
        seen.update(kwargs)
        return real(signals, **kwargs)
    caps.setattr(mcl, "portfolio_replay", spy)
    mcl.run_portfolio(_same_day(2), sectors={"T0": "Tech"}, cluster_fn=None)
    assert {k: seen[k] for k in ("risk_pct", "heat_cap_pct", "sector_cap_pct", "max_open",
                                 "max_position_pct", "max_position_value", "throttles",
                                 "track_keys")} == {
        "risk_pct": 0.75, "heat_cap_pct": 5.0, "sector_cap_pct": 2.5, "max_open": 7,
        "max_position_pct": 20.0, "max_position_value": 900.0, "throttles": False,
        "track_keys": True}
    assert seen["sectors"] == {"T0": "Tech"}


def test_cluster_fn_never_hands_the_fill_bar_to_correlation(monkeypatch):
    from swingbot.core.edge import correlation
    closes = list(100 + np.cumsum(np.random.default_rng(3).normal(0, 1, 60)))
    frames = {"AAA": make_ohlcv(closes), "BBB": make_ohlcv(closes)}
    fill_day = frames["AAA"].index[50]
    seen = {}

    def fake_exposure(open_pos, ticker, dfs, balance, sectors=None):
        seen.update({t: df.index[-1] for t, df in dfs.items()})
        return {}
    monkeypatch.setattr(correlation, "cluster_exposure", fake_exposure)
    monkeypatch.setattr(correlation, "cluster_check", lambda exposure, risk: {"allowed": True})
    mcl.make_cluster_fn(frames, {})([{"ticker": "BBB", "risk_pct": 1.0, "sector": None}],
                                    {"ticker": "AAA", "date": str(fill_day.date())}, 1.0)
    assert seen == {"AAA": frames["AAA"].index[49], "BBB": frames["BBB"].index[49]}
