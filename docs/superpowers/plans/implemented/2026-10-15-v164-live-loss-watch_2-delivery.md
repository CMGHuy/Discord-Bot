# v164 Live loss watch, part 2: delivery (loader, latch, Sunday Part 11, instant flag)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task LW3" -A 400 docs/superpowers/plans/2026-10-15-v164-live-loss-watch_2-delivery.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v164-live-loss-watch-design.md`](../specs/2026-10-15-v164-live-loss-watch-design.md) (§ D3, § Testing "Latch" and "Retrospective")
**Index:** [`2026-10-15-v164-live-loss-watch_0-index.md`](2026-10-15-v164-live-loss-watch_0-index.md) — `## Global Constraints`, `## Deviations from the spec text`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`, never `cd`) and the task ledger all apply here and are not repeated.

**Tasks in this part:** LW3, LW4 (chain D3, sequential: LW4 consumes LW3's `load_watch` and latch helpers). Both start only after LW2 is committed on the branch.

**Contract consumed from part 1 (index ledger, LW1/LW2, all in `swingbot/core/analytics/calibration.py`):** `EXPR_WATCH_START`, `WATCH_COUNT_KEYS`, `EXPR_WATCH_LIVE_N_FLOOR`, `EXPR_WATCH_RESAMPLES`, `LIVE_LOSS_MEANING`, `LIVE_LOSS_LOOKS_CAVEAT`, `REGISTRY_CONTEXT_LABEL`, and `live_loss_watch(trades, registry_entries, *, n_resamples=EXPR_WATCH_RESAMPLES) -> {"rows": list[dict], "counts": dict[str, int]}`, rows already in Deviation-5 order, each with exactly the keys `source, strategy, horizon, live_n, live_wr, live_expr, bound_upper, alert, registry_status, registry_window_kind, registry_run_date, registry_expr`. This part reads `horizon` as `str | None` (`None` = pooled row), `live_wr` as a percentage 0–100 or `None` (the `metrics.win_rate` scale), and `live_expr` / `bound_upper` / `registry_expr` as `float | None`.

# Phase D3: delivery

### Task LW3: Loader + latch module; retrospective Part 11 (Sunday digest, always split, clears latches)

**Model:** opus — crosses `tracking`, `analytics`, `db`, `backtesting`; touches a radon-F legacy builder

**Files:**
- Create: `swingbot/core/tracking/live_loss_watch.py`
- Modify: `swingbot/core/tracking/retrospective.py` (import block `:19-33`; new helpers inserted between `_section` `:372-388` and `build_daily_retrospective` `:391`; Part 11 inserted after Part 10 "Scan health alarm" `:~685-699`, immediately before `if failed_sections:`)
- Test: `tests/tracking/test_live_loss_watch.py` (create)
- Test: `tests/tracking/test_retrospective_live_loss.py` (create)

**Interfaces:**
- Consumes (LW1/LW2, `swingbot/core/analytics/calibration.py`): `live_loss_watch(trades, registry_entries, *, n_resamples) -> {"rows", "counts"}`, `EXPR_WATCH_RESAMPLES`, `EXPR_WATCH_START`, `EXPR_WATCH_LIVE_N_FLOOR`, `WATCH_COUNT_KEYS`, `LIVE_LOSS_MEANING`, `LIVE_LOSS_LOOKS_CAVEAT`, `REGISTRY_CONTEXT_LABEL` (row shape: part header above).
- Consumes (existing): `scheduled_repo().fired_on(job) -> str | None` / `.mark(job, date_iso)` (`swingbot/core/db/repositories/scheduled.py:12,16,23`); `ledger.split_by_ledger(trades) -> (main, weak)` (`swingbot/core/tracking/ledger.py:32`, drops non-regular origins from both halves); `TradeLog().get_trades(status="all", limit=None)` (`swingbot/core/tracking/performance.py`); `registry.load_registry()` (`swingbot/core/backtesting/registry.py:87`); `retrospective._emit_table(title, header_line, sep, row_lines, max_body_chars=1500) -> list[str]` (`:229`); `retrospective._section(name, failures)` (`:372`); `retrospective._BERLIN_TZ` (`:33`).
- Produces (module `swingbot/core/tracking/live_loss_watch.py`, consumed by LW4):
  - `LATCH_PREFIX = "live_loss_watch:"`, `LATCH_CLEARED = "cleared"`
  - `latch_job(row: dict) -> str` — `"live_loss_watch:<source>/<strategy>/<horizon or 'pooled'>"`
  - `is_latched(row: dict) -> bool` — `fired_on(job) not in (None, "cleared")`
  - `mark_latched(row: dict, today: dt.date) -> None` — `mark(job, today.isoformat())`
  - `clear_latches(rows: list[dict]) -> list[str]` — marks `"cleared"` on every row that is latched and has `bound_upper is not None and bound_upper >= 0`; returns the cleared job names in row order
  - `load_watch(*, n_resamples: int = calibration.EXPR_WATCH_RESAMPLES) -> dict` — `calibration.live_loss_watch([*main, *weak], load_registry(), n_resamples=...)` over closed (`win`/`loss`/`closed`) trades split by `split_by_ledger`, exactly the population `snapshots.refresh_snapshot` hands to the snapshot (LW5)
  - seams `_all_trades() -> list[dict]`, `_registry_entries() -> list[dict]` (tests monkeypatch them)
- Produces (`retrospective.py`): `_live_loss_watch_part(today: dt.date) -> list[str]` (`[]` unless Sunday); `_format_live_loss_watch(watch: dict) -> list[str]` (table chunks from `_emit_table`, then one notes message); seam `_berlin_today() -> dt.date`.

**Design notes (binding for this task):**
- `retrospective.py` imports the module as `from swingbot.core.tracking import live_loss_watch as loss_watch` (alias, because `calibration.live_loss_watch` is a function of the same name) and calls `loss_watch.load_watch()` / `loss_watch.clear_latches(...)` through the module attribute, so tests patch `swingbot.core.tracking.live_loss_watch.load_watch` directly.
- `build_daily_retrospective` (radon F 106) gains exactly one `with _section("live loss watch", failed_sections):` and one `messages.extend(_live_loss_watch_part(today))`. The Sunday check and the latch clearing live inside the helper. The builder's own `now_berlin` / `is_today` lines are not touched; the helper reads the real date through the new `_berlin_today()` seam.
- Clearing runs only when `today == _berlin_today()` (Deviation 4): a backdated Sunday `!recap <date>` still shows Part 11 but never re-arms a flag. A bare `!recap` on a Sunday is a digest for the real Berlin today and does clear (Global Constraints, Latch).
- A latched row with `bound_upper is None` stays latched: "no bound" is not evidence the loss has recovered.
- The formatter never reorders rows: LW2 already returns alert rows first, then confluence rows in `HORIZONS` order with pooled last, then strategy rows by name.
- Part 11 always splits itself: 22 rows at ~79 characters per line exceed `_emit_table`'s 1500-character body, so the table arrives as `(part 1/2)`, `(part 2/2)`, each a complete fenced block under Discord's 2000-character limit.

- [ ] **Step 0: Confirm the part-1 contract is on the branch**

Run: `git -C $WT grep -n -E "def live_loss_watch|^WATCH_COUNT_KEYS|^EXPR_WATCH_(START|LIVE_N_FLOOR|RESAMPLES)|^LIVE_LOSS_(MEANING|LOOKS_CAVEAT)|^REGISTRY_CONTEXT_LABEL" swingbot/core/analytics/calibration.py`
Expected: 8 lines (one per symbol). Fewer means LW2 is not committed yet: stop and report, do not stub them.

- [ ] **Step 1: Write the failing loader/latch tests**

Create `tests/tracking/test_live_loss_watch.py`:

```python
"""v164 D3: the live loss watch's both-ledger loader and its scheduled_jobs latch.

The latch tests use the real scheduled_repo(): the autouse _store_database
fixture (tests/conftest.py) gives each test a truncated Postgres database.
"""
import datetime as dt

