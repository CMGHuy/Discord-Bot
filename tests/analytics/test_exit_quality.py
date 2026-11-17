import pytest
from swingbot.core.analytics import exit_quality as eq


def _entry(outcome="win", **overrides):
    entry = {"outcome": outcome, "mfe_r": 2.0, "mae_r": 0.4,
             "exit_efficiency": 0.5, "r_realized": 1.0}
    entry.update(overrides)
    return entry


def test_histograms_are_winners_only_and_preserve_missingness():
    result = eq.efficiency_histogram([_entry(), _entry("loss", exit_efficiency=-1),
                                      _entry(exit_efficiency=None)], bins=2)
    assert result["n"] == 1
    assert result["median"] == 0.5


def test_scatter_includes_losses_but_skips_missing_axes():
    points = eq.mfe_mae_points([_entry(), _entry("loss"), _entry(mae_r=None)])
    assert {point["outcome"] for point in points} == {"win", "loss"}


def test_coverage_reports_missing_values_without_a_divide_by_zero():
    assert eq.coverage([])["mae_r"] == {"non_null": 0, "total": 0, "pct": 0.0}
    assert eq.coverage([_entry(), _entry(exit_efficiency=None)])["exit_efficiency"]["pct"] == 50.0


def _sourced(source, hold, outcome="win", **overrides):
    return _entry(outcome, excursion_source=source, holding_days=hold, **overrides)


@pytest.mark.parametrize("source,hold,trusted,estimate", [
    ("5min", 0.1, True, False),
    ("15min", 0.5, True, False),
    ("hourly", 1.9, True, False),
    ("daily", 1.99, False, True),
    ("daily", 2.0, True, False),     # boundary: two days is trusted
    ("daily", None, False, True),    # unknown hold on daily bars: an estimate
    (None, 3.0, True, False),        # no source, long hold
    (None, 0.5, False, False),       # no source, short hold: no figures at all
])
def test_trust_and_estimate_rules(source, hold, trusted, estimate):
    entry = _sourced(source, hold)
    assert eq.is_trusted(entry) is trusted
    assert eq.is_daily_estimate(entry) is estimate


def test_a_non_numeric_or_nan_hold_on_daily_bars_is_an_estimate():
    assert eq.is_daily_estimate(_sourced("daily", "n/a")) is True
    assert eq.is_daily_estimate(_sourced("daily", float("nan"))) is True
    assert eq.is_trusted(_sourced("daily", float("nan"))) is False


def test_the_threshold_constant_is_two_days():
    assert eq.TRUSTED_MIN_HOLD_DAYS == 2.0


def test_excursion_summary_counts_sources_included_and_excluded():
    entries = [_sourced("5min", 0.2), _sourced("5min", 0.3), _sourced("daily", 0.4),
               _sourced("daily", 4.0), _sourced(None, 0.5), _entry()]
    summary = eq.excursion_summary(entries)
    assert summary == {"sources": {"5min": 2, "daily": 2, "none": 2},
                       "included": 3, "excluded": 1, "total": 6}


def test_excursion_summary_of_an_empty_book():
    assert eq.excursion_summary([]) == {"sources": {}, "included": 0,
                                        "excluded": 0, "total": 0}


def test_scatter_points_carry_the_source():
    points = eq.mfe_mae_points([_sourced("5min", 0.2), _entry()])
    assert [p["excursion_source"] for p in points] == ["5min", None]


def test_aggregates_over_trusted_entries_drop_short_daily_holds():
    entries = [_sourced("5min", 0.2, exit_efficiency=0.9),
               _sourced("daily", 0.3, exit_efficiency=0.1),
               _sourced("daily", 2.5, exit_efficiency=0.5)]
    trusted = [e for e in entries if eq.is_trusted(e)]
    result = eq.efficiency_histogram(trusted, bins=2)
    assert result["n"] == 2 and result["median"] == pytest.approx(0.7)
