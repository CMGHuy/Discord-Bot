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