from swingbot.core.analytics import calibration
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.tracking import live_loss_watch as lw

FLAG_DAY = dt.date(2026, 10, 20)


def _row(horizon="4w", *, bound=-0.2, alert=True, source="confluence", strategy="ALL"):
    return {"source": source, "strategy": strategy, "horizon": horizon, "live_n": 25,
            "live_wr": 40.0, "live_expr": -0.3, "bound_upper": bound, "alert": alert,
            "registry_status": "WEAK", "registry_window_kind": "TRAIN",
            "registry_run_date": "2026-09-01", "registry_expr": -0.05}


def _trade(status, *, ledger="main", origin=None):
    trade = {"status": status, "ledger": ledger, "source": "confluence", "strategy": "MACD",
             "horizon_key": "4w", "opened_at": "2026-10-19T14:00:00+00:00",
             "closed_at": "2026-10-23T14:00:00+00:00", "direction": "bullish",
             "entry": 100.0, "stop_loss": 95.0, "exit_price": 96.0, "legs": []}
    if origin is not None:
        trade["origin"] = origin
    return trade


def _reg(horizon):
    return {"source": "confluence", "strategy": "ALL", "horizon": horizon, "status": "WEAK",
            "n": 300, "win_rate": 45.0, "expectancy_r": -0.05,
            "window": "2020-01-01..2023-12-31", "run_date": "2026-09-01"}


def test_latch_job_names_exact_and_pooled_rows():
    assert lw.latch_job(_row("4w")) == "live_loss_watch:confluence/ALL/4w"
    assert lw.latch_job(_row(None)) == "live_loss_watch:confluence/ALL/pooled"
    assert (lw.latch_job(_row(None, source="strategy", strategy="MACD"))
            == "live_loss_watch:strategy/MACD/pooled")


def test_latch_marks_reads_and_clears():
    row = _row()
    assert lw.is_latched(row) is False
    lw.mark_latched(row, FLAG_DAY)
    assert scheduled_repo().fired_on(lw.latch_job(row)) == "2026-10-20"
    assert lw.is_latched(row) is True

    recovered = _row(bound=0.0, alert=False)          # boundary: 0 counts as recovered
    assert lw.clear_latches([recovered]) == [lw.latch_job(row)]
    assert scheduled_repo().fired_on(lw.latch_job(row)) == lw.LATCH_CLEARED == "cleared"
    assert lw.is_latched(row) is False


def test_clear_latches_keeps_rows_still_below_zero_or_without_a_bound():
    below, unbounded = _row("2w", bound=-0.01), _row("3m", bound=None, alert=False)
    for row in (below, unbounded):
        lw.mark_latched(row, FLAG_DAY)
    assert lw.clear_latches([below, unbounded]) == []
    assert lw.is_latched(below) and lw.is_latched(unbounded)


def test_clear_latches_never_writes_an_unlatched_row():
    row = _row("5m", bound=0.4, alert=False)
    assert lw.clear_latches([row]) == []
    assert scheduled_repo().fired_on(lw.latch_job(row)) is None


def test_latch_namespace_leaves_the_daily_recap_job_alone():
    scheduled_repo().mark("daily_recap", "2026-10-20")
    lw.mark_latched(_row(), dt.date(2026, 10, 21))
    lw.clear_latches([_row(bound=0.5, alert=False)])
    assert scheduled_repo().fired_on("daily_recap") == "2026-10-20"


