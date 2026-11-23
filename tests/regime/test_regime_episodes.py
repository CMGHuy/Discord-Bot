"""v239 V239-3: confirmed episodes -- two consecutive labelled sessions confirm a
key; a shorter run is flicker, merged into the episode it interrupts."""
from datetime import date, timedelta

import pytest

from swingbot.core.market import bear_regime as br
from swingbot.core.market import regime_episodes as ep

A, B, C, N = ep.CORRECTION_KEY, ep.BEAR_KEY, ep.CORRECTION_STRESS_KEY, ep.NORMAL_KEY
DAY0 = date(2026, 10, 1)


def _days(keys, start=DAY0):
    return [(start + timedelta(days=i), key) for i, key in enumerate(keys)]


def _day(i):
    return DAY0 + timedelta(days=i)


@pytest.mark.parametrize("state, stress, key", [
    (br.BEAR, None, ep.BEAR_KEY), (br.BEAR, True, ep.BEAR_KEY),
    (br.CORRECTION, True, ep.CORRECTION_STRESS_KEY), (br.CORRECTION, False, ep.CORRECTION_KEY),
    (br.CORRECTION, None, ep.CORRECTION_KEY), (br.NORMAL, True, ep.NORMAL_KEY),
    (br.UNKNOWN, None, ep.UNKNOWN_KEY), ("garbage", None, ep.UNKNOWN_KEY)])
def test_episode_key(state, stress, key):
    assert ep.episode_key(state, stress) == key


def test_constants():
    assert ep.CONFIRM_SESSIONS == 2
    assert ep.EPISODE_KEYS == ("BEAR", "CORRECTION_STRESS", "CORRECTION", "NORMAL", "UNKNOWN")


def test_no_days_no_episode():
    assert ep.confirmed_episodes([]) == [] and ep.current_episode([]) is None


def test_a_single_session_never_confirms():
    assert ep.confirmed_episodes(_days([A])) == []


def test_two_sessions_confirm_and_start_on_the_first():
    assert ep.confirmed_episodes(_days([A, A])) == [ep.Episode(A, _day(0), _day(1), 2)]


def test_flicker_merges_into_the_episode_it_interrupts():
    assert ep.confirmed_episodes(_days([A, A, B, A, A])) == [ep.Episode(A, _day(0), _day(4), 5)]


def test_leading_flicker_belongs_to_no_episode():
    assert ep.confirmed_episodes(_days([B, A, A])) == [ep.Episode(A, _day(1), _day(2), 2)]


def test_a_confirmed_change_opens_a_new_episode():
    assert ep.confirmed_episodes(_days([A, A, B, B, B])) == [
        ep.Episode(A, _day(0), _day(1), 2), ep.Episode(B, _day(2), _day(4), 3)]


def test_input_order_does_not_matter():
    days = _days([A, A, B, B])
    assert ep.confirmed_episodes(list(reversed(days))) == ep.confirmed_episodes(days)


def test_a_stored_gap_counts_labelled_sessions_not_calendar_days():
    days = [(date(2026, 10, 1), A), (date(2026, 10, 20), A)]
    assert ep.current_episode(days) == ep.Episode(A, date(2026, 10, 1), date(2026, 10, 20), 2)


def test_flicker_never_notifies():
    assert ep.confirmed_transition(_days([A, A]), (_day(2), B)) is None


def test_the_confirming_session_notifies_once():
    assert ep.confirmed_transition(_days([A, A, B]), (_day(3), B)) == ep.Transition(A, B)
    assert ep.confirmed_transition(_days([A, A, B, B]), (_day(4), B)) is None


def test_returning_after_flicker_is_no_transition():
    assert ep.confirmed_transition(_days([A, A, B]), (_day(3), A)) is None


def test_a_stress_change_inside_a_correction_is_a_transition():
    assert ep.confirmed_transition(_days([A, A, C]), (_day(3), C)) == ep.Transition(A, C)


def test_first_reading_notifies_with_no_old_key():
    assert ep.confirmed_transition([], (_day(0), A)) is None
    assert ep.confirmed_transition(_days([A]), (_day(1), A)) == ep.Transition(None, A)


def test_a_first_normal_episode_stays_silent():
    assert ep.confirmed_transition(_days([N]), (_day(1), N)) is None
    assert ep.confirmed_transition(_days([A, A, N]), (_day(3), N)) == ep.Transition(A, N)
