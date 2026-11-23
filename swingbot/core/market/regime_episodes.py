"""v239: confirmed regime episodes, the smoothing people read.

bear_regime's day label is raw (the B7-B9 screens use it as is). A change of
episode key is CONFIRMED when the new key holds on CONFIRM_SESSIONS
consecutive labelled sessions; that run becomes the episode and its "since"
count starts on its first day. A shorter run is flicker: it stays in the
stored day rows, is never notified, and is merged into the episode it
interrupts (flicker before the first episode belongs to none). Sessions are
counted as labelled rows, so a stored gap is not padded. Shared by the live
notice (regime_notices), the API's "since" count and the 1993 study.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from swingbot.core.market import bear_regime as br

CONFIRM_SESSIONS: Final = 2
BEAR_KEY: Final = "BEAR"
CORRECTION_STRESS_KEY: Final = "CORRECTION_STRESS"
CORRECTION_KEY: Final = "CORRECTION"
NORMAL_KEY: Final = "NORMAL"
UNKNOWN_KEY: Final = "UNKNOWN"
EPISODE_KEYS: Final = (BEAR_KEY, CORRECTION_STRESS_KEY, CORRECTION_KEY, NORMAL_KEY, UNKNOWN_KEY)


@dataclass(frozen=True)
class Episode:
    key: str
    start: dt.date
    end: dt.date
    sessions: int


@dataclass(frozen=True)
class Transition:
    old: str | None
    new: str


def episode_key(state: str, stress: bool | None) -> str:
    """BEAR ignores stress (the vocabulary has no "Bear · Stress")."""
    if state == br.CORRECTION:
        return CORRECTION_STRESS_KEY if stress is True else CORRECTION_KEY
    if state in (br.BEAR, br.NORMAL):
        return state
    return UNKNOWN_KEY


def _runs(days: Sequence[tuple[dt.date, str]]) -> list[tuple[str, dt.date, dt.date, int]]:
    runs: list[tuple[str, dt.date, dt.date, int]] = []
    for day, key in sorted(days, key=lambda item: item[0]):
        if runs and runs[-1][0] == key:
            _, start, _, count = runs[-1]
            runs[-1] = (key, start, day, count + 1)
        else:
            runs.append((key, day, day, 1))
    return runs


def confirmed_episodes(days: Sequence[tuple[dt.date, str]]) -> list[Episode]:
    """``(session_date, episode key)`` pairs -> confirmed episodes, oldest first."""
    episodes: list[Episode] = []
    for key, start, end, count in _runs(days):
        last = episodes[-1] if episodes else None
        if last is not None and (count < CONFIRM_SESSIONS or last.key == key):
            episodes[-1] = Episode(last.key, last.start, end, last.sessions + count)
        elif count >= CONFIRM_SESSIONS:
            episodes.append(Episode(key, start, end, count))
    return episodes


def current_episode(days: Sequence[tuple[dt.date, str]]) -> Episode | None:
    episodes = confirmed_episodes(days)
    return episodes[-1] if episodes else None


def confirmed_transition(prior: Sequence[tuple[dt.date, str]],
                         new: tuple[dt.date, str]) -> Transition | None:
    """The transition ``new`` confirms, or None (flicker, no change, a first NORMAL)."""
    before = current_episode(prior)
    after = current_episode([*prior, new])
    if after is None or after.end != new[0]:
        return None
    if before is not None and before.key == after.key:
        return None
    if before is None and after.key == NORMAL_KEY:
        return None
    return Transition(before.key if before else None, after.key)
