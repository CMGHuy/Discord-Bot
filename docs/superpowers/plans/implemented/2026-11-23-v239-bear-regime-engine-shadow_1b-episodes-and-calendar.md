# v239 — Bear-regime engine (shadow): Part 1b, episodes, vocabulary and the live calendar

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V239-3" -A 400 <this file>`); never read the file whole.

**Bump:** bot minor, ui minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-23-v239-bear-regime-engine-shadow-design.md](../specs/2026-11-23-v239-bear-regime-engine-shadow-design.md)
**Index:** [2026-11-23-v239-bear-regime-engine-shadow_0-index.md](2026-11-23-v239-bear-regime-engine-shadow_0-index.md). Its Goal, Global Constraints, Parallelisation and Task ledger apply to every task here.

Part 1 of the index (V239-1..V239-4) is written across two files because the full tasks pass the 1500-line file cap together: `_1-classifier.md` holds V239-1, V239-2 and V239-2b; this file holds V239-3 (confirmed episodes and the one vocabulary every surface renders through) and V239-4 (the half-day-aware `(s, D)` session pair and the completed-bar cut). Every test lands in `tests/regime/`, which V239-1 adds to suite `market-signals`. Run each task's tests with `python scripts/dev/testrun.py file <test>`; no task here runs the full suite or reaches Postgres.

# Phase 1 (continued) — Episodes, vocabulary, calendar

### Task V239-3: Confirmed episodes and the shared vocabulary

**Model:** sonnet — two small pure modules on a fixed table and a fixed merge rule, fully specified here.

**Why:** the day label is raw, but people read smoothed state (spec § Confirmed transitions): a change counts once it holds on two consecutive labelled sessions, and a shorter run is flicker that is stored but never notified and is merged into the episode it interrupts. The notice (V239-7), the API's "since" count (V239-12) and the 1993 study (V239-17) all need that one rule. Every surface also needs one vocabulary and one number form (spec § One vocabulary, one number form; § Discord alert line; reconciliation 6 adds the SHORT-in-CORRECTION line), with no glyphs and alert lines of at most 80 characters.

**Files:**
- Create: `swingbot/core/market/regime_episodes.py`
- Create: `swingbot/core/presentation/regime_text.py`
- Create: `tests/regime/test_regime_episodes.py`
- Create: `tests/regime/test_regime_text.py`

**Interfaces:**
- Consumes (V239-2/2b, `swingbot.core.market.bear_regime`): state constants `BEAR`, `CORRECTION`, `NORMAL`, `UNKNOWN`; action constants `WOULD_VETO`, `CAUTION`, `PULLBACK_WATCH`, `ALIGNED`; `RegimeDay` (fields `state`, `stress`, `pullback_trigger`, `spy_close`, `sma50`, `sma200`, `vix_close`). `swingbot.core.presentation.tokens.fmt_pct(x: float | None) -> str` (takes a percent number; `"+1.0%"`, U+2212 minus for negatives).
- Produces (ledger contract, final):
  - `regime_episodes`: `CONFIRM_SESSIONS = 2`; keys `BEAR_KEY = "BEAR"`, `CORRECTION_STRESS_KEY = "CORRECTION_STRESS"`, `CORRECTION_KEY = "CORRECTION"`, `NORMAL_KEY = "NORMAL"`, `UNKNOWN_KEY = "UNKNOWN"`, `EPISODE_KEYS` (that order); `episode_key(state: str, stress: bool | None) -> str` (BEAR ignores stress; any unrecognised state gives `UNKNOWN_KEY`); `@dataclass(frozen=True) Episode(key: str, start: date, end: date, sessions: int)`; `confirmed_episodes(days: Sequence[tuple[date, str]]) -> list[Episode]` (input is `(session_date, episode key)` pairs, sorted by date inside, oldest episode first); `current_episode(days) -> Episode | None`; `@dataclass(frozen=True) Transition(old: str | None, new: str)`; `confirmed_transition(prior: Sequence[tuple[date, str]], new: tuple[date, str]) -> Transition | None`.
  - `confirmed_transition` returns a `Transition` only on the session that confirms a new episode key: `old` is the previous confirmed episode's key, or `None` for a first reading. A first confirmed `NORMAL` returns `None` (index decision 4). A pullback day is not an episode key; V239-7 notifies it on its own.
  - `regime_text`: `MAX_LINE = 80`; `PULLBACK = "PULLBACK"`; `LABELS: dict[str, str]` and `WORDS: dict[str, str]` keyed by `EPISODE_KEYS + (PULLBACK,)`; `label_for(state, stress, pullback=False) -> str`; `words_for(state, stress, pullback=False) -> str`; `number_line(*, spy_close, sma50, sma200, vix_close) -> str | None`; `display(day: RegimeDay) -> dict` (`{"label", "words", "numbers"}`); `alert_line(state: str | None, action: str | None) -> str | None`.

