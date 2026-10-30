"""v189 D2: a close with two or more realized legs is labelled by the sign
of its UNROUNDED net R, with a ±SCRATCH_EPS_R scratch band (edges
exclusive) and `closed`/`unscored` when the net cannot be trusted."""
import logging
import math
from datetime import date

import pytest

from swingbot.core.analytics import metrics
from tests.analytics.test_golden_partial_trade_metrics import load_golden


def _two_leg(net_r, *, trade_id="t-1"):
    """Golden geometry; TP1 +2R on half, runner r chosen so the blend is net_r."""
    runner_r = 2.0 * net_r - 2.0
    return {"id": trade_id, "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
            "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
                     {"fraction": 0.5, "exit_price": 100.0 + 5.0 * runner_r,
                      "r": runner_r, "reason": "tp1_runner_be"}]}


def test_constants():
    assert metrics.SCRATCH_EPS_R == 0.01
    # v189 D6: scaled-out closes are labelled by net R from this date on;
    # earlier ones keep their TP1-touch label (no backfill).
    assert metrics.LABEL_BASIS_SINCE == "2026-10-30"
    assert date.fromisoformat(metrics.LABEL_BASIS_SINCE).isoformat() == metrics.LABEL_BASIS_SINCE


@pytest.mark.parametrize("row", load_golden()["label_table"], ids=lambda r: str(r["net_r"]))
def test_label_table(row):
    assert metrics.net_outcome(_two_leg(row["net_r"])) == (row["status"], row["close_reason"])


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_band_edges_are_exclusive(sign):
    # 0.5 x 0.01 + 0.5 x 0.01 is exactly float(0.01): the edge itself.
    edge = sign * metrics.SCRATCH_EPS_R
    trade = {"id": "edge", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
             "legs": [{"fraction": 0.5, "r": edge}, {"fraction": 0.5, "r": edge}]}
    assert metrics._blended_r_raw(trade) == edge
    assert metrics.net_outcome(trade) == ("closed", "scratch")


def test_threshold_uses_the_unrounded_blend():
    """+0.012 rounds to 0.01 (the edge, scratch) but is above the band: win.
    -0.012 likewise: loss."""
    assert metrics.r_multiple(_two_leg(0.012)) == 0.01
    assert metrics.net_outcome(_two_leg(0.012)) == ("win", None)
    assert metrics.net_outcome(_two_leg(-0.012)) == ("loss", None)


def test_missing_risk_basis_is_unscored_with_a_warning(caplog):
    trade = _two_leg(1.0, trade_id="no-stop")
    trade["stop_loss"] = None
    with caplog.at_level(logging.WARNING, logger="swingbot.core.analytics.metrics"):
        assert metrics.net_outcome(trade) == ("closed", "unscored")
    assert "no-stop" in caplog.text


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_leg_r_is_unscored_never_a_scratch(bad, caplog):
    trade = _two_leg(1.0, trade_id="nan-leg")
    trade["legs"][1]["r"] = bad
    with caplog.at_level(logging.WARNING, logger="swingbot.core.analytics.metrics"):
        assert metrics.net_outcome(trade) == ("closed", "unscored")
    assert "nan-leg" in caplog.text


def test_non_finite_exit_price_on_a_leg_without_r_is_unscored():
    trade = _two_leg(1.0)
    trade["legs"][1] = {"fraction": 0.5, "exit_price": math.nan, "reason": "manual"}
    assert metrics.net_outcome(trade) == ("closed", "unscored")


def test_warning_names_the_plan_id_when_the_trade_has_no_id(caplog):
    trade = _two_leg(1.0)
    trade.pop("id")
    trade["plan_id"] = "plan-77"
    trade["direction"] = None
    with caplog.at_level(logging.WARNING, logger="swingbot.core.analytics.metrics"):
        assert metrics.net_outcome(trade) == ("closed", "unscored")
    assert "plan-77" in caplog.text


def test_never_falls_back_to_the_tp1_touch_rule():
    """A runner reason starting `tp1_` used to mean `win` whatever the net."""
    trade = _two_leg(-0.2)
    assert trade["legs"][1]["reason"].startswith("tp1_")
    assert metrics.net_outcome(trade) == ("loss", None)
