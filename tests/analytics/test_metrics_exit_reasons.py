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


@pytest.mark.parametrize(("text", "status", "bucket"), [
    # One row per string mapped in spec §3.5a, copied verbatim from
    # production's /analytics/exit-quality unmapped_reasons on 2026-09-16.
    pytest.param("loss", "loss", "stop", id="literal-loss"),
    pytest.param("tp1_runner_be", "win", "runner_be", id="tp1-runner-be"),
    pytest.param("tp1_runner_tp2", "win", "runner_tp2", id="tp1-runner-tp2"),
    pytest.param("auto (near-tp stall)", "win", "timeout", id="near-tp-stall"),
    pytest.param("time_exit", "closed", "timeout", id="v119-compression-time-exit"),
])
def test_production_close_reasons_map_by_exact_text(text, status, bucket):
    trade = {"status": status, "close_reason": text, "entry": 100.0, "stop_loss": 99.0,
             "direction": "bullish", "exit_price": 100.0}
    assert metrics.exit_reason_bucket(trade) == bucket


def test_an_unlisted_text_that_merely_contains_a_mapped_word_is_still_other():
    # Exact match only (metrics.exit_reason_bucket docstring): a substring
    # rule is how a table like this starts lying.
    trade = {"status": "win", "close_reason": "not a stop at all", "entry": 100.0,
             "stop_loss": 99.0, "direction": "bullish", "exit_price": 101.0}
    assert metrics.exit_reason_bucket(trade) == "other"


@pytest.mark.parametrize(("text", "status"), [
    pytest.param("auto (price monitor)", "win", id="price-monitor-win"),
    pytest.param("auto (price monitor)", "loss", id="price-monitor-loss"),
    pytest.param("", "win", id="empty-win"),
    pytest.param("", "loss", id="empty-loss"),
    pytest.param("manual", "closed", id="manual"),
    pytest.param("manual (plan close, admin ui)", "closed", id="manual-plan-close"),
])
def test_production_texts_with_no_matching_bucket_stay_other(text, status):
    # These six rows from spec §3.5a were considered and deliberately left
    # unmapped: "auto (price monitor)" covers both a win (hit take-profit)
    # and a loss (hit stop) mechanism under one text, which a text-only alias
    # cannot safely disambiguate; an empty reason; and two operator-initiated
    # closes with no EXIT_REASONS bucket of their own.
    trade = {"status": status, "close_reason": text, "entry": 100.0, "stop_loss": 99.0,
             "direction": "bullish", "exit_price": 100.0}
    assert metrics.exit_reason_bucket(trade) == "other"


# --- v165: public name, and the text-only half for scale-out legs ----------
#
# The P&L calendar's day page buckets each realized LEG by the leg's own
# reason (`trade["legs"][i]["reason"]`), while a whole trade keeps the
# trade-level bucket. The text half is split out so the leg path and the
# trade path cannot drift apart on what an exact name or an alias means.


def test_the_private_name_is_gone_with_no_alias():
    assert not hasattr(metrics, "_exit_reason_bucket")


@pytest.mark.parametrize("name", list(metrics.EXIT_REASONS))
def test_every_exit_reason_name_buckets_to_itself_from_text(name):
    assert metrics.exit_reason_bucket_text(name) == name


@pytest.mark.parametrize(("text", "bucket"), [
    pytest.param("loss", "stop", id="alias-loss"),
    pytest.param("tp1_runner_be", "runner_be", id="alias-runner-be"),
    pytest.param("tp1_runner_tp2", "runner_tp2", id="alias-runner-tp2"),
    pytest.param("auto (near-tp stall)", "timeout", id="alias-near-tp-stall"),
    pytest.param("time_exit", "timeout", id="alias-time-exit"),
])
def test_text_aliases_resolve_like_the_trade_level_bucket(text, bucket):
    assert metrics.exit_reason_bucket_text(text) == bucket


def test_text_is_stripped_and_lowercased_before_the_lookup():
    assert metrics.exit_reason_bucket_text("  TP1 ") == "tp1"
    assert metrics.exit_reason_bucket_text("Runner_Trail") == "runner_trail"


@pytest.mark.parametrize("text", [
    pytest.param(None, id="none"),
    pytest.param("", id="empty"),
    pytest.param("   ", id="blank"),
    pytest.param("not a stop at all", id="substring-only"),
    pytest.param("auto (price monitor)", id="ambiguous-text"),
    pytest.param("scratch exit", id="prose-needs-status"),
])
def test_text_with_no_exact_name_or_alias_is_none_not_a_guess(text):
    # None, not "other": the caller decides what an unmatched leg means.
    # "scratch exit" is resolve_outcome's job on a whole trade, and a leg
    # has no status of its own to resolve against.
    assert metrics.exit_reason_bucket_text(text) is None


def test_the_trade_level_bucket_does_not_gain_the_texts_stripping():
    # Pins "output unchanged": close_reason_text only lowercases, so a
    # padded reason on a whole trade stayed "other" before v165 and must
    # stay "other" after it. Only the leg path normalises whitespace.
    trade = {"status": "loss", "close_reason": " loss ", "entry": 100.0,
             "stop_loss": 99.0, "direction": "bullish", "exit_price": 99.0}
    assert metrics.exit_reason_bucket(trade) == "other"


def test_the_trade_level_bucket_still_falls_back_to_resolve_outcome():
    trade = {"status": "closed", "close_reason": "scratch exit", "entry": 100.0,
             "stop_loss": 99.0, "direction": "bullish", "exit_price": 100.0}
    assert metrics.exit_reason_bucket(trade) == "scratch"
