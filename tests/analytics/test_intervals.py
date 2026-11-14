"""v219: the Wilson score interval used for every share on the Partials tab."""
import pytest

from swingbot.core.analytics.intervals import wilson_interval


@pytest.mark.parametrize("k, n, lo, hi", [
    (1, 4, 0.045586, 0.699364),
    (1, 3, 0.061490, 0.792345),
    (1, 2, 0.094529, 0.905471),
    (5, 10, 0.236590, 0.763410),
])
def test_reference_values(k, n, lo, hi):
    got = wilson_interval(k, n)
    assert got == pytest.approx((lo, hi), abs=1e-6)


def test_zero_successes_pins_the_lower_bound_at_zero():
    lo, hi = wilson_interval(0, 3)
    assert lo == 0.0
    assert hi == pytest.approx(0.561506, abs=1e-6)


def test_all_successes_pins_the_upper_bound_at_one():
    lo, hi = wilson_interval(3, 3)
    assert hi == 1.0
    assert lo == pytest.approx(0.438494, abs=1e-6)


@pytest.mark.parametrize("n", [6, 11, 21, 22, 27])
def test_the_ends_are_exact_where_floats_drift(n):
    assert wilson_interval(0, n)[0] == 0.0
    assert wilson_interval(n, n)[1] == 1.0


def test_bounds_stay_inside_zero_and_one_and_bracket_the_rate():
    for n in range(1, 30):
        for k in range(n + 1):
            lo, hi = wilson_interval(k, n)
            assert 0.0 <= lo <= k / n <= hi <= 1.0


def test_a_wider_z_gives_a_wider_interval():
    lo95, hi95 = wilson_interval(5, 10)
    lo99, hi99 = wilson_interval(5, 10, z=2.576)
    assert lo99 < lo95 and hi99 > hi95
    assert (lo99, hi99) == pytest.approx((0.184213, 0.815787), abs=1e-6)


@pytest.mark.parametrize("n", [0, -1])
def test_no_trials_is_none_not_an_error(n):
    assert wilson_interval(0, n) is None


@pytest.mark.parametrize("k, n", [(-1, 3), (4, 3)])
def test_successes_outside_the_trials_are_rejected(k, n):
    with pytest.raises(ValueError):
        wilson_interval(k, n)
