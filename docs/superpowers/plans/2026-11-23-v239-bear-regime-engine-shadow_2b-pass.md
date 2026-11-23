# v239 — Bear-regime engine (shadow): Part 2b — the scan-pass engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V239-8" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v239-bear-regime-engine-shadow-design.md](../specs/2026-11-23-v239-bear-regime-engine-shadow-design.md) — its `## Code reconciliation` section overrides the text above it.
**Index:** [2026-11-23-v239-bear-regime-engine-shadow_0-index.md](2026-11-23-v239-bear-regime-engine-shadow_0-index.md) — Global Constraints, Parallelisation, the task ledger and the eight "Decisions this index fixes" apply here.

Task: V239-8, split out of part 2 only to keep each file under 1500 lines. It needs V239-2/2b (classifier), V239-3 (episodes), V239-4 (calendar), V239-5 (`regime_scan.py`, mode), V239-6/6b (store) and V239-7 (notice).

# Phase 2 — Config, store, notice, pass (continued)

### Task V239-8: Regime pass: compute-or-read `D`, insert once, notice from the winner

**Model:** opus — every wiring decision in one never-raising function: read-or-compute, stale skip, race loser, notice from the winner.

**Files:**
- Modify: `swingbot/core/scanning/regime_scan.py` (V239-5 created it with `MODES` and `regime_mode`; this task writes the whole file, keeping both unchanged)
- Test: `tests/regime/test_regime_pass.py` (suite `market-signals`)

**Interfaces:**
- Consumes:
  - V239-2/2b `bear_regime`: `classify` (a `None` or stale SPY frame gives `UNKNOWN` / `REASON_STALE`; a `None` ^VIX frame gives `stress=None`), `RegimeDay.to_row` / `from_row`, `ROW_COLUMNS`, `STATES`, `SPY`, `VIX`, `REASON_STALE`.
  - V239-3 `regime_episodes`: `episode_key(state, stress) -> str`, `confirmed_transition(prior, new) -> Transition | None`.
  - V239-4 `regime_calendar`: `session_pair(now) -> (s, D)`, `cut_completed(df, now)`, `sessions_between(older, newer) -> int`.
  - V239-6b `market_regime`: `market_regime_repo()`, `.day(d)`, `.recent(limit)` (oldest first), `.insert_once(row, *, notice_event)` -> bool; `COLUMNS`, `STATES`.
  - V239-7 `regime_notices`: `unfilled_bullish_rows(plans, *, new_state)`, `notice_payload(day, transition, *, open_longs, unfilled, gap_sessions, now)`, `notice_event(payload, *, session_date)`.
  - Existing: `get_daily_data(ticker, period)` (`marketdata/data.py`, sets `df.attrs["source"]`); `swallowed(log, tag, exc, msg, *args, exc_info=False)`; `singletons.trade_log.get_trades(status="open", limit=None)`; `PlanStore().open_plans()`.
- Produces (ledger contract, final): `regime_for_pass(*, now: datetime | None = None, repo=None, fetch: Callable[[str], DataFrame] | None = None, plans=None, trades=None) -> RegimeDay | None`. It never raises. It returns `None` under `off` (or an unknown mode) without touching the store or the network, and `None` on any failure (logged as `scan.regime.pass`). V239-10 calls it once per `_sync_run_scan` pass and once per SHORT lane run. `regime_scan.FETCH_PERIOD = "2y"`, `regime_scan.PRIOR_SESSIONS = 60`.

**Behaviour:** index decisions 1, 2, 4, 6 and 8; a race loser returns the winner's row; a notice that cannot be built still stores the day. One test below pins each.

- [ ] **Step 1: Write the failing test**

Create `tests/regime/test_regime_pass.py`:

```python
"""v239 V239-8: the regime pass -- compute-or-read D, insert once, notice from the winner.

The replay fixture (V239-2b) gives real bars: labelled after the 11-18 close,
D = 11-19 is CORRECTION with stress (spec "This week replayed")."""
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.db.repositories import market_regime as mr
from swingbot.core.market import bear_regime as br
from swingbot.core.scanning import regime_scan as rs

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "regime" / "spy_vix_replay.csv"
AFTER_CLOSE = datetime(2026, 11, 18, 22, 0, tzinfo=timezone.utc)   # 17:00 ET Wed
INTRADAY = datetime(2026, 11, 19, 16, 0, tzinfo=timezone.utc)      # 11:00 ET Thu
S, D = date(2026, 11, 18), date(2026, 11, 19)


def _replay():
    raw = pd.read_csv(FIXTURE, parse_dates=["Date"], index_col="Date")
    spy = raw.rename(columns={"spy_high": "High", "spy_close": "Close"})[["High", "Close"]]
    vix = raw[["vix_close"]].rename(columns={"vix_close": "Close"}).dropna()
    return spy, vix


SPY, VIX = _replay()


def _fetcher(spy=SPY, vix=VIX, calls=None, fail=()):
    def fetch(symbol):
        if calls is not None:
            calls.append(symbol)
        if symbol in fail:
            raise ValueError(f"no data for {symbol}")
        df = (spy if symbol == br.SPY else vix).copy()
        df.attrs["source"] = "alpaca" if symbol == br.SPY else "yfinance"
        return df
    return fetch


class _Repo:
    """In-memory MarketRegimeRepository: rows by session, and what it enqueued."""

    def __init__(self, rows=(), winner=None, fail=False):
        self.rows = {row["session_date"]: row for row in rows}
        self.inserted, self.events, self.winner, self.fail = [], [], winner, fail

    def day(self, session_date, *, conn=None):
        if self.fail:
            raise RuntimeError("store down")
        return self.rows.get(session_date)

    def recent(self, limit=60, *, conn=None):
        return [self.rows[key] for key in sorted(self.rows)][-limit:]

    def insert_once(self, row, *, notice_event=None, conn=None):
        if self.winner is not None:            # another process inserted first
            self.rows[row["session_date"]] = self.winner
            return False
        self.rows[row["session_date"]] = row
        self.inserted.append(row)
        self.events.append(notice_event)
        return True


class _Broken:
    def __iter__(self):
        raise RuntimeError("store down")


def _row(day, state, stress=False):
    regime_day = br.RegimeDay(session_date=day, last_bar_date=day - timedelta(days=1),
                              state=state, stress=stress)
    return {**regime_day.to_row(), "computed_at": AFTER_CLOSE}


def _prior(*states, end=S):
    """Stored rows, one per weekday ending at `end`, oldest first."""
    days = pd.bdate_range(end=end, periods=len(states)).date
    return [_row(day, state) for day, state in zip(days, states)]


def _labels_as(monkeypatch, **fields):
    day = br.RegimeDay(session_date=D, last_bar_date=S,
                       **{"state": br.CORRECTION, "stress": False, **fields})
    monkeypatch.setattr(br, "classify", lambda *args, **kwargs: day)
    return day


def _run(repo, now=AFTER_CLOSE, fetch=None, plans=(), trades=()):
    return rs.regime_for_pass(now=now, repo=repo, fetch=fetch or _fetcher(),
                              plans=list(plans), trades=list(trades))


def _tagged(caplog, tag):
    return any(getattr(record, "swallowed_tag", "") == tag for record in caplog.records)


@pytest.fixture(autouse=True)
def _shadow(monkeypatch):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", "shadow")


def test_constants_and_the_db_layer_restates_the_classifier_row():
    assert (rs.FETCH_PERIOD, rs.PRIOR_SESSIONS) == ("2y", 60)
    assert mr.COLUMNS == br.ROW_COLUMNS
    assert mr.STATES == br.STATES


@pytest.mark.parametrize("mode", ["off", "bogus"])
def test_off_touches_neither_the_store_nor_the_network(monkeypatch, mode):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", mode)
    calls, touched = [], []
    monkeypatch.setattr(rs, "market_regime_repo", lambda: touched.append("repo"))
    assert rs.regime_for_pass(now=AFTER_CLOSE, fetch=_fetcher(calls=calls)) is None
    assert calls == [] and touched == []


def test_live_behaves_like_shadow(monkeypatch):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", "live")
    assert _run(_Repo()).state == br.CORRECTION


def test_a_stored_row_is_read_back_without_a_fetch():
    calls, repo = [], _Repo([_row(D, br.BEAR)])
    day = _run(repo, fetch=_fetcher(calls=calls))
    assert (day.session_date, day.state) == (D, br.BEAR)
    assert calls == [] and repo.inserted == []


def test_no_row_computes_d_from_both_feeds_and_stores_it_once():
    calls, repo = [], _Repo()
    day = _run(repo, fetch=_fetcher(calls=calls))
    assert sorted(calls) == ["SPY", "^VIX"]
    assert (day.session_date, day.last_bar_date, day.state, day.stress) == (
        D, S, br.CORRECTION, True)
    assert (day.spy_provider, day.vix_provider) == ("alpaca", "yfinance")
    assert repo.inserted == [{**day.to_row(), "computed_at": AFTER_CLOSE}]
    assert _run(repo, fetch=_fetcher(calls=calls)) == day      # the next pass reads it
    assert len(calls) == 2 and len(repo.inserted) == 1


def test_a_partial_bar_and_later_bars_are_cut_before_classifying():
    day = _run(_Repo(), now=INTRADAY)                 # the frames run to 11-20
    hand = br.classify(SPY.loc[:"2026-11-18"], VIX.loc[:"2026-11-18"], last_session=S,
                       session_date=D, spy_provider="alpaca", vix_provider="yfinance")
    assert day == hand


def test_a_stale_spy_label_is_stamped_but_not_stored_so_the_next_pass_retries():
    repo = _Repo()
    stale = _run(repo, fetch=_fetcher(spy=SPY.loc[:"2026-11-17"]))
    assert (stale.state, stale.unknown_reason) == (br.UNKNOWN, br.REASON_STALE)
    assert repo.inserted == []
    assert _run(repo).state == br.CORRECTION and len(repo.inserted) == 1


def test_a_short_history_unknown_is_stored():
    repo = _Repo()
    day = _run(repo, fetch=_fetcher(spy=SPY.loc[:"2026-11-18"].tail(100)))
    assert (day.state, day.unknown_reason) == (br.UNKNOWN, br.REASON_SHORT)
    assert len(repo.inserted) == 1


def test_a_failed_spy_fetch_is_a_stale_unknown_and_never_raises(caplog):
    repo = _Repo()
    with caplog.at_level(logging.WARNING):
        day = _run(repo, fetch=_fetcher(fail=("SPY",)))
    assert (day.state, day.unknown_reason) == (br.UNKNOWN, br.REASON_STALE)
    assert repo.inserted == [] and _tagged(caplog, "scan.regime.fetch")


def test_a_failed_vix_fetch_stores_a_day_without_stress():
    repo = _Repo()
    day = _run(repo, fetch=_fetcher(fail=("^VIX",)))
    assert (day.state, day.stress, day.vix_provider) == (br.CORRECTION, None, None)
    assert len(repo.inserted) == 1


def test_a_store_failure_returns_none_and_never_raises(caplog):
    with caplog.at_level(logging.WARNING):
        assert _run(_Repo(fail=True)) is None
    assert _tagged(caplog, "scan.regime.pass")


def test_a_lost_race_returns_the_winners_row():
    winner = _row(D, br.BEAR)
    assert _run(_Repo(winner=winner)) == br.RegimeDay.from_row(winner)


def test_a_single_new_session_is_flicker_stored_without_a_notice(monkeypatch):
    _labels_as(monkeypatch)
    repo = _Repo(_prior(br.NORMAL, br.NORMAL, br.NORMAL))
    _run(repo)
    assert len(repo.inserted) == 1 and repo.events == [None]


def test_the_confirming_session_enqueues_one_notice_with_the_book(monkeypatch):
    _labels_as(monkeypatch)
    repo = _Repo(_prior(br.NORMAL, br.NORMAL, br.CORRECTION))
    plans = [SimpleNamespace(ticker="AAPL", status="PENDING", direction="bullish",
                             trigger_price=101.5, entry_context={"bear_regime": "NORMAL"})]
    trades = [{"direction": "bullish"}, {"direction": "bullish"}, {"direction": "bearish"}]
    _run(repo, plans=plans, trades=trades)
    (event,) = repo.events
    payload = event["payload"]
    assert (event["kind"], event["transition_id"]) == ("bear_regime", f"market_regime:{D}")
    assert (payload["kind"], payload["old_label"], payload["new_label"]) == (
        "transition", "Normal", "Correction")
    assert payload["open_longs"] == 2 and payload["gap_sessions"] == 1
    assert payload["unfilled"] == [{"ticker": "AAPL", "entry": 101.5}]


def test_a_pullback_day_notifies_without_a_transition(monkeypatch):
    _labels_as(monkeypatch, pullback_trigger=True)
    repo = _Repo(_prior(br.CORRECTION, br.CORRECTION))
    _run(repo)
    assert repo.events[0]["payload"]["kind"] == "pullback"


def test_a_gap_is_counted_in_nyse_sessions(monkeypatch):
    _labels_as(monkeypatch)
    repo = _Repo(_prior(br.NORMAL, br.NORMAL, br.CORRECTION, end=date(2026, 11, 6)))
    _run(repo)
    assert repo.events[0]["payload"]["gap_sessions"] == 9      # 11-09..11-13, 11-16..11-19


def test_a_notice_that_cannot_be_built_never_costs_the_row(monkeypatch, caplog):
    _labels_as(monkeypatch)
    monkeypatch.setattr(rs.regime_notices, "notice_payload", lambda *a, **k: 1 / 0)
    repo = _Repo(_prior(br.NORMAL, br.NORMAL, br.CORRECTION))
    with caplog.at_level(logging.WARNING):
        _run(repo)
    assert len(repo.inserted) == 1 and repo.events == [None]
    assert _tagged(caplog, "scan.regime.notice")


def test_unreadable_plans_and_trades_read_as_unavailable(monkeypatch):
    _labels_as(monkeypatch)
    repo = _Repo(_prior(br.NORMAL, br.NORMAL, br.CORRECTION))
    rs.regime_for_pass(now=AFTER_CLOSE, repo=repo, fetch=_fetcher(), plans=_Broken(),
                       trades=_Broken())
    payload = repo.events[0]["payload"]
    assert (payload["open_longs"], payload["unfilled"]) == (None, None)
```