**Vocabulary this task fixes:** the spec's table, plus two entries it leaves open: `NORMAL` reads `Normal` / `no correction or bear trend` (only the notice headline "Correction → Normal" shows it), and `UNKNOWN`'s words stay the spec's `—`.

- [ ] **Step 1: Write the failing episode tests**

Create `tests/regime/test_regime_episodes.py`:

```python
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
```

- [ ] **Step 2: Write the failing vocabulary tests**

Create `tests/regime/test_regime_text.py`:

```python
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
```

- [ ] **Step 3: Run both files to see them fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_episodes.py`
Expected: collection error, `ImportError: cannot import name 'regime_episodes'`.

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_text.py`
Expected: collection error, `ImportError: cannot import name 'regime_text'`.

- [ ] **Step 4: Write `regime_episodes`**

Create `swingbot/core/market/regime_episodes.py`:

```python
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
```

- [ ] **Step 5: Write `regime_text`**

Create `swingbot/core/presentation/regime_text.py`:

```python
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
```

- [ ] **Step 6: Run both files to see them pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_episodes.py`
Expected: `0 failed`.

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_text.py`
Expected: `0 failed`.

Run: `python -m radon cc -s -n C swingbot/core/market/regime_episodes.py swingbot/core/presentation/regime_text.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/market/regime_episodes.py swingbot/core/presentation/regime_text.py tests/regime/test_regime_episodes.py tests/regime/test_regime_text.py
git commit -m "feat(v239): confirmed regime episodes and the shared regime vocabulary"
```

### Task V239-4: Live session pair and completed-bar cut (half-day aware)

**Model:** opus — calendar edge cases (weekend, holiday, early close, after-close-before-refresher) decide which bar the live label reads; a wrong cut is lookahead or a frozen stale label.

**Why:** the label is for session `D` and reads only bars dated `≤ s` (spec § Indexing). `strategy_pass.completed_frame` is weekday 09:30–16:00 only (spec reconciliation 2): between 13:00 and 16:00 on a half-day it drops that session's completed bar, so the spec's "a half-day counts as completed after its early close" fails with it. The pair therefore comes from the half-day-aware `session` helpers, and the cut keeps every bar dated on or before `s`. On every regular day this equals `completed_frame`'s result (pinned below); on a half-day after 13:00 it keeps the completed bar that `completed_frame` would drop, and before the open it also drops a provider's early bar dated today. `sessions_between` gives V239-7 its "after a gap of N sessions" count.

**Files:**
- Create: `swingbot/core/scanning/regime_calendar.py`
- Create: `tests/regime/test_regime_calendar.py`

**Interfaces:**
- Consumes: `swingbot.core.market.session.last_regular_close(now) -> datetime` (UTC instant of the latest NYSE close at or before `now`; 13:00 ET on early-close days, holidays skipped), `session.US_MARKET_TZ`, `session.nyse_calendar() -> SessionCalendar` (`.next_session(d)` = first session strictly after `d`, `.sessions(start, end)` inclusive; covers 2018–2030). Tests also import `swingbot.core.scanning.strategy_pass.completed_frame(df, now)`.
- Produces (ledger contract, final):
  - `session_pair(now: datetime) -> tuple[date, date]`: `(s, D)`; raises `ValueError` only past the frozen calendar's end.
  - `cut_completed(df: DataFrame, now: datetime) -> DataFrame`: the rows dated `≤ s` (wall date of each index entry, naive or tz-aware); `None` and empty frames are returned unchanged.
  - `sessions_between(older: date, newer: date) -> int`: NYSE sessions after `older` up to and including `newer`; `0` when `newer ≤ older`.

- [ ] **Step 1: Write the failing tests**

Create `tests/regime/test_regime_calendar.py`:

