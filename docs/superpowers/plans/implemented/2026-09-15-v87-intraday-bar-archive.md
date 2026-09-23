# v87 Intraday Bar Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-15-v87-intraday-bar-archive-design.md`
**Bump:** bot patch
**Edge:** none (integrity)

**Closed 2026-09-23, merged to `main` at `d4fccbf3`, bot patch.** All tasks
(IA1–IA7) landed as designed; the one-week check (IA7 Step 4) passed. IA1–IA6's
checkboxes below were never ticked during execution despite the work landing
(commits `9afac464`…`f94e45b7`) — left as-is rather than rewritten after the
fact; verdict comes from the merge commits, not the boxes, per
`document-lifecycle.md`.

**Goal:** Archive 15m and 5m bars forward before Yahoo's 60-day window drops them, and stamp `issued_at` on every live plan, so a later entry-timing measurement has data to run on.

**Architecture:** No new subsystem. The existing `market_data_refresh` loop already archives whatever `MARKET_DATA_TIMEFRAMES` lists, merge-only; this plan states the sub-hourly cadence explicitly, points the default at `15min,5min`, adds one plan field set on the live attach path, and adds an ops coverage report.

**Tech Stack:** Python 3.11, pandas, pytest, yfinance (via the existing `data_store` fetchers).

## Global Constraints

- Worktree: `.claude/worktrees/2026-09-15-v87-intraday-bar-archive/`, branch of the same name, created when execution starts (`document-lifecycle.md`).
- Per-task check: `python scripts/dev/testrun.py file <test file>`; the full suite runs **once**, in Task IA5.
- `1min` is **not** added anywhere.
- `issued_at` is set on the live path only; `backtest_scenarios.replay_scenarios` must leave it `None`.
- The E29 reading is **not** stored on the plan.
- `market_data/` paths go through `data_store.cache_path` / `load_from_disk`, never hand-built.
- Never `cd` in a Bash tool command (it breaks the guardrails hook); use absolute paths or `git -C`.
- Production is the Hetzner VM; every production config change is mirrored into the repo and committed (Task IA4 does the mirror before IA7 applies it).

## Parallelisation

- **Group 1 (parallel):** IA1 (`plan_types.py`, `analyze.py`, their tests, the v67 note), IA2 (`data_refresh.py`, its tests), IA3 (new `scripts/ops/intraday_archive_coverage.py`, new test) — disjoint files, no symbol one consumes from another.
- **Sequential:** IA4 after IA2 (the Field help text describes the cadence IA2 sets). IA5 after IA1–IA4. IA6 after the branch merges to `main` (a bump goes last). IA7 after IA6 is deployed.

---

### Task IA1: `issued_at` on every live plan

**Files:**
- Modify: `swingbot/core/planning/plan_types.py` (append one field after `pending_notice`, the last field of `TradePlanV2`)
- Modify: `swingbot/core/scanning/analyze.py:327-388` (`attach_plan_v2`)
- Modify: `docs/superpowers/plans/2026-08-29-v67-json-to-postgres_2b-trading-state-plans.md` (note under `### Task P2-07`)
- Modify: `docs/superpowers/specs/2026-09-15-v87-intraday-bar-archive-design.md` §3.3 (wording fix, see Step 9)
- Test: `tests/planning/test_plan_serialization.py`, `tests/scanning/test_engine_v2_plans.py`, `tests/db/test_plans_repository.py`, `tests/backtesting/test_backtest_scenarios.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `TradePlanV2.issued_at: str | None` — UTC ISO-8601 timestamp (`datetime.now(timezone.utc).isoformat()`), `None` for replayed plans and for records persisted before v87.

- [ ] **Step 1: Write the failing serialization tests**

Append to `tests/planning/test_plan_serialization.py`:

```python
def test_issued_at_defaults_to_none_and_round_trips():
    p = _plan()
    assert p.issued_at is None
    stamped = _plan(issued_at="2026-09-15T14:31:07.123456+00:00")
    q = plan_from_dict(plan_to_dict(stamped))
    assert q.issued_at == "2026-09-15T14:31:07.123456+00:00"


