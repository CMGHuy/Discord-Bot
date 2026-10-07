"""v136 §4: BH q-values across the pre-registration ledger. Reported, never gating."""
import pytest

from swingbot.core.backtesting.instrument import stats


def test_textbook_example():
    # sorted .005 .01 .03 .04, m=4: raw .02 .02 .04 .04
    assert stats.bh_qvalues([0.01, 0.04, 0.03, 0.005]) == pytest.approx(
        [0.02, 0.04, 0.04, 0.02])


def test_step_up_takes_the_running_minimum_from_the_top():
    # the smaller p's raw value is 0.04 * 2 / 1 = 0.08; the larger p's 0.041 caps it
    assert stats.bh_qvalues([0.04, 0.041]) == pytest.approx([0.041, 0.041])


def test_ties_share_one_q():
    assert stats.bh_qvalues([0.02, 0.02, 0.5]) == pytest.approx([0.03, 0.03, 0.5])


def test_q_never_falls_below_p_and_never_exceeds_one():
    ps = [0.001, 0.2, 0.5, 0.9, 1.0, 0.03]
    qs = stats.bh_qvalues(ps)
    assert all(p <= q <= 1.0 for p, q in zip(ps, qs))


def test_q_is_monotone_in_p():
    ps = [0.3, 0.001, 0.02, 0.02, 0.6]
    qs = stats.bh_qvalues(ps)
    order = sorted(range(len(ps)), key=ps.__getitem__)
    assert [qs[i] for i in order] == sorted(qs)


def test_null_p_values_pass_through_and_do_not_count_toward_m():
    assert stats.bh_qvalues([None, 0.01, None, 0.04]) == [
        None, pytest.approx(0.02), None, pytest.approx(0.04)]


def test_a_single_p_value_is_its_own_q():
    assert stats.bh_qvalues([0.7]) == pytest.approx([0.7])


def test_empty_input():
    assert stats.bh_qvalues([]) == []


def test_accepts_any_iterable():
    assert stats.bh_qvalues(p for p in (0.01, 0.04)) == pytest.approx([0.02, 0.04])


@pytest.mark.parametrize("bad", [-0.1, 1.5, float("nan")])
def test_an_out_of_range_p_is_refused(bad):
    with pytest.raises(ValueError, match="p-value"):
        stats.bh_qvalues([0.01, bad])