def test_load_watch_feeds_closed_trades_of_both_ledgers_only(monkeypatch):
    trades = [_trade("loss"), _trade("win", ledger="weak"), _trade("closed"),
              _trade("open"), _trade("loss", origin="next_session")]
    registry = [_reg("4w"), _reg(None)]
    seen = {}

    def fake_rule(trades_in, registry_in, *, n_resamples):
        seen.update(trades=trades_in, registry=registry_in, n=n_resamples)
        return {"rows": [], "counts": {}}

    monkeypatch.setattr(lw, "_all_trades", lambda: trades)
    monkeypatch.setattr(lw, "_registry_entries", lambda: registry)
    monkeypatch.setattr(lw.calibration, "live_loss_watch", fake_rule)

    assert lw.load_watch(n_resamples=300) == {"rows": [], "counts": {}}
    # main ledger first (loss, closed), then weak (win); open and outlook trades dropped
    assert [t["status"] for t in seen["trades"]] == ["loss", "closed", "win"]
    assert {t["ledger"] for t in seen["trades"]} == {"main", "weak"}
    assert seen["registry"] is registry
    assert seen["n"] == 300


def test_load_watch_default_resamples_is_the_pre_registered_constant(monkeypatch):
    seen = {}
    monkeypatch.setattr(lw, "_all_trades", lambda: [])
    monkeypatch.setattr(lw, "_registry_entries", lambda: [])
    def fake_rule(trades_in, registry_in, *, n_resamples):
        seen["n"] = n_resamples
        return {"rows": [], "counts": {}}

    monkeypatch.setattr(lw.calibration, "live_loss_watch", fake_rule)
    lw.load_watch()
    assert seen["n"] == calibration.EXPR_WATCH_RESAMPLES == 10_000


def test_load_watch_runs_the_real_rule_over_both_ledgers(monkeypatch):
    trades = [_trade("loss") for _ in range(3)] + [_trade("win", ledger="weak")]
    monkeypatch.setattr(lw, "_all_trades", lambda: trades)
    monkeypatch.setattr(lw, "_registry_entries", lambda: [_reg("4w"), _reg(None)])

    watch = lw.load_watch(n_resamples=200)

    rows = {row["horizon"]: row for row in watch["rows"]}
    assert rows["4w"]["live_n"] == 4          # main + weak ledger
    assert rows[None]["live_n"] == 4          # and the pooled row
    assert set(watch["counts"]) <= set(calibration.WATCH_COUNT_KEYS)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/tracking/test_live_loss_watch.py`
Expected: FAIL at collection with `ImportError: cannot import name 'live_loss_watch' from 'swingbot.core.tracking'`.

- [ ] **Step 3: Implement the loader and latch module**

Create `swingbot/core/tracking/live_loss_watch.py`:

```python
"""v164 D3: the live loss watch's population loader and its latch.

Shared by retrospective Part 11 (the Sunday digest, which clears latches) and
loops.daily_recap (the instant ops-channel flag, which marks them), so neither
of those modules imports the other.

Population: closed trades (win / loss / manual close) of BOTH ledgers, split
exactly as snapshots.refresh_snapshot splits them, so the digest, the flag and
the admin Edge tab judge the same trades. calibration.live_loss_watch applies
the regular-origin and start-date rules on top.

Latch: one scheduled_jobs row per registry row, job
``live_loss_watch:<source>/<strategy>/<horizon or "pooled">``; ``fired_on``
holds the Berlin date the row was flagged, or the literal ``"cleared"``
(sa.Text, no migration). Report-only: nothing here writes the registry, a
badge or a plan.
"""
from __future__ import annotations

import datetime as dt
import logging

from swingbot.core.analytics import calibration
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.tracking.ledger import split_by_ledger

log = logging.getLogger(__name__)

LATCH_PREFIX = "live_loss_watch:"
LATCH_CLEARED = "cleared"
_CLOSED_STATUSES = ("win", "loss", "closed")


def latch_job(row: dict) -> str:
    """The scheduled_jobs key of one registry row's latch."""
    horizon = row.get("horizon") or "pooled"
    return f"{LATCH_PREFIX}{row['source']}/{row['strategy']}/{horizon}"


def is_latched(row: dict) -> bool:
    """True while a flag for this row is open (posted and not yet cleared)."""
    return scheduled_repo().fired_on(latch_job(row)) not in (None, LATCH_CLEARED)


def mark_latched(row: dict, today: dt.date) -> None:
    """Open the latch. Call only after the flag's send returned a message."""
    scheduled_repo().mark(latch_job(row), today.isoformat())


def _recovered(row: dict) -> bool:
    bound = row.get("bound_upper")
    return bound is not None and bound >= 0


def clear_latches(rows: list[dict]) -> list[str]:
    """Re-arm every latched row whose upper bound is back at or above zero.

    Called only by the Sunday digest built for the real Berlin today. A row
    with no bound stays latched: no bound is not evidence of recovery."""
    cleared = []
    for row in rows:
        if _recovered(row) and is_latched(row):
            job = latch_job(row)
            scheduled_repo().mark(job, LATCH_CLEARED)
            cleared.append(job)
    if cleared:
        log.info("live loss watch: cleared latches %s", ", ".join(cleared))
    return cleared


def _all_trades() -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status="all", limit=None)


def _registry_entries() -> list[dict]:
    from swingbot.core.backtesting import registry
    return registry.load_registry()


def load_watch(*, n_resamples: int = calibration.EXPR_WATCH_RESAMPLES) -> dict:
    """The live loss watch over both ledgers: ``{"rows": [...], "counts": {...}}``."""
    closed = [trade for trade in _all_trades() if trade.get("status") in _CLOSED_STATUSES]
    main, weak = split_by_ledger(closed)
    return calibration.live_loss_watch([*main, *weak], _registry_entries(), n_resamples=n_resamples)
