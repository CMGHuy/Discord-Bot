Version: ui 1.8.0 · bot 1.3.2
Bump: none — this plan ships no running code. It adds one script under
`scripts/` and one results document. Per `document-conventions.md`, "a spec that
ships no running code bumps nothing", and a measurement is finished work whether
the answer is yes or no.
Edge: expectancy — the hypothesis is that a measurable slice of the
confluence population's negative expectancy is concentrated on high-alert-density
days, where many simultaneous alerts are one market-wide condition wearing many
tickers. If true, a later throttle removes a negative population. If false, that
is recorded and the idea is closed.
Origin: EXTERNAL — HKUDS/Vibe-Trading, read 2026-08-22, now vendored
(untracked, gitignored) at `Vibe-Trading-main/` in this repo's root. The
busy-day vs quiet-day PnL
comparison is from `agent/src/skills/trade-journal/SKILL.md`, where it diagnoses
overtrading in a human. Reframed here as a correlation question about a
mechanical scanner; the bucket edges are this repo's, chosen for a 75-ticker
universe, not that project's.
**Revert lever:** none required. This plan ships no running code — one script
under `scripts/` and one results document. It cannot affect trading performance.
Any throttle it might justify is a separate spec with its own pre-registration.

# Alert-density expectancy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether expectancy varies with how many alerts the scanner
fires on the same day, over TRAIN. Nothing more. This plan deliberately stops
at the number.

**Where the idea comes from.** HKUDS/Vibe-Trading's `trade-journal` skill
diagnoses "overtrading" by comparing average PnL on busy days (≥3 trades) with
quiet days (≤1), and reports a large gap. In a human that is a behavioural
finding. For this bot it is a *correlation* finding, and it is the same
pathology as spec v49 one level up: v49 says several detectors landing on one
price can be one observation; this asks whether several tickers alerting on one
day can be one trade.

**Architecture:** One script under `scripts/backtest/`, one results doc. No
module under `swingbot/`, no config Field, no flag, no gate.

**Tech Stack:** the existing backtest replay + stdlib. No new dependency.

## Global Constraints

- **This plan changes no trading behaviour and ships no flag.** If the answer
  is yes, the throttle is a *new* spec with its own pre-registered hypothesis
  and its own one-shot budget. Writing a gate inside this plan would spend a
  validation shot on a component nobody pre-registered.
- **TRAIN only (2020-01-01…2023-12-31).** The 2024–25 window is tainted for any
  selection decision, and "is there a density effect worth building on" is
  exactly a selection decision.
- **`data/scan_telemetry.jsonl` cannot answer this.** It carries per-scan
  `alerts` / `signals` counts, but its history starts 2026-08-07 — about two
  weeks. It is a live cross-check with a stated caveat in the results doc, never
  the primary instrument. Do not let its convenience pull the measurement onto a
  sample that cannot support it.
- **Density is defined once, in code, before any number is read.** See Task 1.
  Redefining it after seeing a null result is the exact failure the one-shot
  discipline exists to prevent — and this plan has no shot to spend, which makes
  that temptation *cheaper*, not more legitimate.
- **One flushed progress line per unit of work** before anything is
  backgrounded — the repo's standing rule, and this is a multi-hour-shaped
  sweep.
- Verify with `python scripts/dev/testrun.py file <test file>`; `test-runner`
  subagent for the full suite. Green means `0 failed` **and** `0 xfailed`.

---

# Phase 1 — Define the measure

### Task 1: Density definition and bucketing

**Files:**
- Create: `scripts/backtest/measure_alert_density.py`
- Test: `tests/scripts/test_alert_density.py`

**Interfaces:**
- Produces: `density_by_day(trades: list[dict]) -> dict[str, int]`,
  `DENSITY_BUCKETS: tuple[tuple[str, int, int], ...]`,
  `bucket_trades(trades: list[dict]) -> list[dict]`.
- Consumes: nothing (pure functions over a trade list).