```python
"""v239 V239-4: the live (s, D) pair and the completed-bar cut. One case per
calendar situation the spec names: weekend, holiday, half-day, and a scan
after the close but before the refresher ran. November 2026: Thanksgiving is
Thu 11-26 (holiday), Fri 11-27 closes at 13:00 ET; Dec 24 closes at 13:00 and
Dec 25 is a holiday."""
import datetime as dt
from datetime import date

import pandas as pd
import pytest

from swingbot.core.market import session
from swingbot.core.scanning import regime_calendar as rc
from swingbot.core.scanning.strategy_pass import completed_frame


def _et(month, day, hour, minute=0):
    return dt.datetime(2026, month, day, hour, minute, tzinfo=session.US_MARKET_TZ)


def _frame(end: date, tz=None) -> pd.DataFrame:
    """Real NYSE sessions (no bar on a holiday) from 2026-01-02 through ``end``."""
    days = session.nyse_calendar().sessions(date(2026, 1, 2), end)
    if not session.nyse_calendar().is_session(end):
        days.append(end)                                   # a stray early bar dated ``end``
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in days], name="Date")
    if tz:
        index = index.tz_localize(tz)
    closes = [float(i) for i in range(len(index))]
    return pd.DataFrame({"High": closes, "Close": closes}, index=index)


@pytest.mark.parametrize("now, s, d", [
    (_et(11, 23, 11), date(2026, 11, 20), date(2026, 11, 23)),     # Monday, in session
    (_et(11, 23, 15, 59), date(2026, 11, 20), date(2026, 11, 23)),
    (_et(11, 23, 16), date(2026, 11, 23), date(2026, 11, 24)),     # the close itself
    (_et(11, 23, 16, 30), date(2026, 11, 23), date(2026, 11, 24)),  # after close, before refresher
    (_et(11, 24, 8), date(2026, 11, 23), date(2026, 11, 24)),      # pre-market
    (_et(11, 21, 12), date(2026, 11, 20), date(2026, 11, 23)),     # Saturday
    (_et(11, 22, 20), date(2026, 11, 20), date(2026, 11, 23)),     # Sunday
    (_et(11, 25, 20), date(2026, 11, 25), date(2026, 11, 27)),     # skips Thanksgiving
    (_et(11, 26, 12), date(2026, 11, 25), date(2026, 11, 27)),     # on the holiday
    (_et(11, 27, 12, 59), date(2026, 11, 25), date(2026, 11, 27)),  # half-day, before 13:00
    (_et(11, 27, 13), date(2026, 11, 27), date(2026, 11, 30)),     # half-day, at its close
    (_et(11, 27, 14), date(2026, 11, 27), date(2026, 11, 30)),     # half-day, after its close
    (_et(12, 24, 14), date(2026, 12, 24), date(2026, 12, 28)),     # Dec 24 half-day, Dec 25 shut
])
def test_session_pair(now, s, d):
    assert rc.session_pair(now) == (s, d)


def test_session_pair_reads_a_utc_clock():
    now = dt.datetime(2026, 11, 23, 21, 30, tzinfo=dt.timezone.utc)   # 16:30 ET
    assert rc.session_pair(now) == (date(2026, 11, 23), date(2026, 11, 24))


def test_an_intraday_partial_bar_is_cut():
    df = _frame(date(2026, 11, 23))
    out = rc.cut_completed(df, _et(11, 23, 11))
    assert out.index[-1] == pd.Timestamp("2026-11-20")
    pd.testing.assert_frame_equal(out, df.iloc[:-1])


def test_after_the_close_the_session_bar_is_kept():
    df = _frame(date(2026, 11, 23))
    pd.testing.assert_frame_equal(rc.cut_completed(df, _et(11, 23, 16, 30)), df)


def test_a_half_day_bar_counts_as_completed_after_the_early_close():
    df = _frame(date(2026, 11, 27))
    now = _et(11, 27, 14)
    pd.testing.assert_frame_equal(rc.cut_completed(df, now), df)
    # why completed_frame alone is not enough: it is blind to the 13:00 close
    assert len(completed_frame(df, now)) == len(df) - 1


def test_a_half_day_bar_is_cut_before_the_early_close():
    out = rc.cut_completed(_frame(date(2026, 11, 27)), _et(11, 27, 12))
    assert out.index[-1] == pd.Timestamp("2026-11-25")


def test_a_premarket_bar_dated_today_is_cut():
    out = rc.cut_completed(_frame(date(2026, 11, 24)), _et(11, 24, 8))
    assert out.index[-1] == pd.Timestamp("2026-11-23")


def test_a_weekend_bar_is_cut():
    out = rc.cut_completed(_frame(date(2026, 11, 21)), _et(11, 21, 12))      # stray Saturday bar
    assert out.index[-1] == pd.Timestamp("2026-11-20")


@pytest.mark.parametrize("end, now", [
    (date(2026, 11, 23), _et(11, 23, 11)),
    (date(2026, 11, 23), _et(11, 23, 16, 30)),
    (date(2026, 11, 23), _et(11, 24, 8)),
    (date(2026, 11, 20), _et(11, 21, 12)),
])
def test_on_regular_days_the_cut_equals_completed_frame(end, now):
    df = _frame(end)
    pd.testing.assert_frame_equal(rc.cut_completed(df, now), completed_frame(df, now))


def test_a_tz_aware_index_is_cut_by_its_wall_date():
    naive, aware = _frame(date(2026, 11, 23)), _frame(date(2026, 11, 23), tz="UTC")
    now = _et(11, 23, 11)
    assert list(rc.cut_completed(aware, now).index.date) == list(rc.cut_completed(naive, now).index.date)


@pytest.mark.parametrize("df", [None, pd.DataFrame({"Close": []})])
def test_nothing_to_cut_is_returned_unchanged(df):
    assert rc.cut_completed(df, _et(11, 23, 11)) is df


@pytest.mark.parametrize("older, newer, n", [
    (date(2026, 11, 20), date(2026, 11, 23), 1),
    (date(2026, 11, 25), date(2026, 11, 27), 1),     # Thanksgiving is not a session
    (date(2026, 11, 13), date(2026, 11, 23), 6),
    (date(2026, 11, 20), date(2026, 11, 30), 5),
    (date(2026, 11, 20), date(2026, 11, 20), 0),
    (date(2026, 11, 23), date(2026, 11, 20), 0),
])
def test_sessions_between(older, newer, n):
    assert rc.sessions_between(older, newer) == n
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_calendar.py`
Expected: collection error, `ImportError: cannot import name 'regime_calendar'`.

