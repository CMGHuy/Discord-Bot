# v82 — Earnings Blackout Measurement Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-10-v82-earnings-awareness-design.md` (Phase B, C2/C3, and its "Planning findings" section)
**Bump:** ui patch
**Edge:** expectancy

**Goal:** Build a session calendar, one earnings calendar, and a pre-registered
instrument, then run the earnings-blackout hypothesis through the v72 funnel
and record whatever it says.

**Architecture:** `core/market/session.py` gains a `SessionCalendar`;
`core/market/earnings_calendar.py` owns every earnings question (report timing,
reaction session, sessions-to-reaction, exposure at K, the display label);
`core/backtesting/earnings_blackout.py` is the pure arithmetic of the
measurement (arms, Stage 1 selection, folds, calendar-shift permutation) over an
exposure table; `scripts/backtest/measure_earnings_blackout.py` builds that
table from one replay per window and writes what `validate_component.py`
consumes.

**Tech Stack:** Python 3.11, pandas, numpy, yfinance, pytest.

## Global Constraints

- **Pre-registered and frozen by the spec commit:** `GRID = (1, 2, 3, 5)`,
  `COVERAGE_FLOOR_PCT = 90.0`, `SELECTION_WINDOW = 2018-06-01..2020-12-31`,
  `FOLD_TEST_YEARS = 2021, 2022, 2023`, `VALIDATION_WINDOW =
  2024-01-01..2025-12-31`, permutation `n = 200`, `seed = 42`, shift
  `U[20, 200)` sessions. Changing any of them is a new pre-registration.
- **2024-01-01..2025-12-31 is never replayed or read before a Stage 2 PASS
  is committed.** The instrument enforces this (`--stage2-doc`); never
  bypass it.
- `swingbot/core/backtesting/acceptance.py` and `backtest_wf.py` get **no diff**.
- **No live behaviour change.** `EARNINGS_BLACKOUT_SESSIONS` defaults to 0 and
  stays unwired; Plan A wires it.
- Exposure rule (B2): exposed at K iff `1 <= distance <= K`; ETFs and
  uncovered rows are never exposed and stay in both arms.
- Per-task checks: `python scripts/dev/testrun.py file <one test file>`. The
  full suite runs **once**, in M7. Tasks M8–M14 change no code.
- Replays longer than a couple of minutes go to the `backtest-runner`
  subagent; progress is `data/v82/<run>/progress.txt` ("37/89 tickers (42%)"),
  deleted on completion.
- Never hard-code a version number. M7 resolves it from `VERSION.json`.
- Every outcome is written down — PASS, FAIL, REFUSED and INSUFFICIENT_COVERAGE
  alike.

## Before starting

- Work M1–M7 in a worktree named after the plan stem:
  `.claude/worktrees/2026-09-10-v82-earnings-measurement/`, branch
  `2026-09-10-v82-earnings-measurement` (`docs/claude/document-lifecycle.md`).
  Run `git worktree list` first; never dispatch with `isolation: "worktree"`
  onto an existing worktree.
- `data/backtest_cache/` is untracked, so the worktree has no OHLCV cache.
  Tests that need it skip; M7 runs them on `main`. M8–M14 run from the **main
  checkout**.
- This plan does not depend on v81. Plan A (label, notice, wiring) does.

## Parts

| File | Tasks |
|---|---|
| `2026-09-10-v82-earnings-measurement_1-foundation.md` | M1 session calendar · M2 earnings calendar · M3 rename, frozen class, gate rewrite |
| `2026-09-10-v82-earnings-measurement_2-instrument.md` | M4 measurement arithmetic · M5 earnings-date fetch · M6 instrument script · M7 full suite, merge, release |
| `2026-09-10-v82-earnings-measurement_3-measurement.md` | M8 data and dry run · M9 Run 1 · M10 Stage 1 · M11 Stage 0 · M12 Stage 2 · M13 Run 2 and Stage 3 · M14 record and close out |

## File map

