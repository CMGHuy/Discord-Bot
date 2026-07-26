# tests/test_wf_portfolio.py
import pytest

from swingbot.core.backtest_wf import portfolio_replay


def _sig(date, ticker, r, exit_date, sector="Tech"):
    return {"date": date, "ticker": ticker, "sector": sector,
            "r_multiple": r, "exit_date": exit_date}


def test_heat_cap_forces_skips_deterministically():
    # 8 simultaneous signals at 1% risk each, 6% heat cap -> 6 taken, 2 skipped
    sigs = [_sig("2021-01-04", f"T{i}", 0.4, "2021-02-01") for i in range(8)]
    out = portfolio_replay(sigs, heat_cap_pct=6.0, sector_cap_pct=100.0)
    assert out["trades_taken"] == 6
    assert out["trades_skipped"] == 2


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