- [ ] **Step 3: Write the calendar module**

Create `swingbot/core/scanning/regime_calendar.py`:

```python
"""v239: the live (s, D) session pair and the completed-bar cut.

D is the NYSE session the bear-regime label is FOR; s is the last completed
session before it. s is the date of session.last_regular_close(now), which is
holiday-aware and closes a half-day at 13:00 ET; D is the next NYSE session
after s. A weekend, a holiday, a half-day after its early close, and a scan
after the close but before the refresher ran each map to one pair.

cut_completed keeps only bars dated on or before s. It does not call
strategy_pass.completed_frame: that helper is weekday 09:30-16:00 only, so
between 13:00 and 16:00 on a half-day it would drop the session's completed
bar. On a regular day the two cuts agree (tests/regime/test_regime_calendar.py).
The calendar covers 2018-2030 (session.NYSE_LAST_YEAR_COVERED); the 1993
base-rate study derives its sessions from the SPY bar index instead.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from swingbot.core.market import session


def session_pair(now: dt.datetime) -> tuple[dt.date, dt.date]:
    """``(s, D)``: the last completed NYSE session and the one the label is for."""
    last = session.last_regular_close(now).astimezone(session.US_MARKET_TZ).date()
    target = session.nyse_calendar().next_session(last)
    if target is None:
        raise ValueError(f"no NYSE session after {last} in the frozen calendar")
    return last, target


def cut_completed(df: pd.DataFrame | None, now: dt.datetime) -> pd.DataFrame | None:
    """Every bar dated on or before s; later bars (partial or stray) are dropped."""
    if df is None or len(df) == 0:
        return df
    last, _ = session_pair(now)
    return df.loc[pd.DatetimeIndex(df.index).date <= last]


def sessions_between(older: dt.date, newer: dt.date) -> int:
    """NYSE sessions after ``older`` up to and including ``newer``."""
    if newer <= older:
        return 0
    return len(session.nyse_calendar().sessions(older + dt.timedelta(days=1), newer))
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_calendar.py`
Expected: `0 failed`. If a `session_pair` case fails, check `session.NYSE_HOLIDAYS` holds `2026-11-26` and `2026-12-25` and `session.is_early_close` returns True for `2026-11-27` and `2026-12-24` before changing anything: the expectations follow the NYSE 2026 calendar.

Run: `python -m radon cc -s -n C swingbot/core/scanning/regime_calendar.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/regime_calendar.py tests/regime/test_regime_calendar.py
git commit -m "feat(v239): half-day-aware regime session pair and completed-bar cut"
```