```

- [ ] **Step 4: Run the loader/latch tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/tracking/test_live_loss_watch.py`
Expected: PASS, `8 passed`, `0 failed`. (A skip that names the db-test start command means Postgres is down: start it and re-run; a skip is not green.)

- [ ] **Step 5: Write the failing Part 11 tests**

Create `tests/tracking/test_retrospective_live_loss.py`:

```python
"""v164 D3: retrospective Part 11 -- the Sunday live loss watch digest."""
import datetime as dt

from swingbot.core.analytics import calibration
from swingbot.core.tracking import live_loss_watch as lw
from swingbot.core.tracking import retrospective as retro

SUNDAY = dt.date(2026, 10, 18)
MONDAY = dt.date(2026, 10, 19)
LATER = dt.date(2026, 10, 21)          # the real date for a backdated !recap
_HORIZONS = ("4w", "2w", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m", None)
_STRATEGIES = ("Bollinger Bands", "Candlestick Pattern", "Fibonacci", "Ichimoku", "MACD",
               "Moving Average", "Pivot Points", "RSI", "Stochastic", "Trendline",
               "Volume Profile")


def _row(source, strategy, horizon, *, alert=False, bound=0.1):
    return {"source": source, "strategy": strategy, "horizon": horizon, "live_n": 24,
            "live_wr": 41.7, "live_expr": -0.12, "bound_upper": bound, "alert": alert,
            "registry_status": "WEAK", "registry_window_kind": "TRAIN",
            "registry_run_date": "2026-09-01", "registry_expr": -0.04}


def _watch():
    """22 rows in LW2's order: the one alert row (confluence 4w) first."""
    rows = [_row("confluence", "ALL", "4w", alert=True, bound=-0.05)]
    rows += [_row("confluence", "ALL", h) for h in _HORIZONS[1:]]
    rows += [_row("strategy", name, None) for name in _STRATEGIES]
    counts = {key: index + 1 for index, key in enumerate(calibration.WATCH_COUNT_KEYS)}
    return {"rows": rows, "counts": counts}


def _isolate(monkeypatch, tmp_path, watch, *, real_today=SUNDAY):
    monkeypatch.setattr(retro, "_HISTORY_PATH", str(tmp_path / "history.json"))
    calls = []

    def load(**kwargs):
        calls.append(kwargs)
        return watch

    monkeypatch.setattr(lw, "load_watch", load)
    monkeypatch.setattr(retro, "_berlin_today", lambda: real_today)
    return calls


def _part11(messages):
    return [message for message in messages if "Live loss watch" in message]


def test_part_11_posts_on_sunday_only(tmp_path, monkeypatch):
    calls = _isolate(monkeypatch, tmp_path, _watch(), real_today=MONDAY)
    assert _part11(retro.build_daily_retrospective([], today=MONDAY)) == []
    assert calls == []                              # no bootstrap on a weekday

    calls = _isolate(monkeypatch, tmp_path, _watch())
    assert len(_part11(retro.build_daily_retrospective([], today=SUNDAY))) >= 3
    assert len(calls) == 1


def test_part_11_always_splits_into_fenced_chunks_under_the_discord_limit():
    messages = retro._format_live_loss_watch(_watch())
    tables = [message for message in messages if "```" in message]
    assert len(tables) >= 2
    assert "(part 1/" in tables[0]
    assert all(len(message) < 2000 for message in messages)
    assert all(table.count("```") == 2 for table in tables)
    body = "\n".join(tables)
    for name in _STRATEGIES:
        assert name in body
    assert "confluence pooled" in body


def test_rows_keep_the_rule_order_and_the_alert_row_is_marked():
    messages = retro._format_live_loss_watch(_watch())
    first_table_lines = messages[0].splitlines()
    first_row = first_table_lines[4]                # title, ```, header, separator, row 1
    assert first_row.startswith("confluence 4w")
    assert "LOSS" in first_row
    tables = [message for message in messages if "```" in message]
    assert sum("LOSS" in line for table in tables for line in table.splitlines()) == 1
    assert "1 of 22 row(s) flagged" in messages[0]


def test_notes_state_meaning_label_population_counts_and_caveat():
    watch = _watch()
    notes = retro._format_live_loss_watch(watch)[-1]
    assert calibration.LIVE_LOSS_MEANING in notes
    assert calibration.REGISTRY_CONTEXT_LABEL in notes
    assert calibration.LIVE_LOSS_LOOKS_CAVEAT in notes
    assert calibration.EXPR_WATCH_START.isoformat() in notes
    for key in calibration.WATCH_COUNT_KEYS:
        assert f"{key} {watch['counts'][key]}" in notes


def test_empty_watch_still_posts_the_notes():
    messages = retro._format_live_loss_watch(
        {"rows": [], "counts": {key: 0 for key in calibration.WATCH_COUNT_KEYS}})
    assert len(messages) == 1
    assert "0 of 0 row(s) flagged" in messages[0]


def test_a_raising_loader_lands_in_failed_sections(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path, _watch())

    def boom(**kwargs):
        raise RuntimeError("bootstrap exploded")

    monkeypatch.setattr(lw, "load_watch", boom)
    messages = retro.build_daily_retrospective([], today=SUNDAY)
    assert _part11(messages) == []
    assert "live loss watch" in messages[-1]
    assert "failed to build" in messages[-1]


def test_sunday_digest_for_the_real_today_clears_recovered_latches(tmp_path, monkeypatch):
    watch = _watch()
    alert_row, recovered_row = watch["rows"][0], watch["rows"][1]
    for row in (alert_row, recovered_row):
        lw.mark_latched(row, dt.date(2026, 10, 14))
    _isolate(monkeypatch, tmp_path, watch, real_today=SUNDAY)

    retro.build_daily_retrospective([], today=SUNDAY)

    assert lw.is_latched(alert_row) is True          # still below zero
    assert lw.is_latched(recovered_row) is False     # bound back at >= 0