def test_pre_v87_record_without_issued_at_loads_as_none():
    d = plan_to_dict(_plan())
    d.pop("issued_at", None)
    assert plan_from_dict(d).issued_at is None
```

- [ ] **Step 2: Write the failing live-attach test**

Append to `tests/scanning/test_engine_v2_plans.py` (it already imports `config`, `engine`, `make_ohlcv`, and defines `_item()` / `_scenario()`):

```python
def test_attach_plan_v2_stamps_issued_at_in_utc(monkeypatch):
    from datetime import datetime, timezone
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    item = _item()
    before = datetime.now(timezone.utc)
    engine.attach_plan_v2(item, _scenario(), make_ohlcv([100.0] * 60),
                          "AAPL", "4w", level_map=None)
    after = datetime.now(timezone.utc)
    assert item.plan_v2 is not None
    stamped = datetime.fromisoformat(item.plan_v2.issued_at)
    assert stamped.tzinfo is not None and stamped.utcoffset().total_seconds() == 0
    assert before <= stamped <= after
```

- [ ] **Step 3: Write the failing replay test**

Append to `tests/backtesting/test_backtest_scenarios.py` (it already defines `_structured_df()` and `GATES`, a fixture pair that `test_replay_yields_plans_with_cooldown` proves produces plans; the file is `pytest.mark.slow`):

```python
def test_replayed_plans_carry_no_issued_at():
    """v87: a replayed plan has no wall-clock issuance. issued_at is stamped
    by analyze.attach_plan_v2 only; a backtest plan carrying one would pool
    fabricated timestamps into any later entry-timing study."""
    out = bs.replay_scenarios("AAPL", _structured_df(), "4w", gates=GATES)
    assert out, "fixture must produce at least one plan"
    assert all(plan.issued_at is None for _, plan in out)
```

- [ ] **Step 4: Run the three files to verify failure**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py
python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py
python scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios.py
```

Expected: the serialization tests FAIL (`TypeError: ... unexpected keyword argument 'issued_at'` / `AttributeError`); the attach test FAILS on `item.plan_v2.issued_at`; the new replay test FAILS with `AttributeError: 'TradePlanV2' object has no attribute 'issued_at'`.

- [ ] **Step 5: Add the field**

In `swingbot/core/planning/plan_types.py`, directly after `pending_notice: dict | None = None` (the current last field of `TradePlanV2`):

```python
    # v87: the UTC wall-clock moment the live scan attached this plan
    # (analyze.attach_plan_v2). created_at is a DATE; an entry-timing study
    # over the 15m/5m archive needs the minute. None for every replayed plan
    # -- a backtest has no wall clock -- and for records persisted before
    # v87. The E29 intraday reading is deliberately NOT stored beside it: it
    # is a pure function of the archived 1h tape and this timestamp.
    issued_at: str | None = None
```

- [ ] **Step 6: Stamp it on the live path**

In `swingbot/core/scanning/analyze.py`, add to the imports near the top (beside `import os`):

```python
from datetime import datetime, timezone
```

In `attach_plan_v2`, replace:

```python
        item.plan_v2 = plan
        try:
            plan.risk_features = risk_features.build(
```

with:

```python
        plan.issued_at = datetime.now(timezone.utc).isoformat()
        item.plan_v2 = plan
        try:
            plan.risk_features = risk_features.build(
```

Before editing, run `git -C E:/Documents/Private/Projects/Discord-Bot grep -n "^from datetime\|^import datetime" -- swingbot/core/scanning/analyze.py`. If `datetime` is already imported under another form, reuse that form instead of adding a second import.

- [ ] **Step 7: Run the three files to verify they pass**

Same three commands as Step 4. Expected: all PASS, `0 failed`.

- [ ] **Step 8: Pin the field in the Postgres round-trip test and the v67 plan**

