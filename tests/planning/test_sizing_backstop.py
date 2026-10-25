"""V187 sizing guards and byte-exact characterization of pre-backstop sizing."""
import hashlib
import itertools
import json
import logging
from types import SimpleNamespace

import pytest

from swingbot.core.edge.sizing import RISK_CEILING_PCT
from swingbot.core.planning import account as acct

NAN, INF = float("nan"), float("inf")
CFG = {"balance": 10_000.0, "risk_pct": 1.0, "position_pct": 20.0, "max_position_pct": 100.0,
       "max_position_value_absolute": 0.0, "max_risk_amount_absolute": 0.0, "sizing_mode": "risk_pct"}


@pytest.fixture(autouse=True)
def no_opex(monkeypatch):
    monkeypatch.setattr(acct.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(acct.app_config, "PORTFOLIO_TARGET_DAILY_VOL_PCT", 0.7)


def _characterization_outputs(mode, floor, monkeypatch):
    """Cover ordinary/gap sizing, all caps, OPEX, edge modes and decimal prices."""
    caps = [{}, {"max_position_pct": 10.0}, {"max_position_value_absolute": 800.0},
            {"max_risk_amount_absolute": 15.0}]
    outputs = []
    for cap, prices, multiplier in itertools.product(caps, [(100.0, 102.0), (174.5, 170.96)], [1.0, 0.75]):
        monkeypatch.setattr(acct.opex, "size_mult", lambda: multiplier)
        outputs.append(acct.compute_position_size(
            *prices, {**CFG, **cap, "sizing_mode": mode}, gap_floor_pct=floor,
            strategy_stats={"win_rate": 0.6, "avg_win_r": 0.3, "avg_loss_r": 1.0, "n": 200},
            ticker_atr_pct=3.0, open_positions=2))
    return outputs


# Captured from 376961d6 before extracting helpers. JSON preserves float repr and key order.
CHARACTERIZATION = [
    ('risk_pct', None, '0a490af4190af1d719bbd46a779455424a7b5d396d1e117e84f83fa5e1fbf782'),
    ('risk_pct', 3.0, '40f026c34d29e5459e78f56ccb92d572b5571d20e51ae97833468748a6813d46'),
    ('account_pct', None, '8f1ed15d8ded0d057337091b0a44a8dd8ddab1338356542254626c2b3751a09e'),
    ('account_pct', 3.0, '5038b3c7cf13adb9fdf986cef87a3fb6235d087f3d42358d226cb4834bdf98f9'),
    ('kelly', None, 'e1aee91d8e701fdb10cfb31c79ba25dd04883022dffce9072c0a8c1717788371'),
    ('kelly', 3.0, 'efdbb2140dc9666892c9ad89e5f30ec510f836eef5444dfaf8a97b0314f6c8c1'),
    ('vol_target', None, 'b32a9f6eb94e34e8d1201570f0e1f6180bb2d53f07e491a3e2e998e98f5a34f0'),
    ('vol_target', 3.0, 'c7290f17f5ae9c8811b86b6ea36a1f99344bdcc338685d2326ee1a79c9c8d4f5'),
    ('min_of_all', None, 'e1aee91d8e701fdb10cfb31c79ba25dd04883022dffce9072c0a8c1717788371'),
    ('min_of_all', 3.0, 'efdbb2140dc9666892c9ad89e5f30ec510f836eef5444dfaf8a97b0314f6c8c1'),
    ('unknown', None, '0a490af4190af1d719bbd46a779455424a7b5d396d1e117e84f83fa5e1fbf782'),
    ('unknown', 3.0, '40f026c34d29e5459e78f56ccb92d572b5571d20e51ae97833468748a6813d46'),
]


@pytest.mark.parametrize("mode,floor,digest", CHARACTERIZATION)
def test_in_range_outputs_remain_byte_identical(mode, floor, digest, monkeypatch):
    outputs = _characterization_outputs(mode, floor, monkeypatch)
    serialized = json.dumps(outputs, separators=(",", ":")).encode()
    assert hashlib.sha256(serialized).hexdigest() == digest


def test_equal_allocation_cap_uses_original_position_value():
    # Reconstructing position_value as shares * entry adds one ulp here.
    cfg = {**CFG, "balance": 1000.0, "position_pct": 20.0, "max_position_pct": 20.0,
           "sizing_mode": "account_pct"}
    out = acct.compute_position_size(0.3, 0.29, cfg)
    assert out["capped"] is False
    assert (out["shares"], out["position_value"], out["risk_amount"]) == (666.67, 200.0, 6.67)


def test_edge_risk_pct_passes_plain_modes_through():
    assert acct._edge_risk_pct("risk_pct", 1.0, None, None, 0) == (1.0, "risk_pct")
    assert acct._edge_risk_pct("account_pct", 1.0, None, None, 0) == (1.0, "account_pct")
    assert acct._edge_risk_pct("min_of_all", 1.0, None, None, 0) == (1.0, "risk_pct")


def test_apply_size_caps_matches_the_three_existing_caps():
    assert acct._apply_size_caps(50.0, 5000.0, 100.0, 2.0, 10_000.0, 100.0, 0.0, 0.0) == (50.0, False)
    assert acct._apply_size_caps(50.0, 5000.0, 100.0, 2.0, 10_000.0, 10.0, 0.0, 0.0) == (10.0, True)
    assert acct._apply_size_caps(50.0, 5000.0, 100.0, 2.0, 10_000.0, 100.0, 800.0, 0.0) == (8.0, True)
    assert acct._apply_size_caps(50.0, 5000.0, 100.0, 2.0, 10_000.0, 100.0, 0.0, 10.0) == (5.0, True)


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.name == acct.log.name and r.levelno == logging.WARNING]


