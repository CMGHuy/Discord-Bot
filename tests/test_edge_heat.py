import pytest

from swingbot.core.edge.heat import heat_check, open_heat, trade_risk_pct

BALANCE = 10_000.0


def _trade(entry, stop, shares):
    return {"entry": entry, "stop_loss": stop, "shares": shares}


def test_trade_risk_pct_from_prices():
    # (100-98) * 100 shares = $200 = 2% of 10k
    assert trade_risk_pct(_trade(100.0, 98.0, 100), BALANCE) == pytest.approx(2.0)


def test_trade_risk_pct_prefers_recorded_value():
    assert trade_risk_pct({"risk_pct": 1.5}, BALANCE) == 1.5


def test_open_heat_sums():
    trades = [_trade(100.0, 98.0, 100)] * 3   # 3 x 2%
    assert open_heat(trades, BALANCE) == pytest.approx(6.0)


def test_heat_check_blocks_at_cap():
    trades = [_trade(100.0, 98.0, 100)] * 3   # 6% open = at the 6% cap
    chk = heat_check(trades, BALANCE, candidate_risk_pct=1.0, cap_pct=6.0)
    assert chk["allowed"] is False
    assert chk["remaining"] == pytest.approx(0.0)


def test_closing_one_frees_heat():
    trades = [_trade(100.0, 98.0, 100)] * 2   # 4% open
    chk = heat_check(trades, BALANCE, candidate_risk_pct=1.0, cap_pct=6.0)
    assert chk["allowed"] is True
    assert chk["remaining"] == pytest.approx(2.0)


def test_sector_heat_and_cap():
    from swingbot.core.edge.heat import sector_check, sector_heat
    sectors = {"AAA": "Energy", "BBB": "Energy", "CCC": "Utilities", "CAND": "Energy"}
    trades = [{"ticker": "AAA", "risk_pct": 2.0}, {"ticker": "BBB", "risk_pct": 1.0},
              {"ticker": "CCC", "risk_pct": 2.0}]
    heat = sector_heat(trades, BALANCE, sectors)
    assert heat["Energy"] == pytest.approx(3.0)
    chk = sector_check(trades, BALANCE, "CAND", 1.0, sectors, cap_pct=3.0)
    assert chk["allowed"] is False and chk["sector"] == "Energy"


def test_unknown_sector_never_blocks():
    from swingbot.core.edge.heat import sector_check
    chk = sector_check([], BALANCE, "MYSTERY", 1.0, sectors={}, cap_pct=3.0)
    assert chk["allowed"] is True


def test_portfolio_report_renders_every_section():
    from swingbot.commands.growth import portfolio_report
    state = {"open_heat": 4.5, "heat_cap": 6.0,
             "sector_heat": {"Energy": 3.0, "Tech": 1.5},
             "clusters": [["XOM", "CVX"]],
             "throttle_mult": 0.75, "paused": False,
             "kill": {"on": False, "reason": None},
             "growth": {"current_multiple": 1.32, "pct_to_target": 12.1}}
    out = portfolio_report(state)
    assert "4.5% / 6.0%" in out
    assert "Energy" in out and "3.0%" in out
    assert "XOM" in out and "CVX" in out
    assert "x0.75" in out
    assert "1.32x" in out


def test_portfolio_report_kill_state_prominent():
    from swingbot.commands.growth import portfolio_report
    state = {"open_heat": 0.0, "heat_cap": 6.0, "sector_heat": {}, "clusters": [],
             "throttle_mult": 0.0, "paused": True,
             "kill": {"on": True, "reason": "manual"}, "growth": {}}
    assert "KILL SWITCH ON" in portfolio_report(state)


def test_collect_portfolio_state_degrades_on_account_config_failure(monkeypatch):
    """Task E52 review Finding (Important): load_account_config() is file I/O
    plus a possible write-back and was the one sub-collector in
    _collect_portfolio_state() NOT try/excepted. If it raises, `balance`
    must still fall back to 0.0 (not NameError) and the growth-path section
    must degrade to {} rather than the whole command crashing."""
    from swingbot.commands.growth import _collect_portfolio_state
    from swingbot.core import account as account_module

    def _boom():
        raise OSError("disk read failed")

    monkeypatch.setattr(account_module, "load_account_config", _boom)

    state = _collect_portfolio_state()

    # Must return a dict with safe defaults, not propagate the exception.
    assert isinstance(state, dict)
    assert state.get("growth") == {}
    # heat/sector_heat/throttle must have used balance=0.0, not raised.
    assert state.get("open_heat") == pytest.approx(0.0)
    assert state.get("sector_heat") == {}


def test_weekly_risk_report_renders():
    from swingbot.commands.growth import weekly_risk_report
    out = weekly_risk_report({
        "heat_utilization_pct": 62.0,
        "biggest_cluster": ["NVDA", "AMD", "AVGO"],
        "throttle_activations": 1,
        "mc": {"max_dd_p95": 0.18, "p_ruin": 0.002, "p_10x": 0.11},
        "growth_delta": 0.014,
    })
    assert "62" in out and "NVDA" in out
    assert "p95 drawdown 18%" in out
    assert "+1.4%" in out
