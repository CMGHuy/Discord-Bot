"""v239 V239-3: one vocabulary, one number form, the alert line per state x
action; no glyphs, every line within MAX_LINE characters."""
from datetime import date

import pytest

from swingbot.core.market import bear_regime as br
from swingbot.core.market import regime_episodes as ep
from swingbot.core.presentation import regime_text as rt

MINUS = "−"
ALLOWED_NON_ASCII = {"·", "—"}          # middle dot, em dash (the spec's own)
LINES = {
    (br.BEAR, br.WOULD_VETO): "Regime: Bear (shadow) — engine would skip this long",
    (br.CORRECTION, br.WOULD_VETO): "Regime: Correction · Stress (shadow) — would skip long",
    (br.CORRECTION, br.CAUTION): "Regime: Correction — dip in an uptrend",
    (br.CORRECTION, br.PULLBACK_WATCH): "Regime: Pullback watch — panic easing in a correction",
    (br.BEAR, br.ALIGNED): "Regime: Bear — with the tape; squeeze risk on rebounds",
    (br.CORRECTION, br.ALIGNED): "Regime: Correction — short in a dip; uptrend intact",
}


@pytest.mark.parametrize("state, stress, pullback, label", [
    (br.BEAR, None, False, "Bear"), (br.BEAR, True, True, "Bear"),
    (br.CORRECTION, True, False, "Correction · Stress"),
    (br.CORRECTION, False, False, "Correction"), (br.CORRECTION, None, False, "Correction"),
    (br.CORRECTION, True, True, "Pullback watch"), (br.NORMAL, None, False, "Normal"),
    (br.UNKNOWN, None, False, "No reading"), ("garbage", None, False, "No reading")])
def test_label_for(state, stress, pullback, label):
    assert rt.label_for(state, stress, pullback) == label


@pytest.mark.parametrize("state, stress, pullback, words", [
    (br.BEAR, None, False, "trend has turned down"),
    (br.CORRECTION, True, False, "dip in an uptrend, high volatility"),
    (br.CORRECTION, False, False, "dip in an uptrend"),
    (br.CORRECTION, False, True, "panic easing inside a correction"),
    (br.UNKNOWN, None, False, "—")])
def test_words_for(state, stress, pullback, words):
    assert rt.words_for(state, stress, pullback) == words


def test_tables_cover_every_episode_key_and_pullback():
    assert set(rt.LABELS) == set(rt.WORDS) == set(ep.EPISODE_KEYS) | {rt.PULLBACK}


def test_number_line_is_the_spec_form():
    line = rt.number_line(spy_close=94.3, sma50=104.0, sma200=100.0, vix_close=37.6)
    assert line == f"SPY {MINUS}5.7% vs SMA200 · {MINUS}9.3% vs SMA50 · VIX 37.6"


def test_number_line_signs_and_missing_parts():
    assert rt.number_line(spy_close=105.0, sma50=100.0, sma200=50.0, vix_close=None) == \
        "SPY +110.0% vs SMA200 · +5.0% vs SMA50"
    assert rt.number_line(spy_close=None, sma50=1.0, sma200=1.0, vix_close=20.0) is None
    assert rt.number_line(spy_close=1.0, sma50=None, sma200=1.0, vix_close=20.0) is None


def test_display_reads_the_day():
    day = br.RegimeDay(session_date=date(2026, 11, 23), last_bar_date=date(2026, 11, 20),
                       state=br.CORRECTION, stress=True, pullback_trigger=True,
                       spy_close=94.3, sma50=104.0, sma200=100.0, vix_close=37.6)
    assert rt.display(day) == {"label": "Pullback watch", "words": "panic easing inside a correction",
                               "numbers": f"SPY {MINUS}5.7% vs SMA200 · {MINUS}9.3% vs SMA50 · VIX 37.6"}
    unknown = br.RegimeDay(session_date=date(2026, 11, 23), last_bar_date=None, state=br.UNKNOWN)
    assert rt.display(unknown) == {"label": "No reading", "words": "—", "numbers": None}


@pytest.mark.parametrize("key", sorted(LINES))
def test_alert_line_per_case_within_the_cap(key):
    line = rt.alert_line(*key)
    assert line == LINES[key]
    assert len(line) <= rt.MAX_LINE == 80


@pytest.mark.parametrize("state, action", [
    (br.NORMAL, br.NONE), (br.UNKNOWN, br.NONE), (br.BEAR, br.NONE), (br.BEAR, br.CAUTION),
    (None, None), (br.CORRECTION, None)])
def test_no_line_outside_the_table(state, action):
    assert rt.alert_line(state, action) is None


def test_no_glyphs_anywhere():
    texts = [*rt.LABELS.values(), *rt.WORDS.values(), *LINES.values()]
    assert {ch for text in texts for ch in text if ord(ch) > 127} <= ALLOWED_NON_ASCII