| File | Change | Task |
|---|---|---|
| `swingbot/core/market/session.py` | `NYSE_HOLIDAYS`, `SessionCalendar`, `nyse_calendar()` | M1 |
| `tests/market/test_session_calendar.py` | new | M1 |
| `swingbot/core/market/events.py` | `get_earnings_datetimes` (cached, past + upcoming) | M2 |
| `swingbot/core/market/earnings_calendar.py` | new — `Report`, `Label`, timing, reaction session, distance, exposure, sources, label | M2 |
| `tests/market/test_earnings_calendar.py` | new | M2 |
| `tests/market/test_events.py` | cache fixture clears the new cache; four tests | M2 |
| `swingbot/config.py` | `EARNINGS_BLACKOUT_DAYS` → `EARNINGS_BLACKOUT_SESSIONS`, `searchable` → `frozen` | M3 |
| `swingbot/scan_params.py` | `earnings_blackout_days` → `earnings_blackout_sessions` | M3 |
| `swingbot/core/edge/gates.py` | `in_earnings_blackout` over B2's rule, `now=` honoured | M3 |
| `.env.example`, `scripts/backtest/wf_components.py` | renamed key and note | M3 |
| `tests/edge/test_edge_gates.py`, `tests/backtesting/test_knob_observability.py`, `tests/test_scan_params_coverage.py` | follow the rename | M3 |
| `swingbot/core/backtesting/earnings_blackout.py` | new — pre-registered constants, `ExposureRow`, arms, selection, folds, permutation | M4 |
| `tests/backtesting/test_earnings_blackout.py` | new | M4 |
| `scripts/data/fetch_earnings_dates.py` | new | M5 |
| `tests/scripts/test_fetch_earnings_dates.py` | new | M5 |
| `scripts/backtest/measure_earnings_blackout.py` | new — `replay`, `coverage`, `select`, `arms`, `permute` | M6 |
| `tests/scripts/test_measure_earnings_blackout.py` | new | M6 |
| `.gitignore` | `data/v82/` | M6 |
| `VERSION.json`, `swingbot/admin/version_history.json` | ui patch | M7 |
| `docs/superpowers/results/<date>-v82-earnings-*.md` | results per stage | M8–M13 |
| `docs/claude/backtest-methodology.md` | closed-pre-registrations row | M14 |

## Parallelisation

- **Sequential:** M1 → M2 — `earnings_calendar.py` imports `SessionCalendar`,
  `nyse_calendar` and `now_et` from M1.
- **Group 1 (parallel, after M2):** M3, M4, M5 — disjoint files (config /
  scan_params / gates / wf_components and their tests; `earnings_blackout.py`
  and its test; the fetch script and its test). Each consumes only M2's
  symbols (`is_exposed`, `next_reaction_distance`, `LiveSource`, `CSV_FIELDS`,
  `report_from_timestamp`).
- **Sequential:** M6 after M4 (imports `earnings_blackout`). M7 after M3–M6.
  M8 → M14 in order: each consumes the previous task's committed result, and
  M10–M13 each end the plan early (jump to M14) on a negative verdict.

## Planning findings, recorded in the spec in this plan's commit

The spec's "Planning findings (Plan B)" section carries all eleven. The ones
that change a task here:

1. Stage 3's permutation is a calendar shift; `permutation_test.py` cannot see
   a post-hoc filter.
2. The rename (spec C2/C3) moved into this plan (M3) because
   `EARNINGS_BLACKOUT_DAYS` also lives in `ScanParams`, `.env.example` and the
   knob-observability `EXEMPT` table — this plan's release is `ui patch`.
3. `get_next_earnings_datetime` drops a before-open report on its own day;
   `LiveSource` uses a new `get_earnings_datetimes`.
4. The holiday table runs through 2030 to match `opex.LAST_YEAR_COVERED`;
   `opex.py` is untouched and pinned by an agreement test.
5. Confluence rows are relabelled `confluence:<strategy>` so pairing keys and
   strata never collide with strategy backtests.

## Progress

- [x] M1 — session calendar
- [x] M2 — earnings calendar
- [x] M3 — rename, frozen class, gate rewrite
- [x] M4 — measurement arithmetic
- [x] M5 — earnings-date fetch
- [x] M6 — instrument script
- [x] M7 — full suite, merge, release (ui patch)
- [x] M8 — earnings data and dry run
- [x] M9 — Run 1 (2018-06..2023-12)
- [ ] M10 — Stage 1 selection
- [ ] M11 — Stage 0 MDE
- [ ] M12 — Stage 2 walk-forward
- [ ] M13 — Run 2 and Stage 3 (one shot)
- [ ] M14 — record and close out