def _size(caplog, entry=100.0, stop=98.0, ticker="AAPL", **cfg):
    with caplog.at_level(logging.WARNING, logger=acct.log.name):
        return acct.compute_position_size(entry, stop, {**CFG, **cfg}, ticker=ticker)


def test_legacy_ten_percent_is_sized_at_the_hard_cap_and_warns(caplog):
    out = _size(caplog, risk_pct=10.0)
    assert (out["shares"], out["risk_amount"], out["risk_pct"]) == (100.0, 200.0, RISK_CEILING_PCT)
    [msg] = _warnings(caplog)
    assert msg.startswith("sizing:") and "ticker=AAPL" in msg and "10.0" in msg


@pytest.mark.parametrize("stored", [-1.0, 0.0, NAN, INF, -INF])
def test_invalid_stored_risk_refuses_sizing_and_warns(caplog, stored):
    assert _size(caplog, risk_pct=stored) is None
    [msg] = _warnings(caplog)
    assert "ticker=AAPL" in msg and repr(stored) in msg


@pytest.mark.parametrize("field,value", [("balance", NAN), ("balance", INF), ("entry", NAN),
                                         ("entry", INF), ("stop", NAN), ("stop", -INF)])
def test_non_finite_inputs_refuse_sizing_and_warn(caplog, field, value):
    kwargs = {"entry": 100.0, "stop": 98.0}
    cfg = {}
    if field == "balance":
        cfg["balance"] = value
    else:
        kwargs[field] = value
    assert _size(caplog, **kwargs, **cfg) is None
    [msg] = _warnings(caplog)
    assert msg.startswith("sizing:") and "ticker=AAPL" in msg


def test_exactly_at_the_cap_is_unchanged_and_silent(caplog):
    out = _size(caplog, risk_pct=RISK_CEILING_PCT)
    assert (out["shares"], out["capped"], out["risk_pct"]) == (100.0, False, RISK_CEILING_PCT)
    assert _warnings(caplog) == []


def test_in_range_risk_is_unchanged_and_silent(caplog):
    out = _size(caplog)
    assert (out["shares"], out["risk_amount"], out["position_value"], out["capped"]) == (50.0, 100.0, 5000.0, False)
    assert _warnings(caplog) == []


def test_account_pct_ignores_a_bad_stored_risk(caplog):
    out = _size(caplog, sizing_mode="account_pct", risk_pct=NAN, stop=95.0)
    assert out["mode"] == "account_pct" and out["shares"] == 20.0
    assert _warnings(caplog) == []


def test_edge_mode_without_estimates_is_clamped_too(caplog):
    out = _size(caplog, sizing_mode="kelly", risk_pct=10.0)
    assert out["risk_pct"] == RISK_CEILING_PCT and out["shares"] == 100.0
    assert len(_warnings(caplog)) == 1


def test_a_deliberate_zero_after_the_multiplier_refuses_silently(caplog, monkeypatch):
    monkeypatch.setattr(acct.opex, "size_mult", lambda *a, **k: 0.0)
    assert _size(caplog) is None
    assert _warnings(caplog) == []


