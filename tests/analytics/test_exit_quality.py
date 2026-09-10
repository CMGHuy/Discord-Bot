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
