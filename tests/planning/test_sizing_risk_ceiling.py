"""v187 D2: the 2% risk ceiling binds in both sizing modes, on the RETURNED
(rounded) share count; rounding floors only when it would breach."""
import itertools

import pytest

from swingbot.core.edge.sizing import RISK_CEILING_PCT
from swingbot.core.planning import account as acct

CFG = {"balance": 10_000.0, "risk_pct": 1.0, "position_pct": 20.0, "max_position_pct": 100.0,
       "max_position_value_absolute": 0.0, "max_risk_amount_absolute": 0.0, "sizing_mode": "risk_pct"}
LIMIT = CFG["balance"] * RISK_CEILING_PCT / 100      # 200.0


@pytest.fixture(autouse=True)
def no_opex(monkeypatch):
    monkeypatch.setattr(acct.opex, "size_mult", lambda *a, **k: 1.0)


def _size(entry=100.0, stop=98.0, **cfg):
    return acct.compute_position_size(entry, stop, {**CFG, **cfg})


def test_account_pct_wide_stop_is_cut_to_two_percent_risk():
    out = _size(stop=80.0, sizing_mode="account_pct")      # 20 shares x $20 = $400 = 4%
    assert (out["shares"], out["risk_amount"], out["position_value"], out["capped"]) == (10.0, 200.0, 1000.0, True)


def test_account_pct_inside_the_ceiling_is_unchanged():
    out = _size(stop=95.0, sizing_mode="account_pct")      # 20 x $5 = $100 = 1%
    assert (out["shares"], out["risk_amount"], out["capped"]) == (20.0, 100.0, False)


def test_account_pct_with_no_stop_distance_is_sized_as_today():
    out = _size(stop=100.0, sizing_mode="account_pct")
    assert (out["shares"], out["risk_amount"], out["capped"]) == (20.0, 0.0, False)


def test_exactly_two_percent_is_not_reported_as_capped():
    out = _size(risk_pct=RISK_CEILING_PCT)
    assert (out["shares"], out["risk_amount"], out["capped"]) == (100.0, 200.0, False)


def test_a_round_up_that_would_breach_is_floored():
    out = _size(stop=97.0, risk_pct=RISK_CEILING_PCT)      # raw 66.666..., round -> 66.67 x 3 = 200.01
    assert out["shares"] == 66.66
    assert (out["risk_amount"], out["position_value"]) == (round(66.66 * 3, 2), round(66.66 * 100, 2))
    assert out["shares"] * 3.0 <= LIMIT * (1 + 1e-9)


def test_a_round_up_inside_the_ceiling_is_kept():
    out = _size(stop=94.0)                                  # raw 16.666..., 16.67 x 6 = 100.02 <= 200
    assert (out["shares"], out["risk_amount"], out["position_value"]) == (16.67, 100.0, 1666.67)


def test_absolute_caps_still_bind_first():
    out = _size(stop=80.0, sizing_mode="account_pct", max_risk_amount_absolute=100.0)
    assert (out["shares"], out["risk_amount"], out["capped"]) == (5.0, 100.0, True)


@pytest.mark.parametrize("mode,entry,distance,risk,position", list(itertools.product(
    ("risk_pct", "account_pct"), (7.31, 100.0, 312.17), (0.013, 0.37, 3.0, 41.9), (0.5, 2.0, 10.0), (5.0, 60.0),
)))
def test_returned_shares_never_risk_more_than_the_ceiling(mode, entry, distance, risk, position):
    out = _size(entry=entry, stop=entry - distance, sizing_mode=mode, risk_pct=risk, position_pct=position)
    assert out["shares"] * distance <= LIMIT * (1 + 1e-9)


def test_helpers():
    assert acct._RISK_TOLERANCE == 1e-9
    assert acct._cap_to_risk_ceiling(20.0, 20.0, 10_000.0) == (10.0, True)
    assert acct._cap_to_risk_ceiling(20.0, 5.0, 10_000.0) == (20.0, False)
    assert acct._cap_to_risk_ceiling(20.0, 0.0, 10_000.0) == (20.0, False)
    assert acct._settle_shares(200.0 / 3.0, 3.0, 10_000.0) == (66.66, 66.66)
    assert acct._settle_shares(100.0 / 6.0, 6.0, 10_000.0) == (100.0 / 6.0, 16.67)
    assert acct._settle_shares(20.0, 0.0, 10_000.0) == (20.0, 20.0)


@pytest.mark.parametrize("excess,capped", [(0.5e-9, False), (2e-9, True)])
def test_ceiling_cap_respects_relative_float_tolerance(excess, capped):
    raw = 10.0 * (1 + excess)
    shares, did_cap = acct._cap_to_risk_ceiling(raw, 20.0, 10_000.0)
    assert did_cap is capped
    assert shares == (10.0 if capped else raw)


def test_gap_figures_use_the_floor_when_rounding_would_breach():
    out = acct.compute_position_size(100.0, 103.0, {**CFG, "risk_pct": RISK_CEILING_PCT},
                                     gap_floor_pct=3.0)
    assert out["shares"] == 66.66
    assert out["gap_risk_amount"] == out["risk_amount"] == 199.98
    assert out["position_value"] == 6666.0
    assert out["gap_floor_pct"] == 3.0
    assert out["gap_sized"] is False


def test_account_ceiling_cut_is_not_reported_as_a_gap_sizing_cut():
    out = acct.compute_position_size(100.0, 120.0, {**CFG, "sizing_mode": "account_pct"},
                                     gap_floor_pct=3.0)
    assert out["shares"] == 10.0
    assert out["gap_risk_amount"] == out["risk_amount"] == 200.0
    assert out["capped"] is True
    assert out["gap_sized"] is False