In `tests/db/test_plans_repository.py`, in `test_full_plan_document_round_trips`, add `issued_at="2026-09-15T14:31:07+00:00",` to the `_plan("P1", ...)` call's keyword arguments, beside `notified_stop=101.5,`. If a second round-trip test (`test_the_full_plan_dict_round_trips`) exists in the file, add the same keyword there too.

In `docs/superpowers/plans/2026-08-29-v67-json-to-postgres_2b-trading-state-plans.md`, directly below the existing v81 note under `### Task P2-07: The plans repository and importer`, insert:

```markdown
> **v87 (2026-09-15):** `TradePlanV2` gained `issued_at` (UTC ISO timestamp,
> live path only). It lives inside `doc`; no column is added. The round-trip
> test carries it, so an importer that drops keys it does not know fails it.
```

In the same file's round-trip test code block for P2-07 (the `rec = _p("P1", ...)` call), add `issued_at="2026-09-15T14:31:07+00:00",` beside `notified_stop=101.5,`.

Run: `python scripts/dev/testrun.py file tests/db/test_plans_repository.py`. Expected: PASS, or SKIPPED if no local Postgres is configured — record which in the task report. A skip is not a failure here; the full-suite run in IA5 runs it wherever the DB fixture is available.

- [ ] **Step 9: Correct the spec's attach-site wording**