**The definition, fixed here and not revisited.** A trade's density is the
number of trades **opened on the same calendar date** across the whole universe,
counted in the same backtest run, including itself. Entry date comes from
`opened_at`. This is a proxy for alert count — not every alert becomes a trade —
and the results doc must say so in those words rather than calling it an alert
count.

**Buckets**, chosen to mirror the source's quiet/busy split while fitting a
75-ticker universe, and frozen before any data contact:

```python
DENSITY_BUCKETS = (("quiet", 1, 1), ("normal", 2, 3), ("busy", 4, 7), ("flood", 8, 10_000))
```

Every bucket is reported even at `n=0`, following `holding_period_split`'s rule
that the shape of the answer is the point.

- [ ] **Step 1: Write the failing test**

```python
"""Entry-day density and its buckets. Pure arithmetic over trade lists."""
from __future__ import annotations

import pytest

from scripts.backtest.measure_alert_density import (
    DENSITY_BUCKETS, bucket_trades, density_by_day,
)


def _t(date, r=0.0, ticker="AAA"):
    return {"opened_at": f"{date}T14:30:00", "ticker": ticker, "r_multiple": r}


def test_density_counts_trades_per_calendar_date():
    trades = [_t("2021-03-01"), _t("2021-03-01"), _t("2021-03-02")]
    assert density_by_day(trades) == {"2021-03-01": 2, "2021-03-02": 1}


def test_density_includes_the_trade_itself():
    assert density_by_day([_t("2021-03-01")]) == {"2021-03-01": 1}


def test_intraday_times_do_not_split_a_day():
    trades = [{"opened_at": "2021-03-01T09:31:00"}, {"opened_at": "2021-03-01T15:59:00"}]
    assert density_by_day(trades) == {"2021-03-01": 2}


def test_trades_without_opened_at_are_skipped_not_crashed():
    assert density_by_day([_t("2021-03-01"), {"ticker": "BBB"}]) == {"2021-03-01": 1}


def test_bucket_assignment_at_every_boundary():
    counts = {"quiet": 1, "normal": 3, "busy": 4, "flood": 8}
    for name, n in counts.items():
        trades = [_t("2021-03-01") for _ in range(n)]
        rows = {r["bucket"]: r for r in bucket_trades(trades)}
        assert rows[name]["n"] == n, f"{n} trades/day should land in {name}"


def test_every_bucket_reported_even_when_empty():
    rows = bucket_trades([_t("2021-03-01")])
    assert [r["bucket"] for r in rows] == [b[0] for b in DENSITY_BUCKETS]
    flood = [r for r in rows if r["bucket"] == "flood"][0]
    assert flood["n"] == 0
    assert flood["expectancy_r"] is None
    assert flood["win_rate"] is None


def test_expectancy_is_mean_r_within_the_bucket():
    trades = [_t("2021-03-01", 1.0), _t("2021-03-01", -1.0),
              _t("2021-03-05", 2.0)]
    rows = {r["bucket"]: r for r in bucket_trades(trades)}
    assert rows["normal"]["expectancy_r"] == pytest.approx(0.0)
    assert rows["quiet"]["expectancy_r"] == pytest.approx(2.0)


def test_empty_input_returns_empty():
    assert bucket_trades([]) == []
```

- [ ] **Step 2: Implement** the three functions. No I/O in any of them — the
  sweep wraps them in Task 2.
- [ ] **Step 3: Verify** — `python scripts/dev/testrun.py file tests/scripts/test_alert_density.py`

---

# Phase 2 — Measure

### Task 2: The TRAIN sweep

**Files:**
- Modify: `scripts/backtest/measure_alert_density.py` (CLI + sweep)

**Interfaces:**
- Consumes: the CSV cache from `scripts/data/fetch_backtest_data.py`, the
  existing replay path used by `scripts/backtest/run_backtest_range.py --train`.
- Produces: a JSON payload and a printed table.

- [ ] **Step 1:** Ensure the CSV cache exists.
- [ ] **Step 2:** Emit trades for TRAIN across the full universe and all ten
  horizons. Reuse `run_backtest_range.py`'s existing plumbing rather than
  writing a second replay — a divergent second harness is how two answers to one
  question get produced.