- [ ] **Step 2: Run it to see it fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_pass.py`
Expected: FAIL, `AttributeError: module 'swingbot.core.scanning.regime_scan' has no attribute 'regime_for_pass'`.

- [ ] **Step 3: Write the pass**

Replace the whole of `swingbot/core/scanning/regime_scan.py` with:

```python
"""v239: the bear-regime pass -- every wiring decision of the daily trend engine.

Once per scan pass (V239-10): `off` reads nothing; else a stored row for D is
read back, or SPY and ^VIX are fetched here (truthful providers), cut to bars
<= s, classified and inserted once -- the notice only from the winning insert.
A stale-SPY UNKNOWN is stamped but never stored, so the next pass retries.

Spec: docs/superpowers/specs/2026-11-23-v239-bear-regime-engine-shadow-design.md
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

import pandas as pd

from swingbot import config
from swingbot.core.db.repositories.market_regime import market_regime_repo
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import bear_regime as br
from swingbot.core.market import regime_episodes as ep
from swingbot.core.marketdata.data import get_daily_data
from swingbot.core.scanning import regime_calendar, regime_notices

log = logging.getLogger(__name__)

MODES = ("off", "shadow", "live")
FETCH_PERIOD = "2y"
#: Stored sessions read to find the prior confirmed episode (about three months).
PRIOR_SESSIONS = 60


def regime_mode() -> str:
    mode = str(getattr(config, "BEAR_REGIME_MODE", "off") or "off").strip().lower()
    return mode if mode in MODES else "off"


def _fetch(symbol: str) -> pd.DataFrame:
    return get_daily_data(symbol, period=FETCH_PERIOD)


def _frame(fetch: Callable[[str], pd.DataFrame], symbol: str,
           now: datetime) -> tuple[pd.DataFrame | None, str | None]:
    """Completed bars dated <= s and their provider; (None, None) when the fetch fails."""
    try:
        df = fetch(symbol)
    except Exception as exc:
        swallowed(log, "scan.regime.fetch", exc, "regime: %s daily fetch failed: %s",
                  symbol, exc)
        return None, None
    source = (getattr(df, "attrs", None) or {}).get("source")
    return regime_calendar.cut_completed(df, now), source


def _compute_day(now: datetime, fetch: Callable[[str], pd.DataFrame]) -> br.RegimeDay:
    last, target = regime_calendar.session_pair(now)
    spy, spy_source = _frame(fetch, br.SPY, now)
    vix, vix_source = _frame(fetch, br.VIX, now)
    return br.classify(spy, vix, last_session=last, session_date=target,
                       spy_provider=spy_source, vix_provider=vix_source)


def _open_longs(trades) -> int | None:
    try:
        if trades is None:
            from swingbot.core.scanning.singletons import trade_log
            trades = trade_log.get_trades(status="open", limit=None) or []
        return sum(1 for trade in trades if trade.get("direction") == "bullish")
    except Exception as exc:
        swallowed(log, "scan.regime.open_trades", exc, "regime: open trades unreadable: %s", exc)
        return None


def _unfilled(plans, new_state: str) -> list[dict] | None:
    try:
        if plans is None:
            from swingbot.core.planning.plan_store import PlanStore
            plans = PlanStore().open_plans()
        return regime_notices.unfilled_bullish_rows(plans, new_state=new_state)
    except Exception as exc:
        swallowed(log, "scan.regime.open_plans", exc, "regime: open plans unreadable: %s", exc)
        return None


def _transition(day: br.RegimeDay, prior: list[br.RegimeDay]) -> ep.Transition | None:
    keyed = [(p.session_date, ep.episode_key(p.state, p.stress)) for p in prior]
    return ep.confirmed_transition(
        keyed, (day.session_date, ep.episode_key(day.state, day.stress)))


def _notice_for(day: br.RegimeDay, now: datetime, repo, plans, trades) -> dict | None:
    prior = [br.RegimeDay.from_row(row) for row in repo.recent(PRIOR_SESSIONS)]
    transition = _transition(day, prior)
    if transition is None and not day.pullback_trigger:
        return None
    gap = (regime_calendar.sessions_between(prior[-1].session_date, day.session_date)
           if prior else None)
    payload = regime_notices.notice_payload(
        day, transition, open_longs=_open_longs(trades), unfilled=_unfilled(plans, day.state),
        gap_sessions=gap, now=now)
    return regime_notices.notice_event(payload, session_date=day.session_date)


def _safe_notice(day: br.RegimeDay, now: datetime, repo, plans, trades) -> dict | None:
    """A notice that cannot be built never costs the stored day."""
    try:
        return _notice_for(day, now, repo, plans, trades)
    except Exception as exc:
        swallowed(log, "scan.regime.notice", exc,
                  "regime: notice not built; the day is still stored: %s", exc, exc_info=True)
        return None


def _labelled(now: datetime, repo, fetch, plans, trades) -> br.RegimeDay:
    _, target = regime_calendar.session_pair(now)
    stored = repo.day(target)
    if stored is not None:
        return br.RegimeDay.from_row(stored)
    day = _compute_day(now, fetch)
    if day.unknown_reason == br.REASON_STALE:
        return day
    event = _safe_notice(day, now, repo, plans, trades)
    if repo.insert_once({**day.to_row(), "computed_at": now}, notice_event=event):
        return day
    winner = repo.day(target)
    return br.RegimeDay.from_row(winner) if winner is not None else day


def regime_for_pass(*, now: datetime | None = None, repo=None,
                    fetch: Callable[[str], pd.DataFrame] | None = None,
                    plans=None, trades=None) -> br.RegimeDay | None:
    """The day this pass stamps; None under `off` or on any failure."""
    if regime_mode() == "off":
        return None
    try:
        return _labelled(now or datetime.now(timezone.utc), repo or market_regime_repo(),
                         fetch or _fetch, plans, trades)
    except Exception as exc:
        swallowed(log, "scan.regime.pass", exc,
                  "regime pass failed; scanning without a label: %s", exc, exc_info=True)
        return None
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_pass.py`
Expected: `0 failed`. A wrong label for D = 11-19 is a V239-2/2b replay issue (`testrun.py file tests/regime/test_bear_regime_replay.py`), not this pass's.

Run: `python scripts/dev/testrun.py file tests/test_config_v239_keys.py`
Expected: `0 failed` (`MODES` and `regime_mode` unchanged).

Run: `python -m radon cc -s -n C swingbot/core/scanning/regime_scan.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/regime_scan.py tests/regime/test_regime_pass.py
git commit -m "feat(v239): regime pass -- compute or read D, insert once, notice from the winner"
```
