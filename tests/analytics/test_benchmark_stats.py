"""v208 V208-7: benchmark stats -- known values, empty inputs and the N guards."""
import math

import pytest

from swingbot.core.analytics import benchmark as bm


def _fixture(n=60):
    idx = [0.01 * math.sin(1.7 * i) + 0.002 * ((i % 5) - 2) for i in range(n)]
    bot = [0.0004 + 0.6 * x + 0.003 * math.cos(2.3 * i) for i, x in enumerate(idx)]
    return bot, idx


BOT, IDX = _fixture()


def test_constants_and_reasons():
    assert (bm.TRADING_DAYS, bm.MIN_BETA_N, bm.MIN_SHARPE_N, bm.MIN_ALPHA_N, bm.MIN_CAPTURE_SIDE_N) == \
        (252, 20, 20, 60, 10)
    assert bm.needs(20) == "needs ≥ 20 sessions"


def test_total_and_cumulative():
    assert bm.total_return([0.1, -0.1]) == pytest.approx(-0.01)
    assert bm.cumulative([0.1, 0.1]) == pytest.approx([0.1, 0.21])
    assert bm.total_return(BOT) == pytest.approx(0.02280255021326738)
    assert bm.cumulative(BOT)[-1] == pytest.approx(bm.total_return(BOT))


def test_empty_and_single_session_inputs():
    assert bm.total_return([]) is None
    assert bm.cumulative([]) == []
    assert bm.max_drawdown([]) is None
    assert bm.money_drawdown([]) is None
    assert bm.losing_streak([]) == 0
    assert bm.total_return([0.02]) == pytest.approx(0.02)
    assert bm.max_drawdown([0.02]) == 0.0
    assert bm.money_drawdown([10_000.0]) == 0.0
    empty = bm.sharpe([])
    assert (empty.value, empty.n, empty.reason) == (None, 0, "needs ≥ 20 sessions")


@pytest.mark.parametrize("returns, expected", [
    ([0.1, -0.5, 0.2], -0.5),
    ([-0.1], -0.1),            # the base close is the first peak
    ([0.05, 0.05], 0.0),
])
def test_max_drawdown_is_a_non_positive_fraction(returns, expected):
    assert bm.max_drawdown(returns) == pytest.approx(expected)


def test_money_drawdown_and_losing_streak():
    assert bm.money_drawdown([10_000.0, 10_500.0, 9_800.0, 10_200.0, 9_700.0]) == pytest.approx(-800.0)
    assert bm.losing_streak([0.01, -0.01, -0.02, 0.0, -0.01, -0.01, -0.01, 0.02]) == 3


def test_sharpe_known_value_ddof_1():
    est = bm.sharpe(BOT)
    assert est.value == pytest.approx(1.2465510910232496)
    assert (est.n, est.reason, est.se, est.t) == (60, None, None, None)


def test_sharpe_guards():
    short = bm.sharpe(BOT[:19])
    assert (short.value, short.n, short.reason) == (None, 19, "needs ≥ 20 sessions")
    flat = bm.sharpe([0.001] * 25)
    assert (flat.value, flat.n, flat.reason) == (None, 25, bm.NO_VARIANCE)


def test_beta_with_standard_error_at_the_threshold():
    est = bm.beta(BOT[:20], IDX[:20])
    assert est.value == pytest.approx(0.5987039626951823)
    assert est.se == pytest.approx(0.06907751418848224)
    assert est.t == pytest.approx(0.5987039626951823 / 0.06907751418848224)
    assert (est.n, est.reason) == (20, None)


def test_beta_guards():
    short = bm.beta(BOT[:19], IDX[:19])
    assert (short.value, short.se, short.n, short.reason) == (None, None, 19, "needs ≥ 20 sessions")
    flat = bm.beta(BOT[:25], [0.0] * 25)
    assert (flat.value, flat.reason) == (None, bm.INDEX_FLAT)


def test_alpha_is_annualised_jensen_with_t_stat():
    est = bm.alpha(BOT, IDX)
    assert est.value == pytest.approx(0.1002628883975672)
    assert est.se == pytest.approx(0.07025359431166461)
    assert est.t == pytest.approx(1.4271567082073118)
    assert (est.n, est.reason) == (60, None)
    assert bm.beta(BOT, IDX).value == pytest.approx(0.5860686561580911)
    assert bm.beta(BOT, IDX).se == pytest.approx(0.03702029864741104)


def test_alpha_needs_sixty_sessions():
    est = bm.alpha(BOT[:59], IDX[:59])
    assert (est.value, est.se, est.t, est.n, est.reason) == (None, None, None, 59, "needs ≥ 60 sessions")


def test_an_exact_linear_fit_has_zero_error():
    idx = IDX
    bot = [0.002 + 0.5 * x for x in idx]
    assert bm.beta(bot, idx).value == pytest.approx(0.5)
    assert bm.beta(bot, idx).se == pytest.approx(0.0, abs=1e-9)
    assert bm.alpha(bot, idx).value == pytest.approx(0.504)


def test_capture_sum_ratio_and_beat_count():
    cap = bm.capture(BOT, IDX)
    assert (cap.up_n, cap.down_n, cap.reason) == (31, 29, None)
    assert cap.up == pytest.approx(0.6186249784112493)
    assert cap.down == pytest.approx(0.4932598706459592)
    assert cap.ratio == pytest.approx(1.2541563083190115)
    assert bm.beat_count(BOT, IDX) == bm.BeatCount(up_days=31, up_beat=7, down_days=29, down_beat=26)


def test_flat_index_days_are_excluded_from_capture_and_beat():
    bot, idx = BOT + [0.05, -0.05], IDX + [0.0, 0.0]
    assert bm.capture(bot, idx) == bm.capture(BOT, IDX)
    assert bm.beat_count(bot, idx) == bm.beat_count(BOT, IDX)


def test_capture_needs_ten_sessions_each_side():
    cap = bm.capture([0.01] * 19, [0.01] * 10 + [-0.01] * 9)
    assert (cap.up, cap.down, cap.ratio, cap.up_n, cap.down_n) == (None, None, None, 10, 9)
    assert cap.reason == bm.CAPTURE_REASON == "needs ≥ 10 index-up and ≥ 10 index-down sessions"


def test_an_all_flat_index_has_no_capture():
    cap = bm.capture([0.01] * 30, [0.0] * 30)
    assert (cap.up, cap.ratio, cap.up_n, cap.down_n, cap.reason) == (None, None, 0, 0, bm.CAPTURE_REASON)


@pytest.mark.parametrize("fn", [bm.beta, bm.alpha, bm.capture, bm.beat_count])
def test_paired_functions_reject_mismatched_lengths(fn):
    with pytest.raises(ValueError):
        fn([0.01, 0.02], [0.01])