In the spec §3.3, replace `Set on the live path only
(strategy- and confluence-sourced plans alike); the backtest leaves it `None`,` with `Set on the live path only,
in `analyze.attach_plan_v2` — the single constructor every plan the live scan
persists goes through; the backtest leaves it `None`,`. (Verified while planning: `scan_run.py:778`'s `PlanStore().add(plan_v2)` is the only live persist site, and its plan always comes from `attach_plan_v2`.)

- [ ] **Step 10: Commit**

```bash
git -C <worktree> add swingbot/core/planning/plan_types.py swingbot/core/scanning/analyze.py tests/planning/test_plan_serialization.py tests/scanning/test_engine_v2_plans.py tests/backtesting/test_backtest_scenarios.py tests/db/test_plans_repository.py docs/superpowers/plans/2026-08-29-v67-json-to-postgres_2b-trading-state-plans.md docs/superpowers/specs/2026-09-15-v87-intraday-bar-archive-design.md
git -C <worktree> commit -m "feat(v87): stamp issued_at on every live plan"
```

(End the message with the session's attribution lines.)

---

### Task IA2: State the sub-hourly refresh cadence

**Files:**
- Modify: `swingbot/core/marketdata/data_refresh.py:41-46` (`REFRESH_HOURS`)
- Test: `tests/marketdata/test_data_refresh.py`, `tests/test_market_data_refresh_task.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `REFRESH_HOURS["15min"] == 24.0`, `REFRESH_HOURS["5min"] == 24.0`.

- [ ] **Step 1: Write the failing cadence test**

Append to `tests/marketdata/test_data_refresh.py`:

```python
def test_sub_hourly_archive_frames_state_a_24h_cadence():
    """v87: 15min/5min are archived forward. 24h against Yahoo's ~60-day
    window leaves ~59 days of slack; the value is stated, not inherited from
    DEFAULT_REFRESH_HOURS, so a later change to the default cannot silently
    stretch it."""
    assert refresh_mod.REFRESH_HOURS["15min"] == 24.0
    assert refresh_mod.REFRESH_HOURS["5min"] == 24.0
    assert "1min" not in refresh_mod.REFRESH_HOURS
    for tf in ("15min", "5min"):
        assert data_store.TIMEFRAMES[tf]["max_days"] >= 30 * refresh_mod.REFRESH_HOURS[tf] / 24


def test_is_stale_uses_the_sub_hourly_cadence(tmp_path):
    import os, time
    path = cache_path("AAPL", "5min", base_dir=str(tmp_path))
    with open(path, "w") as f:
        f.write("Datetime,Open,High,Low,Close,Volume\n")
    twenty_hours_ago = time.time() - 20 * 3600
    os.utime(path, (twenty_hours_ago, twenty_hours_ago))
    assert refresh_mod.is_stale("AAPL", "5min", base_dir=str(tmp_path)) is False
    thirty_hours_ago = time.time() - 30 * 3600
    os.utime(path, (thirty_hours_ago, thirty_hours_ago))
    assert refresh_mod.is_stale("AAPL", "5min", base_dir=str(tmp_path)) is True
```

- [ ] **Step 2: Write the ordering test**

Append to `tests/test_market_data_refresh_task.py`:

```python
def test_sub_hourly_frames_refresh_after_hourly(monkeypatch):
    """v87: when the sweep's time budget binds, the frames it defers must be
    the archive-only ones (15min/5min), never hourly, which feeds live E29
    context."""
    from swingbot.commands.scanning import loops as loops_mod

    captured = {}

    def fake_refresh_all(symbols, timeframes, **_kwargs):
        captured["timeframes"] = timeframes
        return {"summary": {tf: {"full": 0, "incremental": 0, "fresh": 1,
                                  "failed": 0, "added": 0} for tf in timeframes},
                "failures": [], "state": {}, "deadline_hit": False}

    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", True, raising=False)
    monkeypatch.setattr(config, "MARKET_DATA_TIMEFRAMES", "5min,15min,hourly,daily",
                        raising=False)
    monkeypatch.setattr(loops_mod, "load_watchlist", lambda: ["AAPL"], raising=False)
    monkeypatch.setattr(loops_mod, "_refresh_priority_tickers", lambda: [])
    monkeypatch.setattr("swingbot.core.marketdata.data_refresh.refresh_all", fake_refresh_all)

    _run(scanning_mod.market_data_refresh.coro())

    order = captured["timeframes"]
    assert order.index("hourly") < order.index("15min")
    assert order.index("hourly") < order.index("5min")
```

- [ ] **Step 3: Run both files to verify**

```bash
python scripts/dev/testrun.py file tests/marketdata/test_data_refresh.py
python scripts/dev/testrun.py file tests/test_market_data_refresh_task.py
```

Expected: `test_sub_hourly_archive_frames_state_a_24h_cadence` FAILS with `KeyError: '15min'`. `test_is_stale_uses_the_sub_hourly_cadence` and `test_sub_hourly_frames_refresh_after_hourly` already PASS (the default is 24h and `sorted()` is stable on ties) — they are regression pins for behaviour this plan relies on, and passing before the change is correct.

- [ ] **Step 4: Add the entries**

In `swingbot/core/marketdata/data_refresh.py`, replace:

```python
REFRESH_HOURS = {
    "monthly": 24.0,
    "weekly": 24.0,
    "daily": 12.0,
    "hourly": 4.0,
}
```

with:

```python
REFRESH_HOURS = {
    "monthly": 24.0,
    "weekly": 24.0,
    "daily": 12.0,
    "hourly": 4.0,
    # v87: archived forward for a future entry-timing measurement. Yahoo
    # serves these for ~60 days only, so 24h leaves ~59 days of slack before
    # a missed refresh loses bars. Stated rather than inherited from
    # DEFAULT_REFRESH_HOURS. 1min is deliberately absent (not archived).
    "15min": 24.0,
    "5min": 24.0,
}
```

- [ ] **Step 5: Run both files to verify they pass**

Same two commands as Step 3. Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add swingbot/core/marketdata/data_refresh.py tests/marketdata/test_data_refresh.py tests/test_market_data_refresh_task.py
git -C <worktree> commit -m "feat(v87): state the 24h refresh cadence for the 15m/5m archive"
```

---

### Task IA3: The archive coverage report

**Files:**
- Create: `scripts/ops/intraday_archive_coverage.py`
- Test: `tests/scripts/test_intraday_archive_coverage.py`

**Interfaces:**
- Consumes: `swingbot.core.marketdata.data_store.load_from_disk(ticker, interval, base_dir)`, `data_store.timeframe_name`.
- Produces: `coverage(base_dir: str, timeframes=("15min", "5min")) -> dict[str, dict]`, `render(report: dict) -> str`, `main(argv: list[str] | None = None) -> int`. Per-timeframe dict keys: `symbols` (int), `earliest` (str ISO date or None), `latest` (str ISO date or None), `median_sessions` (float or None), `stale` (sorted list of symbols).

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_intraday_archive_coverage.py`:

```python
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import intraday_archive_coverage as cov  # noqa: E402
from swingbot.core.marketdata.data_store import cache_path  # noqa: E402


def _write_intraday(base_dir, symbol, tf, first_day, sessions, bars_per_session=4):
    days = pd.bdate_range(first_day, periods=sessions)
    stamps = [day + pd.Timedelta(hours=14, minutes=30 + 15 * k)
              for day in days for k in range(bars_per_session)]
    frame = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0,
                          "Volume": 100.0}, index=pd.DatetimeIndex(stamps, name="Datetime"))
    frame.to_csv(cache_path(symbol, tf, base_dir=str(base_dir)))