def test_backdated_sunday_digest_reports_but_never_clears(tmp_path, monkeypatch):
    watch = _watch()
    recovered_row = watch["rows"][1]
    lw.mark_latched(recovered_row, dt.date(2026, 10, 14))
    _isolate(monkeypatch, tmp_path, watch, real_today=LATER)

    messages = retro.build_daily_retrospective([], today=SUNDAY)

    assert _part11(messages)                          # Deviation 4: still shown
    assert lw.is_latched(recovered_row) is True
```

- [ ] **Step 6: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/tracking/test_retrospective_live_loss.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.tracking.retrospective' has no attribute '_berlin_today'` (and `_format_live_loss_watch`).

- [ ] **Step 7: Add the import to `retrospective.py`**

In the import block (`:28-33`), after `from swingbot.core.analytics.journal import JournalStore`, add:

```python
from swingbot.core.tracking import live_loss_watch as loss_watch
```

(No cycle: `live_loss_watch` imports `calibration`, `scheduled`, `ledger` at module top and `performance`/`registry` lazily; none of them imports `retrospective`.)

- [ ] **Step 8: Add the Part 11 helpers**

Insert this block between the end of `_section` (`:388`) and `def build_daily_retrospective` (`:391`):

```python
# ---------------------------------------------------------------------------
# Part 11: live loss watch (v164 D3) -- the Sunday digest
# ---------------------------------------------------------------------------

def _berlin_today() -> dt.date:
    """The real Berlin date. A seam so tests can backdate the digest."""
    return dt.datetime.now(_BERLIN_TZ).date()


def _llw_opt(value, spec: str) -> str:
    return "—" if value is None else format(value, spec)


def _llw_label(row: dict) -> str:
    if row.get("source") == "confluence":
        return f"confluence {row.get('horizon') or 'pooled'}"
    return str(row.get("strategy") or "?")


#: (header, width, cell) per column -- the digest table is table-driven.
#: Reg / Window / RegExpR are registry context, labelled as not comparable.
_LLW_COLUMNS = (
    ("Row", 20, _llw_label),
    ("N", 4, lambda row: str(row.get("live_n", 0))),
    ("WR%", 4, lambda row: _llw_opt(row.get("live_wr"), ".0f")),
    ("ExpR", 6, lambda row: _llw_opt(row.get("live_expr"), "+.2f")),
    ("Up90", 6, lambda row: _llw_opt(row.get("bound_upper"), "+.2f")),
    ("Flag", 4, lambda row: "LOSS" if row.get("alert") else ""),
    ("Reg", 9, lambda row: str(row.get("registry_status") or "—")),
    ("Window", 10, lambda row: str(row.get("registry_window_kind") or "—")),
    ("RegExpR", 7, lambda row: _llw_opt(row.get("registry_expr"), "+.2f")),
)


def _llw_line(cells: list[str]) -> str:
    widths = [width for _, width, _ in _LLW_COLUMNS]
    return " ".join(f"{cell[:width]:<{width}}" for cell, width in zip(cells, widths)).rstrip()


def _llw_row_line(row: dict) -> str:
    return _llw_line([cell(row) for _, _, cell in _LLW_COLUMNS])


def _llw_notes(watch: dict, flagged: int, total: int) -> str:
    counts = watch.get("counts") or {}
    counted = " · ".join(f"{key} {counts.get(key, 0)}" for key in calibration.WATCH_COUNT_KEYS)
    return "\n".join([
        f"**📉 Live loss watch — {flagged} of {total} row(s) flagged · notes**",
        f"• A LOSS flag means: {calibration.LIVE_LOSS_MEANING}.",
        f"• Up90 = 90th percentile of the week-clustered bootstrap of mean R; a row flags at "
        f"N >= {calibration.EXPR_WATCH_LIVE_N_FLOOR} with Up90 < 0.",
        f"• Reg / Window / RegExpR: {calibration.REGISTRY_CONTEXT_LABEL}.",
        f"• Population: closed trades (win, loss, manual close) of both ledgers, opened on or "
        f"after {calibration.EXPR_WATCH_START.isoformat()} (Berlin).",
        f"• Counted: {counted} (manual closes are in the rows; the others are excluded).",
        f"• {calibration.LIVE_LOSS_LOOKS_CAVEAT}.",
    ])


def _format_live_loss_watch(watch: dict) -> list[str]:
    """Part 11 as messages: the row table (always self-split by _emit_table
    into fenced chunks under Discord's limit), then one notes message."""
    rows = watch.get("rows") or []
    flagged = sum(1 for row in rows if row.get("alert"))
    title = f"📉 Live loss watch — {flagged} of {len(rows)} row(s) flagged"
    header = _llw_line([name for name, _, _ in _LLW_COLUMNS])
    table = _emit_table(title, header, "-" * len(header), [_llw_row_line(row) for row in rows])
    return [*table, _llw_notes(watch, flagged, len(rows))]


def _live_loss_watch_part(today: dt.date) -> list[str]:
    """Part 11 (v164 D3), Sundays only. Loads both ledgers itself: the
    retrospective's own input is the main ledger only (recap.py:51). Clears
    recovered latches only for the real Berlin today, so a backdated
    !recap <date> reports but never re-arms a flag."""
    if today.weekday() != 6:
        return []
    watch = loss_watch.load_watch()
    if today == _berlin_today():
        loss_watch.clear_latches(watch.get("rows") or [])
    return _format_live_loss_watch(watch)
```

- [ ] **Step 9: Wire Part 11 into the builder**

In `build_daily_retrospective`, immediately after the Part 10 `with _section("scan health", failed_sections):` block ends (after its `failed_sections.append("scan health")` line) and before `if failed_sections:`, insert:

```python
    # ── Part 11: Live loss watch (Sundays only, v164) ──────────────────────
    with _section("live loss watch", failed_sections):
        messages.extend(_live_loss_watch_part(today))
```

Nothing else in the builder changes.

- [ ] **Step 10: Run both test files to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/tracking/test_retrospective_live_loss.py`
Expected: PASS, `8 passed`, `0 failed`.

Run: `python $WT/scripts/dev/testrun.py file tests/tracking/test_live_loss_watch.py`
Expected: PASS, `8 passed`.

Run: `python $WT/scripts/dev/testrun.py file tests/tracking/test_retrospective_v2.py`
Expected: PASS, `0 failed` (existing retrospective behaviour unchanged).

- [ ] **Step 11: Complexity gate**

Run: `python -m radon cc -s -n C $WT/swingbot/core/tracking/live_loss_watch.py $WT/swingbot/core/tracking/retrospective.py`
Expected: exactly the three pre-existing legacy lines for `retrospective.py` and nothing from `live_loss_watch.py`: `build_daily_retrospective - F (106)` (the added `with` and call add no branch; any higher number means a branch was added to the builder — move it into the helper), `_analyse - F (72)`, `_collect_weekly_risk_stats - D (21)`. No new function appears.

- [ ] **Step 12: Commit**

```bash
git -C $WT add swingbot/core/tracking/live_loss_watch.py swingbot/core/tracking/retrospective.py tests/tracking/test_live_loss_watch.py tests/tracking/test_retrospective_live_loss.py
git -C $WT commit -m "feat(v164): live loss watch loader + latch; Sunday retrospective Part 11 (LW3)"
git -C $R status --short
```

Expected: the commit lands on branch `2026-10-15-v164-live-loss-watch`; `git -C $R status --short` shows no file of this plan (other sessions' v162 files may be listed: leave them alone).

### Task LW4: Instant latched ops-channel flag from `daily_recap`

**Model:** sonnet — one command module plus an embed builder, latch contract given

**Files:**
- Modify: `swingbot/commands/scanning/notices.py` (new builder after `config_notice_embed`, `:~80`)
- Modify: `swingbot/commands/scanning/loops.py` (import block `:1-23`; new helpers after `_mark_scheduled_job_fired` `:699-701`; one call in `daily_recap` `:705-742`, after the `recap._post_retrospective()` try/except)
- Test: `tests/commands/test_live_loss_flag.py` (create)

**Interfaces:**
- Consumes (LW3, `swingbot/core/tracking/live_loss_watch.py`): `load_watch(*, n_resamples=...) -> {"rows": [...], "counts": {...}}`, `is_latched(row) -> bool`, `mark_latched(row, today: dt.date) -> None`, `clear_latches(rows) -> list[str]` (tests only), `latch_job(row) -> str` (tests only).
- Consumes (LW2, `calibration.py`): `LIVE_LOSS_MEANING`, `REGISTRY_CONTEXT_LABEL`; row keys as in the part header.
- Consumes (existing): `loops._ops_channel()` (`loops.py:51`, `None` when no channel configured); `notices.send_guarded(channel, embed, *, what) -> message | None` (`notices.py:~36`, swallows send failures); `notices.system_embed(kind, detail, description)`; `Kind.RETROSPECTIVE` (`swingbot/core/presentation/kinds.py:142`).
- Produces: `notices.live_loss_flag_embed(row: dict)` — a SYSTEM `RETROSPECTIVE` embed, detail `live loss watch` (title `📜 RETROSPECTIVE · live loss watch`), body naming the row and carrying the meaning text and the registry-context label (Deviation 3); `loops._post_live_loss_flags(today: dt.date) -> int` — number of flags sent, never raises.

**Design notes (binding for this task):**
- **Only `daily_recap` calls the flag**, right after `recap._post_retrospective()`, with its own Berlin `today` (`SESSION_TZ` is `BERLIN_TZ`, `bot_core.py:31`). `!recap` (always a channel override) and a backdated recap never reach it, and `recap.py` gains no import of `loops`. On a Sunday the retrospective's Part 11 has already cleared recovered latches by the time the flag runs.
- The call is a bare `await _post_live_loss_flags(today)`: the function guards itself (a raise inside a `tasks.loop` body would stop the loop), so `daily_recap` gains no branch (radon stays B 7).
- `load_watch` (22 rows × 10 000 bootstrap draws plus a DB read) runs through `asyncio.to_thread`, like the other blocking calls in `loops.py`.
- Latch order per row: send first; **mark only when `send_guarded` returned a message** (it returns `None` on a swallowed failure), so a failed send retries on the next scheduled recap. A missing ops channel posts nothing and latches nothing.
- One post per alerting row per episode. A row with `alert` false is never posted, latched or unlatched here; clearing belongs to the Sunday digest alone (LW3).

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_live_loss_flag.py`:

```python
"""v164 D3: the instant, latched ops-channel flag of the live loss watch.

Latches use the real scheduled_repo() (autouse _store_database fixture,
tests/conftest.py); the watch itself is faked so no bootstrap runs here.
"""
import asyncio
import datetime as dt
import types

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import loops as loops_mod
from swingbot.commands.scanning import notices, recap
from swingbot.core.analytics import calibration
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.tracking import live_loss_watch as lw

DAY = dt.date(2026, 10, 20)          # a Tuesday


class _Chan:
    def __init__(self, *, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord down")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=len(self.sent))     # a discord.Message stand-in


def _row(horizon="4w", *, alert=True, bound=-0.08):
    return {"source": "confluence", "strategy": "ALL", "horizon": horizon, "live_n": 31,
            "live_wr": 38.7, "live_expr": -0.27, "bound_upper": bound, "alert": alert,
            "registry_status": "WEAK", "registry_window_kind": "TRAIN",
            "registry_run_date": "2026-09-01", "registry_expr": -0.03}


def _wire(monkeypatch, rows, chan):
    monkeypatch.setattr(lw, "load_watch", lambda **kwargs: {"rows": rows, "counts": {}})
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: chan)


def _flag(day=DAY):
    return asyncio.run(loops_mod._post_live_loss_flags(day))


def test_flag_embed_names_the_row_and_states_the_meaning():
    embed = notices.live_loss_flag_embed(_row())
    assert embed.title == "📜 RETROSPECTIVE · live loss watch"
    assert "confluence / ALL / 4w" in embed.description
    assert calibration.LIVE_LOSS_MEANING in embed.description
    assert calibration.REGISTRY_CONTEXT_LABEL in embed.description
    assert "-0.08R" in embed.description and "-0.27R" in embed.description
    pooled = notices.live_loss_flag_embed(_row(None))
    assert "confluence / ALL / pooled" in pooled.description


def test_flag_embed_tolerates_missing_figures():
    row = dict(_row(), live_wr=None, registry_expr=None, registry_window_kind=None,
               registry_status=None, registry_run_date=None)
    assert "—" in notices.live_loss_flag_embed(row).description


def test_posts_once_per_alert_row_and_latches_it(monkeypatch):
    rows = [_row("4w"), _row("2w", alert=False, bound=0.1), _row(None, bound=-0.02)]
    chan = _Chan()
    _wire(monkeypatch, rows, chan)

    assert _flag() == 2
    assert len(chan.sent) == 2
    assert lw.is_latched(rows[0]) and lw.is_latched(rows[2])
    assert not lw.is_latched(rows[1])
    assert scheduled_repo().fired_on(lw.latch_job(rows[0])) == "2026-10-20"


def test_rerun_the_same_day_is_silent(monkeypatch):
    chan = _Chan()
    _wire(monkeypatch, [_row()], chan)
    assert _flag() == 1
    assert _flag() == 0
    assert len(chan.sent) == 1


def test_silent_while_latched_on_later_days(monkeypatch):
    chan = _Chan()
    _wire(monkeypatch, [_row()], chan)
    _flag()
    assert _flag(DAY + dt.timedelta(days=1)) == 0
    assert _flag(DAY + dt.timedelta(days=6)) == 0
    assert len(chan.sent) == 1


def test_re_arms_only_after_a_sunday_clear(monkeypatch):
    chan = _Chan()
    row = _row()
    _wire(monkeypatch, [row], chan)
    _flag()
    lw.clear_latches([dict(row, bound_upper=0.05, alert=False)])   # what Part 11 does
    assert _flag(DAY + dt.timedelta(days=7)) == 1
    assert len(chan.sent) == 2
    assert scheduled_repo().fired_on(lw.latch_job(row)) == "2026-10-27"


def test_a_failed_send_does_not_latch_and_retries_next_time(monkeypatch):
    row = _row()
    _wire(monkeypatch, [row], _Chan(fail=True))
    assert _flag() == 0
    assert not lw.is_latched(row)

    chan = _Chan()
    _wire(monkeypatch, [row], chan)
    assert _flag(DAY + dt.timedelta(days=1)) == 1
    assert lw.is_latched(row)


def test_no_ops_channel_posts_and_latches_nothing(monkeypatch):
    row = _row()
    _wire(monkeypatch, [row], None)
    assert _flag() == 0
    assert not lw.is_latched(row)


def test_a_raising_watch_never_escapes(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("bootstrap exploded")

    monkeypatch.setattr(lw, "load_watch", boom)
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: _Chan())
    assert _flag() == 0


def _fixed_now(monkeypatch, now):
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)

        @classmethod
        def utcnow(cls):
            return now

    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)


def test_daily_recap_flags_after_the_retrospective_even_when_it_fails(monkeypatch):
    order = []

    async def post():
        order.append("retro")
        raise RuntimeError("retrospective exploded")

    async def flags(today):
        order.append(("flags", today))
        return 0

    async def prune():
        return None

    _fixed_now(monkeypatch, dt.datetime(2026, 10, 20, 23, 15))
    monkeypatch.setattr(config, "SESSION_END_HOUR", 23)
    monkeypatch.setattr(loops_mod.recap, "_post_retrospective", post)
    monkeypatch.setattr(loops_mod, "_post_live_loss_flags", flags)
    monkeypatch.setattr(loops_mod, "_prune_alert_posts", prune)
    monkeypatch.setattr(loops_mod, "_recap_fired_date", None)

    asyncio.run(scanning_mod.daily_recap.coro())

    assert order == ["retro", ("flags", DAY)]


def test_recap_command_path_never_flags(monkeypatch):
    """!recap / !recap <date> go through recap._post_retrospective with a
    channel override; only the scheduled daily_recap posts flags."""
    from swingbot.core.tracking import retrospective

    calls = []

    async def flags(today):
        calls.append(today)
        return 0

    async def resolve(*args, **kwargs):
        return _Chan()

    monkeypatch.setattr(loops_mod, "_post_live_loss_flags", flags)
    monkeypatch.setattr(retrospective, "build_daily_retrospective",
                        lambda trades, today=None: ["recap body"])
    monkeypatch.setattr(recap, "trade_log", types.SimpleNamespace(get_trades=lambda **kw: []))
    monkeypatch.setattr(recap, "_resolve_retrospective_channel", resolve)

    asyncio.run(recap._post_retrospective(channel_id_override=1, today=dt.date(2026, 10, 18)))
    asyncio.run(recap._post_retrospective(channel_id_override=1))

    assert calls == []
    assert not hasattr(recap, "loops")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_live_loss_flag.py`
