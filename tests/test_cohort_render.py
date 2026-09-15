from swingbot.core.scanning.plan_table import cohort_line


def _plan(label, **stats):
    class P:
        cohort_label = label
        cohort_stats = dict({"regime2_state": "bear_volatile", "win_rate": 41.2,
                             "expectancy_r": -0.38, "n_live": 100,
                             "n_backtest": 500, "run_date": "2026-09-14"}, **stats)
        direction = "bearish"
    return P()


def test_poor_renders_the_caution_with_its_own_numbers():
    line = cohort_line(_plan("COHORT_POOR"))
    assert "⚠️" in line
    assert "bear volatile" in line
    assert "41.2" in line
    assert "-0.38" in line
    assert "600" in line          # n_live + n_backtest
    assert "2026-09-14" in line


def test_typical_renders_nothing():
    assert cohort_line(_plan("COHORT_TYPICAL")) is None


def test_strong_renders_a_stat_line_without_a_warning():
    line = cohort_line(_plan("COHORT_STRONG", win_rate=61.0, expectancy_r=0.42))
    assert "⚠️" not in line
    assert "61.0" in line


def test_unknown_says_not_enough_data_never_safe():
    line = cohort_line(_plan("COHORT_UNKNOWN"))
    assert "Not enough" in line
    assert "safe" not in line.lower()


def test_a_plan_with_no_cohort_stats_renders_nothing_rather_than_crashing():
    class P:
        cohort_label = "COHORT_POOR"
        cohort_stats = {}
        direction = "bearish"
    assert cohort_line(P()) is None
