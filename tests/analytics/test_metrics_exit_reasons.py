"""R attributed by exit reason -- the table behind the scratch+timeout gate."""
from __future__ import annotations

import pytest

from swingbot.core.analytics import metrics


def _t(reason, r, status="closed"):
    """A closed trade whose SHARED r_multiple() evaluates to `r`.

    The plan's fixture set a literal "r_multiple" key, but that is a derived
    API field (admin/api_v1/trades.py computes it via dash.closed_r), not
    something metrics.r_multiple reads -- it recomputes from
    entry/stop_loss/exit_price/direction, per this module's "one definition
    per stat" constraint. A fixture carrying only the literal would score
    None for every trade and make the arithmetic assertions below vacuous.

    entry 100, stop 99 -> risk 1.0, so exit = 100 + r gives exactly r.
    `r=None` omits exit_price, which is how r_multiple reports "uncomputable".
    """
    trade = {"status": status, "close_reason": reason,
             "entry": 100.0, "stop_loss": 99.0, "direction": "bullish"}
    if r is not None:
        trade["exit_price"] = 100.0 + r
    return trade


def test_every_reason_is_reported_even_at_zero():
    rows = metrics.exit_reason_split([_t("stop", -1.0)])
    assert [r["reason"] for r in rows] == list(metrics.EXIT_REASONS)
    empty = [r for r in rows if r["reason"] == "timeout"][0]
    assert empty["n"] == 0
    assert empty["avg_r"] is None
    assert empty["win_rate"] is None
    assert empty["total_r"] == pytest.approx(0.0)


def test_total_and_average_r_per_reason():
    closed = [_t("stop", -1.0), _t("stop", -1.0), _t("timeout", -0.2)]
    rows = {r["reason"]: r for r in metrics.exit_reason_split(closed)}
    assert rows["stop"]["n"] == 2
    assert rows["stop"]["total_r"] == pytest.approx(-2.0)
    assert rows["stop"]["avg_r"] == pytest.approx(-1.0)
    assert rows["timeout"]["total_r"] == pytest.approx(-0.2)


def test_share_pct_sums_to_100_over_non_empty_reasons():
    closed = [_t("stop", -1.0), _t("timeout", -0.2), _t("scratch", 0.05)]
    rows = metrics.exit_reason_split(closed)
    assert sum(r["share_pct"] for r in rows) == pytest.approx(100.0)


def test_unknown_reason_lands_in_other_not_dropped():
    rows = {r["reason"]: r for r in metrics.exit_reason_split([_t("moon_exit", 0.4)])}
    assert rows["other"]["n"] == 1
    assert rows["other"]["total_r"] == pytest.approx(0.4)


def test_trade_with_no_r_multiple_counts_in_n_but_not_in_total_r():
    rows = {r["reason"]: r for r in metrics.exit_reason_split([_t("stop", None)])}
    assert rows["stop"]["n"] == 1
    assert rows["stop"]["total_r"] == pytest.approx(0.0)
    assert rows["stop"]["avg_r"] is None


def test_empty_input_returns_empty_list():
    assert metrics.exit_reason_split([]) == []


def test_runner_reasons_bucket_separately_from_tp1():
    # "runner_tp2" must not be swallowed by the "tp1" bucket, and vice versa:
    # these are the two halves of the harvest question this table exists for.
    rows = {r["reason"]: r for r in metrics.exit_reason_split(
        [_t("tp1", 1.0), _t("runner_tp2", 2.0), _t("runner_trail", 1.5)])}
    assert rows["tp1"]["n"] == 1
    assert rows["runner_tp2"]["n"] == 1
    assert rows["runner_trail"]["n"] == 1
    assert rows["other"]["n"] == 0


def test_leg_reason_drives_the_bucket():
    # A v2-manager close keeps a coarse close_reason and hides the real one in
    # the last leg -- the same subtlety resolve_outcome handles.
    trade = _t("closed", 2.0)
    trade["legs"] = [{"reason": "runner_tp2"}]
    rows = {r["reason"]: r for r in metrics.exit_reason_split([trade])}
    assert rows["runner_tp2"]["n"] == 1