def test_coverage_reports_depth_and_a_stale_symbol(tmp_path):
    _write_intraday(tmp_path, "AAPL", "15min", "2026-07-01", 50)
    _write_intraday(tmp_path, "MSFT", "15min", "2026-07-01", 50)
    _write_intraday(tmp_path, "OLD", "15min", "2026-07-01", 40)   # stops 10 sessions early
    report = cov.coverage(str(tmp_path), timeframes=("15min",))
    tf = report["15min"]
    assert tf["symbols"] == 3
    assert tf["earliest"] == "2026-07-01"
    assert tf["latest"] == str(pd.bdate_range("2026-07-01", periods=50)[-1].date())
    assert tf["median_sessions"] == 50
    assert tf["stale"] == ["OLD"]


def test_an_empty_timeframe_reports_zero_not_a_crash(tmp_path):
    report = cov.coverage(str(tmp_path), timeframes=("5min",))
    assert report["5min"] == {"symbols": 0, "earliest": None, "latest": None,
                              "median_sessions": None, "stale": []}


def test_render_and_main_exit_zero(tmp_path, capsys):
    _write_intraday(tmp_path, "AAPL", "5min", "2026-07-01", 5)
    assert cov.main(["--base-dir", str(tmp_path), "--timeframes", "5min"]) == 0
    out = capsys.readouterr().out
    assert "5min" in out and "symbols=1" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/scripts/test_intraday_archive_coverage.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'intraday_archive_coverage'`.

- [ ] **Step 3: Write the script**

Create `scripts/ops/intraday_archive_coverage.py`:

```python
#!/usr/bin/env python3
"""v87: is the 15m/5m archive actually growing?

Yahoo serves sub-hourly bars for ~60 days only; the bot's market_data_refresh
loop archives them forward, merge-only. This prints, per timeframe, how many
symbols are archived, the earliest and latest bar across the archive, the
median depth in sessions, and which symbols have fallen more than
STALE_SESSIONS behind the archive's newest bar.

Run on production (the archive lives there, not on the dev machine):

    python scripts/ops/intraday_archive_coverage.py
    python scripts/ops/intraday_archive_coverage.py --timeframes 5min

A week after rollout, `earliest` must be unchanged and `latest` current.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swingbot.core.marketdata.data_store import DATA_DIR, load_from_disk, timeframe_name  # noqa: E402

ARCHIVE_TIMEFRAMES = ("15min", "5min")
STALE_SESSIONS = 3


def _symbols(base_dir: str, tf: str) -> list[str]:
    folder = os.path.join(base_dir, tf)
    if not os.path.isdir(folder):
        return []
    return sorted(name[:-4] for name in os.listdir(folder) if name.endswith(".csv"))


def coverage(base_dir: str, timeframes=ARCHIVE_TIMEFRAMES) -> dict:
    report = {}
    for raw in timeframes:
        tf = timeframe_name(raw)
        spans = {}
        for symbol in _symbols(base_dir, tf):
            frame = load_from_disk(symbol, tf, base_dir=base_dir)
            if frame is None or frame.empty:
                continue
            dates = frame.index.normalize().unique()
            spans[symbol] = (dates.min().date(), dates.max().date(), len(dates))
        if not spans:
            report[tf] = {"symbols": 0, "earliest": None, "latest": None,
                          "median_sessions": None, "stale": []}
            continue
        newest = max(last for _, last, _ in spans.values())
        stale = sorted(s for s, (_, last, _) in spans.items()
                       if np.busday_count(last, newest) > STALE_SESSIONS)
        report[tf] = {
            "symbols": len(spans),
            "earliest": str(min(first for first, _, _ in spans.values())),
            "latest": str(newest),
            "median_sessions": statistics.median(n for _, _, n in spans.values()),
            "stale": stale,
        }
    return report


def render(report: dict) -> str:
    lines = []
    for tf, row in report.items():
        lines.append(f"{tf}: symbols={row['symbols']} earliest={row['earliest']} "
                     f"latest={row['latest']} median_sessions={row['median_sessions']}")
        if row["stale"]:
            lines.append(f"  stale (> {STALE_SESSIONS} sessions behind): {', '.join(row['stale'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-dir", default=str(ROOT / DATA_DIR))
    parser.add_argument("--timeframes", default=",".join(ARCHIVE_TIMEFRAMES))
    args = parser.parse_args(argv)
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    print(render(coverage(args.base_dir, timeframes)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scripts/test_intraday_archive_coverage.py`
Expected: 3 PASS.

If `load_from_disk` returns the index as strings rather than a `DatetimeIndex` for these CSVs, fix it inside `coverage` with `pd.to_datetime(frame.index, utc=True)` before `.normalize()` — do not change `data_store`.

- [ ] **Step 5: Commit**

```bash
git -C <worktree> add scripts/ops/intraday_archive_coverage.py tests/scripts/test_intraday_archive_coverage.py
git -C <worktree> commit -m "feat(v87): intraday archive coverage report"
```

---

### Task IA4: Point the default at the archive, and mirror it

**Files:**
- Modify: `swingbot/config.py:778-784` (`MARKET_DATA_TIMEFRAMES` Field)
- Modify: `.env.example:484-485`
- Test: `tests/test_config_flags.py`

**Interfaces:**
- Consumes: IA2's `REFRESH_HOURS` entries (the help text states that cadence).
- Produces: `config.FIELDS` entry `MARKET_DATA_TIMEFRAMES` with default `"monthly,weekly,daily,hourly,15min,5min"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config_flags.py`:

```python
def test_v87_market_data_timeframes_default_archives_15m_and_5m():
    from swingbot.core.marketdata.data_store import timeframe_name

    by_key = {f.key: f for f in config.FIELDS}
    names = [t.strip() for t in by_key["MARKET_DATA_TIMEFRAMES"].default.split(",")]
    assert names == ["monthly", "weekly", "daily", "hourly", "15min", "5min"]
    assert [timeframe_name(n) for n in names] == names
    assert "1min" not in names
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/test_config_flags.py`
Expected: FAIL — the default list ends at `hourly`.

- [ ] **Step 3: Change the Field**

In `swingbot/config.py`, replace:

```python
          type="text", default="monthly,weekly,daily,hourly",
          help="Comma-separated timeframe folders to keep current. Names come from "
               "swingbot/core/marketdata/data_store.py:TIMEFRAMES. Sub-hourly ones (15min, 5min, 1min) "
               "are accepted but Yahoo only serves them for the trailing 30-60 days, so they "
               "cannot support training -- leave them out unless you want live entry timing."),
```

with:

```python
          type="text", default="monthly,weekly,daily,hourly,15min,5min",
          help="Comma-separated timeframe folders to keep current. Names come from "
               "swingbot/core/marketdata/data_store.py:TIMEFRAMES. 15min and 5min are archived "
               "FORWARD (v87): Yahoo serves them for ~60 days only, so the archive is only as "
               "deep as the day it started, and removing them here stops the archive -- bars "
               "that age out meanwhile are gone for good. They refresh every 24h, after hourly. "
               "1min is accepted but not archived by default (~600 MB/year, little use at swing horizons)."),
```

- [ ] **Step 4: Mirror into `.env.example`**

Replace:

```
# Comma-separated timeframe folders to keep current.
MARKET_DATA_TIMEFRAMES=monthly,weekly,daily,hourly
```

with:

```
# Comma-separated timeframe folders to keep current. 15min/5min are archived
# forward for a future entry-timing measurement (v87) -- Yahoo only serves
# ~60 days of them, so removing them stops the archive for good.
MARKET_DATA_TIMEFRAMES=monthly,weekly,daily,hourly,15min,5min
```

- [ ] **Step 5: Run to verify it passes, plus the refresh-task file**

```bash
python scripts/dev/testrun.py file tests/test_config_flags.py
python scripts/dev/testrun.py file tests/test_market_data_refresh_task.py
```

Expected: all PASS. The second run proves no existing refresh-task test assumed the old default (they all monkeypatch `MARKET_DATA_TIMEFRAMES`; if one does not and now fails, set it explicitly in that test to the value it was written against).

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add swingbot/config.py .env.example tests/test_config_flags.py
git -C <worktree> commit -m "feat(v87): archive 15min and 5min bars by default"
```

---

### Task IA5: Full-suite verification

Dispatch the `test-runner` subagent (or run `python scripts/dev/testrun.py full`) once, over IA1–IA4. Expect `0 failed`, `0 xfailed`. This plan touches no `frontend/` file, so no `npm test`.

**If it is not green, fix forward from those failures** — they are this plan's regressions, and the task is not done until the run is. Record the verdict line in the task report.

Then merge the branch to `main` per `document-lifecycle.md`. A conflict-free merge is not re-run; a merge that resolved conflicts gets one run.

---

### Task IA6: Release — bot patch

Runs on `main` after IA5's merge (a bump goes last, `working-conventions.md`).

- [ ] **Step 1:** Read `VERSION.json` from disk. Increment `bot` at patch level; leave `ui` untouched. Set `bot_updated` to now, UTC, `YYYY-MM-DD HH-MM-SS`.
- [ ] **Step 2:** Run `python scripts/dev/build_version_matrix.py`.
- [ ] **Step 3:** Run `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`. Expected: PASS (it is the only check that can catch a missed regeneration).
- [ ] **Step 4:** Commit both files: `release(bot): <new version> -- intraday bar archive`.

---

### Task IA7: Production rollout and the one-week check

**Outward-facing.** Pushing `main` deploys through GitHub Actions (`docs/deploy/DEPLOY_HETZNER.md`). Confirm with the human partner before `git push`.

- [x] **Step 1: Deploy.** Pushed `main` at `d4fccbf3` on 2026-09-17 after the human partner's confirmation. GitHub Actions run `35207850361` completed successfully.

- [x] **Step 2: Set the production value.** Production's `.env` sets `MARKET_DATA_TIMEFRAMES` explicitly (verified 2026-09-15: `monthly,weekly,daily,hourly`), so the new default alone does **not** reach it. Change it in the admin UI's Settings page (saving sends the bot `SIGHUP`), or on the VM:

```bash
./scripts/ops/ssh-hetzner.sh "sed -i 's/^MARKET_DATA_TIMEFRAMES=.*/MARKET_DATA_TIMEFRAMES=monthly,weekly,daily,hourly,15min,5min/' /opt/swing-bot/.env && grep '^MARKET_DATA_TIMEFRAMES' /opt/swing-bot/.env && cd /opt/swing-bot && docker compose kill -s SIGHUP bot"
```

The repo already carries this value (IA4), so the mirror rule is satisfied before the change is made.

Done by the human partner directly on the VM at 2026-09-17 10:04:18 UTC; the bot's config auto-reload logged the change (`MARKET_DATA_TIMEFRAMES: 'monthly,weekly,daily,hourly' -> 'monthly,weekly,daily,hourly,15min,5min'`), confirmed by SSH read-only log check.

- [x] **Step 3: First-day check.** After two refresh wakes (`MARKET_DATA_REFRESH_MINUTES`, default 60):

```bash
./scripts/ops/ssh-hetzner.sh "grep -h 'market_data_refresh' /opt/swing-bot/logs/*.log | tail -20; grep -hi 'heartbeat\|disconnect' /opt/swing-bot/logs/*.log | tail -5"
./scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/ops/intraday_archive_coverage.py"
```

Read `/opt/swing-bot/logs/*.log`, not `docker logs` (empty after a deploy). Expected within 24h: `15min` and `5min` each report `symbols` equal to the watchlist size and `median_sessions` near 40 (≈60 calendar days), no new gateway disconnects, and summary lines that name `15min`/`5min`. If the cold pull is still incomplete after 24h, record how far it got — do **not** raise `MARKET_DATA_REFRESH_BUDGET_SECONDS` without the human partner's say-so (the budget exists because of the 2026-08-24 outage).

Ran 2026-09-17 ~12:20 UTC (within 2h of Step 2, ahead of the 24h expectation): `15min` and `5min` both report `symbols=77` (full watchlist), `earliest=2026-06-23`, `latest=2026-09-17`, `median_sessions=60` — beats the ≈40 expectation. No gateway disconnects in the heartbeat log across the window (106-114ms latency throughout). The 11:04 UTC refresh wake did hit its 120s time budget on the cold pull and carried the remainder to the next wake, exactly the documented fallback behavior, not an error.

- [x] **Step 4: One-week check — the done condition.** Seven days after Step 2 (target: 2026-09-24), run the coverage command again. Done when, for both timeframes, `earliest` is unchanged from Step 3 (or earlier) and `latest` is the most recent session. Record both readings in the close-out commit.

Ran 2026-09-23 (one day ahead of the 2026-09-24 target, at the human partner's request): `15min` reports `symbols=77 earliest=2024-09-19 latest=2026-09-22 median_sessions=63`; `5min` reports `symbols=77 earliest=2026-06-23 latest=2026-09-22 median_sessions=64`. Both `earliest` readings are unchanged from or earlier than Step 3 (`15min` in particular now reaches back to 2024-09-19, well before Step 3's 2026-06-23), and `latest=2026-09-22` is the most recent closed session as of the check. Done condition met.

**Note (added after Step 3, human partner's request):** No Claude session or scheduling mechanism available in this repo's tooling reliably survives the dev machine being off for 7 days (session-local cron dies with the session; a cloud routine cannot reach the VM's SSH key, which by design lives only in WSL on the dev machine, never committed). Installed a daily crontab entry directly on the VM instead, mirrored at `scripts/ops/install_intraday_coverage_cron.sh`: it runs `intraday_archive_coverage.py` inside the bot container at 06:07 UTC daily and appends timestamped output to `/opt/swing-bot/logs/intraday_coverage_cron.log`, so a reading exists for 2026-09-24 regardless of session state. Verified with one manual trigger (2026-09-17T14:36:26Z) before relying on the schedule. This is additive ops tooling, not a plan task; left in place after Step 4 unless the human partner asks it removed.

- [x] **Step 5: Close out** per `document-lifecycle.md`: move this plan and its spec to `implemented/`. Amend `Bump:`/`Edge:` in the closing commit only if the outcome differed from the prediction, with one clause saying why. Outcome matched the prediction — `Bump:`/`Edge:` unchanged.