Expected: FAIL — `AttributeError: module 'swingbot.commands.scanning.notices' has no attribute 'live_loss_flag_embed'` and `module 'swingbot.commands.scanning.loops' has no attribute '_post_live_loss_flags'` (the `test_recap_command_path_never_flags` monkeypatch fails the same way until Step 4).

- [ ] **Step 3: Add the flag embed to `notices.py`**

Add to the import block of `swingbot/commands/scanning/notices.py` (after `from swingbot.core.presentation.kinds import Kind`):

```python
from swingbot.core.analytics import calibration
```

(`notices.py` stays pure: `calibration` has no bot or discord import, and does not import `commands`.)

Insert after `config_notice_embed` (`:~80`):

```python
def _r_text(value) -> str:
    return "—" if value is None else f"{value:+.2f}R"


def live_loss_flag_embed(row: dict):
    """v164 D3: the instant flag for one live-loss-watch row (posted once per
    episode, latched in scheduled_jobs). Rides the RETROSPECTIVE kind with
    detail ``live loss watch`` -- no new Kind, so no registry change."""
    wr = row.get("live_wr")
    wr_text = "—" if wr is None else f"{wr:.0f}%"
    horizon = row.get("horizon") or "pooled"
    body = (
        f"**{row['source']} / {row['strategy']} / {horizon}**\n"
        f"• Live N {row.get('live_n', 0)} · WR {wr_text} · ExpR {_r_text(row.get('live_expr'))} · "
        f"90% upper bound {_r_text(row.get('bound_upper'))}\n"
        f"• Meaning: {calibration.LIVE_LOSS_MEANING}.\n"
        f"• {calibration.REGISTRY_CONTEXT_LABEL}: {row.get('registry_status') or '—'} · "
        f"{row.get('registry_window_kind') or '—'} · ExpR {_r_text(row.get('registry_expr'))} "
        f"(run {row.get('registry_run_date') or '—'})\n"
        "• Posted once per episode; the Sunday retrospective re-arms it once the "
        "upper bound is back at or above zero."
    )
    return system_embed(Kind.RETROSPECTIVE, "live loss watch", body)
```

- [ ] **Step 4: Add the flag poster to `loops.py`**

Add to the import block of `swingbot/commands/scanning/loops.py` (after `from swingbot.core.scanning import outlook_session`):

```python
from swingbot.core.tracking import live_loss_watch as loss_watch
```

Insert after `_mark_scheduled_job_fired` (`:699-701`), before `@tasks.loop(minutes=1)` / `async def daily_recap`:

```python
async def _send_live_loss_flags(today: dt.date) -> int:
    watch = await asyncio.to_thread(loss_watch.load_watch)
    pending = [row for row in watch.get("rows") or []
               if row.get("alert") and not loss_watch.is_latched(row)]
    if not pending:
        return 0
    channel = _ops_channel()
    if channel is None:
        log.warning("daily_recap: %d live loss flag(s) pending but no ops channel resolved",
                    len(pending))
        return 0
    sent = 0
    for row in pending:
        message = await notices.send_guarded(
            channel, notices.live_loss_flag_embed(row), what="live loss watch flag")
        if message is not None:            # send_guarded swallows failures: latch only on success
            loss_watch.mark_latched(row, today)
            sent += 1
    return sent


async def _post_live_loss_flags(today: dt.date) -> int:
    """v164 D3: one ops-channel post per alerting live-loss-watch row with no
    open latch, latched once the send returned a message. Called only from
    daily_recap, after the retrospective (whose Sunday Part 11 clears
    recovered latches). Report-only, and never raises: a raise inside a
    tasks.loop body would stop the loop."""
    try:
        return await _send_live_loss_flags(today)
    except Exception:
        log.exception("daily_recap: live loss watch flags failed, none posted")
        return 0
```

In `daily_recap`, change the tail from:

```python
    try:
        await recap._post_retrospective()
    except Exception:
        log.exception("daily_recap: failed to post retrospective")
    await _prune_alert_posts()
```

to:

```python
    try:
        await recap._post_retrospective()
    except Exception:
        log.exception("daily_recap: failed to post retrospective")
    await _post_live_loss_flags(today)
    await _prune_alert_posts()
```

Update the `daily_recap` docstring's last sentence to: `Guards against duplicate posts within the same calendar day. After the retrospective it posts any new live-loss-watch flags (v164) to the ops channel.`

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_live_loss_flag.py`
Expected: PASS, `11 passed`, `0 failed`.

- [ ] **Step 6: Run the neighbouring loop and notice tests**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_scheduled_jobs.py`
Expected: PASS, `0 failed` (its `daily_recap` test now also runs the real `_post_live_loss_flags` over an empty book: no alert rows, so nothing posts).

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_recap_notices.py`
Expected: PASS, `0 failed`.

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_system_notices.py`
Expected: PASS, `0 failed`.

- [ ] **Step 7: Complexity gate**

Run: `python -m radon cc -s -n C $WT/swingbot/commands/scanning/loops.py $WT/swingbot/commands/scanning/notices.py`
Expected: exactly the four pre-existing `loops.py` lines — `_session_scan_tick - C (15)`, `market_data_refresh - C (14)`, `config_watcher - C (13)`, `trade_monitor - C (13)` — and nothing else (no new function, nothing from `notices.py`).

Run: `python -m radon cc -s $WT/swingbot/commands/scanning/loops.py | grep -E "daily_recap|live_loss"`
Expected: `daily_recap - B (7)` unchanged; `_send_live_loss_flags` and `_post_live_loss_flags` both A.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/commands/scanning/notices.py swingbot/commands/scanning/loops.py tests/commands/test_live_loss_flag.py
git -C $WT commit -m "feat(v164): instant latched live-loss-watch flag in the ops channel (LW4)"
git -C $R status --short
```

Expected: the commit lands on branch `2026-10-15-v164-live-loss-watch`; `git -C $R status --short` shows no file of this plan.

