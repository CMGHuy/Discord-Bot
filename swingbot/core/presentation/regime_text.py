"""v239: the one regime vocabulary and number form.

Every surface renders through here: the alert line (alert_embeds), the
transition notice (regime_notices), the API's display fields and so the
banner. Numbers use one form, SPY as a signed percent from each average then
VIX as a level ("SPY −5.7% vs SMA200 · −9.3% vs SMA50 · VIX 37.6", U+2212
through tokens.fmt_pct). No glyphs: plain-text channels render the same.
Alert lines say what the engine WOULD do (shadow) and never give an order
instruction; each is at most MAX_LINE characters.
"""
from __future__ import annotations

from typing import Final

from swingbot.core.market import bear_regime as br
from swingbot.core.market import regime_episodes as ep
from swingbot.core.presentation.tokens import fmt_pct

MAX_LINE: Final = 80
PULLBACK: Final = "PULLBACK"

LABELS: Final[dict[str, str]] = {
    ep.BEAR_KEY: "Bear",
    ep.CORRECTION_STRESS_KEY: "Correction · Stress",
    ep.CORRECTION_KEY: "Correction",
    ep.NORMAL_KEY: "Normal",
    ep.UNKNOWN_KEY: "No reading",
    PULLBACK: "Pullback watch",
}
WORDS: Final[dict[str, str]] = {
    ep.BEAR_KEY: "trend has turned down",
    ep.CORRECTION_STRESS_KEY: "dip in an uptrend, high volatility",
    ep.CORRECTION_KEY: "dip in an uptrend",
    ep.NORMAL_KEY: "no correction or bear trend",
    ep.UNKNOWN_KEY: "—",
    PULLBACK: "panic easing inside a correction",
}
_LINES: Final[dict[tuple[str, str], str]] = {
    (br.BEAR, br.WOULD_VETO): "Regime: Bear (shadow) — engine would skip this long",
    (br.CORRECTION, br.WOULD_VETO): "Regime: Correction · Stress (shadow) — would skip long",
    (br.CORRECTION, br.CAUTION): "Regime: Correction — dip in an uptrend",
    (br.CORRECTION, br.PULLBACK_WATCH): "Regime: Pullback watch — panic easing in a correction",
    (br.BEAR, br.ALIGNED): "Regime: Bear — with the tape; squeeze risk on rebounds",
    (br.CORRECTION, br.ALIGNED): "Regime: Correction — short in a dip; uptrend intact",
}


def _key(state: str, stress: bool | None, pullback: bool) -> str:
    if pullback and state == br.CORRECTION:
        return PULLBACK
    return ep.episode_key(state, stress)


def label_for(state: str, stress: bool | None, pullback: bool = False) -> str:
    return LABELS[_key(state, stress, pullback)]


def words_for(state: str, stress: bool | None, pullback: bool = False) -> str:
    return WORDS[_key(state, stress, pullback)]


def _pct(close: float, average: float) -> float:
    return (close / average - 1.0) * 100.0


def number_line(*, spy_close: float | None, sma50: float | None, sma200: float | None,
                vix_close: float | None) -> str | None:
    if spy_close is None or not sma50 or not sma200:
        return None
    parts = [f"SPY {fmt_pct(_pct(spy_close, sma200))} vs SMA200",
             f"{fmt_pct(_pct(spy_close, sma50))} vs SMA50"]
    if vix_close is not None:
        parts.append(f"VIX {vix_close:.1f}")
    return " · ".join(parts)


def display(day: br.RegimeDay) -> dict:
    """The API's ``display`` block: ``{"label", "words", "numbers"}``."""
    return {"label": label_for(day.state, day.stress, day.pullback_trigger),
            "words": words_for(day.state, day.stress, day.pullback_trigger),
            "numbers": number_line(spy_close=day.spy_close, sma50=day.sma50,
                                   sma200=day.sma200, vix_close=day.vix_close)}


def alert_line(state: str | None, action: str | None) -> str | None:
    """The one alert line for a plan's stamped state and action, or None."""
    return _LINES.get((state, action))