- [ ] **Step 3:** One flushed line per ticker-horizon:
  `print(f"[{n}/{total}] {ticker} {horizon} trades={k}", flush=True)`. **Confirm
  it prints before backgrounding anything** — the repo has already paid for that
  lesson once.
- [ ] **Step 4:** Report per bucket: `n`, `win_rate`, `expectancy_r`, `total_r`,
  and the share of all trades. Also report the **same table split by
  `source == "confluence"` vs the rest**, because confluence is the population
  the hypothesis is actually about and pooling it with the validated strategies
  would dilute exactly the signal being looked for.

---

### Task 3: Run it

- [ ] **Step 1:** Dispatch the `backtest-runner` subagent — this is a full
  75-ticker × 10-horizon pass and none of its per-ticker output should reach the
  controlling context.
- [ ] **Step 2:** The subagent keeps a plain-text progress file updated **at each
  real milestone**, including before it starts waiting on its own sweep. A report
  file written once at the start and again at the end leaves the controller
  unable to tell "still working" from "silently stalled" for hours.
- [ ] **Step 3:** Capture the JSON payload to
  `docs/superpowers/results/2026-08-XX-alert-density-train.json`.

---

# Phase 3 — Report

### Task 4: Write the finding

**Files:**
- Create: `docs/superpowers/results/2026-08-XX-alert-density-train.md`

- [ ] **Step 1:** The full table, both splits, every bucket including empty ones.
- [ ] **Step 2:** State the definition used ("trades opened on the same calendar
  date, a proxy for alert count — not every alert becomes a trade") and the
  bucket edges, before the numbers.
- [ ] **Step 3:** Honest observations. Three outcomes, all of them finished work:
  - **A monotone decline** in expectancy from `quiet` to `flood` on the
    confluence population is the hypothesis surviving. Name the successor spec
    it justifies (a daily alert cap or a density-aware confidence penalty) and
    stop. Do not draft the gate here.
  - **No gradient** closes the idea. Record it as a negative result and say so —
    "no density effect measurable on TRAIN" is the answer, not a stub.
  - **A gradient that reverses** (busy days better) is the most interesting
    outcome and the one most likely to be an artefact: check first whether busy
    days are simply trending days where every setup works, which would make
    density a proxy for regime and the finding a restatement of the regime
    filter. Say which of the two it is, or say that the data cannot distinguish
    them.
- [ ] **Step 4:** Cross-check against `data/scan_telemetry.jsonl` for the ~2
  weeks it covers, clearly labelled as anecdote with `n` stated. It cannot
  confirm or refute anything at that length; it is there to catch a gross
  definitional error, not to add evidence.

---

### Task 5: Close-out

- [ ] **Step 1:** Full suite via the `test-runner` subagent. `0 failed`, `0 xfailed`.
- [ ] **Step 2:** **No `VERSION.json` bump** — nothing in `swingbot/` changed.
  Confirm that by diffing the shipped package, not by memory.
- [ ] **Step 3:** Amend the `Edge:` header if the measurement came back null —
  a plan that predicted `expectancy` and measured nothing is the most useful
  record this repo can keep, and it belongs in the document, not in a commit
  message.
- [ ] **Step 4:** `git mv` this plan into `implemented/` (which holds finished,
  abandoned and null-result plans alike), remove the worktree, `git branch -d`
  (never `-D`; never a `backup*` or `stable-*` branch).

---

## Parallelisation

**Sequential throughout.** Task 2 consumes the bucketing contract Task 1
introduces; Task 3 runs what Task 2 builds; Task 4 reports what Task 3 produced;
Task 5 closes. There is no honest parallel group here, and saying so is worth as
much as a wide one — it stops the next session re-deriving the dependency graph
to find out.

The one genuine concurrency note: Task 3's sweep is long, and the controlling
session should be doing something else entirely while it runs — **not** another
task in this plan, and not another agent inside
`scripts/backtest/measure_alert_density.py`.