def test_missing_ticker_is_named_as_a_question_mark(caplog):
    _size(caplog, ticker=None, risk_pct=10.0)
    assert "ticker=?" in _warnings(caplog)[0]


def test_ticker_is_optional_for_every_existing_caller():
    assert acct.compute_position_size(100.0, 98.0, dict(CFG))["shares"] == 50.0


@pytest.mark.parametrize("stored,effective,expected", [
    (1.0, 1.0, 1.0), (1.0, 0.75, 0.75), (10.0, 10.0, RISK_CEILING_PCT), (1.0, 0.0, None),
    (-1.0, -1.0, None), (NAN, NAN, None), (1.0, NAN, None),
])
def test_usable_risk_pct(stored, effective, expected):
    assert acct._usable_risk_pct(stored, effective, "T") == expected




@pytest.mark.parametrize("multiplier", [NAN, INF, -INF])
def test_non_finite_effective_risk_refuses_and_warns(caplog, monkeypatch, multiplier):
    monkeypatch.setattr(acct.opex, "size_mult", lambda: multiplier)
    assert _size(caplog) is None
    [msg] = _warnings(caplog)
    assert "effective risk_pct" in msg and repr(multiplier) in msg and "ticker=AAPL" in msg


def test_overflowing_stop_distance_is_rejected_and_named(caplog):
    assert _size(caplog, entry=1e308, stop=-1e308) is None
    [msg] = _warnings(caplog)
    assert "stop_distance=inf" in msg and "ticker=AAPL" in msg


def test_non_finite_final_shares_are_rejected_and_warned(caplog):
    assert _size(caplog, entry=1e-308, stop=0.0, balance=1e308) is None
    [msg] = _warnings(caplog)
    assert "share count inf" in msg and "ticker=AAPL" in msg


@pytest.mark.parametrize("cfg,entry", [({"balance": 0.0}, 100.0), ({}, 0.0)])
def test_original_nonpositive_guard_still_precedes_stop_access(caplog, cfg, entry):
    assert _size(caplog, entry=entry, stop=None, **cfg) is None
    assert _warnings(caplog) == []


def test_bad_stored_risk_cannot_be_hidden_by_an_edge_estimator(caplog):
    with caplog.at_level(logging.WARNING, logger=acct.log.name):
        out = acct.compute_position_size(100.0, 98.0, {**CFG, "sizing_mode": "kelly", "risk_pct": INF},
                                         strategy_stats={"win_rate": 0.6, "avg_win_r": 0.3,
                                                         "avg_loss_r": 1.0, "n": 200}, ticker="AAPL")
    assert out is None
    assert "stored risk_pct=inf" in _warnings(caplog)[0]


def test_repeated_invalid_rows_warn_every_time(caplog):
    for _ in range(2):
        assert _size(caplog, risk_pct=NAN) is None
    assert len(_warnings(caplog)) == 2


@pytest.mark.parametrize("legacy", [False, True])
def test_analyze_warning_names_ticker_and_keeps_stamped_gap_sizing(caplog, monkeypatch, legacy):
    from swingbot.core.scanning import analyze

    monkeypatch.setattr(analyze, "load_account_config", lambda: {**CFG, "risk_pct": 10.0})
    monkeypatch.setattr(analyze.trade_log, "get_trades", lambda **k: [])
    monkeypatch.setattr(analyze.corr_mod, "cluster_exposure", lambda *a, **k: {"cluster": []})
    plan = SimpleNamespace(ticker="AAPL", trigger_price=100.0, entry_price=100.0, stop_loss=102.0,
                           tp1=96.0, strategy="X", quality_breakdown=[], quality_score=0,
                           badge=None, badge_stats=None, direction="bearish",
                           gap_sizing={"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120})
    if legacy:
        del plan.ticker
    item = SimpleNamespace(plan_v2=plan, result=SimpleNamespace(ticker="AAPL"))
    with caplog.at_level(logging.WARNING, logger=acct.log.name):
        ctx = analyze.build_decision_context(item, {}, None)
    assert ctx["sizing"]["shares"] == 50.0  # clamped $200 / stamped $4 gap, not $2 stop
    assert ctx["sizing"]["risk_pct"] == RISK_CEILING_PCT
    [msg] = _warnings(caplog)
    expected_ticker = "?" if legacy else "AAPL"
    assert msg.startswith("sizing:") and f"ticker={expected_ticker}" in msg and "10.0" in msg
