Version: ui 1.8.0 · bot 1.3.2
Bump: bot patch (1.3.2 → 1.3.3) — two new sections in an existing digest and
two new analytics functions; no change to what the bot trades or alerts on.
Edge: none (integrity) — this ships no edge. It measures where R actually comes
from and how long losers are held, so the next expectancy/harvest plan is aimed
at something instead of guessed at. Say that plainly; do not let a diagnostic
borrow the language of an improvement.
Origin: EXTERNAL — HKUDS/Vibe-Trading, read 2026-08-22, now vendored
(untracked, gitignored) at `Vibe-Trading-main/` in this repo's root. The
disposition-ratio thresholds
(medium ≥ 1.2, high ≥ 1.5) are taken verbatim from
`agent/src/skills/trade-journal/SKILL.md`; the exit-reason table is modelled on
`agent/backtest/metrics.py:by_exit_reason_stats`. Those bands are that project's
numbers, calibrated on retail broker exports, **not** measured on this repo's
trades — treat a severity label as a prompt to look, never as a verdict.
**Revert lever:** none required. Two pure functions and two digest sections; no
flag, no gate, no change to what the bot trades or alerts on, so it cannot lower
trading performance. To back it out entirely, revert the commit.

# Closed-trade attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer two questions the record cannot currently answer. **Where does
R come from?** — `close_reason` is carried through five modules and aggregated
in none, so there is no table of R by exit reason (TP1 / TP2 / runner / stop /
breakeven-stop / scratch / timeout / reversed). **Are losers held longer than
winners?** — `_holding_days` exists and `holding_period_split` buckets by
duration, but nothing splits duration by outcome.

**Why the second one matters.** In a human that ratio is the disposition
effect, a bias. In a mechanical bot it is an exit-design defect: if losers are
systematically held longer than winners, the stop and the timeout are doing work
the target should be doing, and every extra day in a loser is R bleeding out.
Idea and thresholds are lifted from HKUDS/Vibe-Trading's `trade-journal` skill
(medium ≥ 1.2, high ≥ 1.5).

**Architecture:** Two pure functions in `analytics/metrics.py`, one helper
promoted out of `analytics/journal.py` to break a would-be import cycle, two
formatter blocks in `analytics/insights.py`. No new file in the live path, no
config Field, no gate.

**Tech Stack:** stdlib + the existing `analytics` package. No new dependency.

## Global Constraints

- **`metrics.py` must not import `journal.py`.** The dependency runs the other
  way today (`journal.py:15` imports `metrics`), so the shared reason-resolver
  moves *into* `metrics.py` and `journal.py` imports it back. Adding the reverse
  edge is a circular import, not a style question.
- **`insights.py` formats, it never computes.** Its module docstring commits to
  "Every number is delegated to metrics.py/calibration.py -- this module only
  formats, it never computes a stat from scratch." Both new sections obey that.
- **Empty buckets are reported, not dropped.** `holding_period_split`'s docstring
  states the rule: "the shape of the answer is the point". A reason with zero
  trades is a finding — it means an exit path never fires.
- **`None`, never `0`, for an undefined statistic.** A ratio over zero winners
  is unknown, and `0.0` would read as "losers exit instantly".
- **Discord's cap.** `insights.py` already chunks at
  `DISCORD_MESSAGE_LIMIT = 1900`; both new sections go through `_chunk`.
- **This plan spends no validation budget and opens no pre-registration.** If a
  number here suggests a change to trading behaviour, that is a *new* spec with
  its own shot — not an edit inside this plan.
- Verify with `python scripts/dev/testrun.py file <test file>` while iterating;
  `test-runner` subagent for the full suite. Green means `0 failed` **and** `0 xfailed`.

---

# Phase 1 — Shared reason vocabulary

### Task 1: Promote the reason resolver into `metrics.py`

**Files:**
- Modify: `swingbot/core/analytics/metrics.py`
- Modify: `swingbot/core/analytics/journal.py`
- Test: `tests/analytics/test_metrics_reasons.py`

**Interfaces:**
- Produces: `metrics.resolve_outcome(trade: dict) -> str`,
  `metrics.close_reason_text(trade: dict) -> str`, `metrics.EXIT_REASONS: tuple[str, ...]`.
- Consumes: nothing new.

`journal._resolve_outcome` (`journal.py:84`) and `journal._close_reason_text`
(`journal.py:140`) already encode the vocabulary correctly, including the
subtlety that a v2-manager close hides its real reason in `legs[-1]["reason"]`
while `status` stays the generic `"closed"`. Move them verbatim, keep
`journal.py` calling them through `metrics.`, and do not re-derive the logic —
this task is a move plus a canonical reason list, not a rewrite.

**The canonical list**, derived from what the code already emits
(`journal._RUNNER_SUBSTRINGS = ("runner_tp2", "runner_trail", "runner_be")`,
`reversal.py:127`'s `close_reason == "reversed"`, and the
`"scratch"`/`"timeout"` branches):

```python
EXIT_REASONS = ("tp1", "runner_tp2", "runner_trail", "runner_be",
                "stop", "scratch", "timeout", "reversed", "other")
```

`"other"` is deliberate and must never be silently dropped: a non-empty
`"other"` bucket means a reason string exists that this list does not know,
which is a finding about the data, not a formatting problem.

- [ ] **Step 1: Write the failing test**

```python
"""Exit-reason vocabulary shared by journal and metrics."""
from __future__ import annotations

import pytest

from swingbot.core.analytics import metrics


def test_win_and_loss_come_from_status():
    assert metrics.resolve_outcome({"status": "win"}) == "win"
    assert metrics.resolve_outcome({"status": "loss"}) == "loss"


def test_scratch_and_timeout_come_from_close_reason_under_generic_closed():
    assert metrics.resolve_outcome({"status": "closed", "close_reason": "scratch"}) == "scratch"
    assert metrics.resolve_outcome({"status": "closed", "close_reason": "Timeout"}) == "timeout"


def test_leg_reason_wins_over_close_reason():
    trade = {"status": "closed", "close_reason": "timeout",
             "legs": [{"reason": "scratch exit"}]}
    assert metrics.resolve_outcome(trade) == "scratch"


def test_unknown_reason_falls_back_to_status():
    assert metrics.resolve_outcome({"status": "closed", "close_reason": "???"}) == "closed"


def test_close_reason_text_prefers_last_leg():
    trade = {"close_reason": "stop", "legs": [{"reason": "runner_trail"}]}
    assert metrics.close_reason_text(trade) == "runner_trail"


def test_close_reason_text_is_lowercased_and_never_none():
    assert metrics.close_reason_text({"close_reason": None}) == ""
    assert metrics.close_reason_text({"close_reason": "STOP"}) == "stop"


def test_journal_still_resolves_identically():
    # The move must not change journal's behaviour.
    from swingbot.core.analytics import journal
    trade = {"status": "closed", "close_reason": "scratch"}
    assert journal._resolve_outcome(trade) == metrics.resolve_outcome(trade)


def test_exit_reasons_includes_other():
    assert "other" in metrics.EXIT_REASONS
```

- [ ] **Step 2: Move both helpers** into `metrics.py` as public names, leaving
  `journal._resolve_outcome = metrics.resolve_outcome` style delegation (or
  direct call sites) so `tests/analytics/test_journal.py` keeps passing untouched.
- [ ] **Step 3: Verify** — the new file **plus** `tests/analytics/test_journal.py`
  and `tests/analytics/test_journal_tags.py`. A green new test with a red journal
  test means the move changed behaviour.

---

# Phase 2 — The two statistics

### Task 2: R attributed by exit reason

**Files:**
- Modify: `swingbot/core/analytics/metrics.py`
- Test: `tests/analytics/test_metrics_exit_reasons.py`

**Interfaces:**
- Produces: `exit_reason_split(closed: list[dict]) -> list[dict]`, one row per
  `EXIT_REASONS` entry with `{reason, n, share_pct, total_r, avg_r, win_rate}`.
- Consumes: `metrics.r_multiple` (`metrics.py:96`), `metrics.resolve_outcome`.

**Why `total_r` and not just `avg_r`.** The question is where the R comes from,
and a reason with a great average over three trades contributes nothing. Both
columns, always, plus `n`.

- [ ] **Step 1: Write the failing test**

```python
"""R attributed by exit reason -- the table behind the scratch+timeout gate."""
from __future__ import annotations

import pytest

from swingbot.core.analytics import metrics


def _t(reason, r, status="closed"):
    return {"status": status, "close_reason": reason, "r_multiple": r}


def test_every_reason_is_reported_even_at_zero():
    rows = metrics.exit_reason_split([_t("stop", -1.0)])
    assert [r["reason"] for r in rows] == list(metrics.EXIT_REASONS)
    empty = [r for r in rows if r["reason"] == "timeout"][0]
    assert empty["n"] == 0
    assert empty["avg_r"] is None
    assert empty["win_rate"] is None
    assert empty["total_r"] == pytest.approx(0.0)


def test_total_and_average_r_per_reason():
    closed = [_t("stop", -1.0), _t("stop", -1.0), _t("timeout", -0.2)]
    rows = {r["reason"]: r for r in metrics.exit_reason_split(closed)}
    assert rows["stop"]["n"] == 2
    assert rows["stop"]["total_r"] == pytest.approx(-2.0)
    assert rows["stop"]["avg_r"] == pytest.approx(-1.0)
    assert rows["timeout"]["total_r"] == pytest.approx(-0.2)


def test_share_pct_sums_to_100_over_non_empty_reasons():
    closed = [_t("stop", -1.0), _t("timeout", -0.2), _t("scratch", 0.05)]
    rows = metrics.exit_reason_split(closed)
    assert sum(r["share_pct"] for r in rows) == pytest.approx(100.0)


def test_unknown_reason_lands_in_other_not_dropped():
    rows = {r["reason"]: r for r in metrics.exit_reason_split([_t("moon_exit", 0.4)])}
    assert rows["other"]["n"] == 1
    assert rows["other"]["total_r"] == pytest.approx(0.4)


def test_trade_with_no_r_multiple_counts_in_n_but_not_in_total_r():
    rows = {r["reason"]: r for r in metrics.exit_reason_split([_t("stop", None)])}
    assert rows["stop"]["n"] == 1
    assert rows["stop"]["total_r"] == pytest.approx(0.0)
    assert rows["stop"]["avg_r"] is None


def test_empty_input_returns_empty_list():
    assert metrics.exit_reason_split([]) == []
```

- [ ] **Step 2: Implement**, mirroring `holding_period_split`'s shape and its
  "every bucket reported even at n=0" rule.
- [ ] **Step 3: Verify** — `python scripts/dev/testrun.py file tests/analytics/test_metrics_exit_reasons.py`

---

### Task 3: Hold time split by outcome

**Files:**
- Modify: `swingbot/core/analytics/metrics.py`
- Test: `tests/analytics/test_metrics_hold_by_outcome.py`

**Interfaces:**
- Produces: `hold_by_outcome(closed: list[dict]) -> dict` —
  `{avg_winner_days, avg_loser_days, ratio, severity, n_winners, n_losers}`.
- Consumes: `metrics._holding_days` (`metrics.py:327`), `metrics.resolve_outcome`.

**Severity thresholds** (Vibe-Trading `trade-journal`, unchanged):
`ratio >= 1.5` → `"high"`, `>= 1.2` → `"medium"`, else `"low"`.

**`MIN_TRADES_FOR_RATIO = 5` already exists at `metrics.py:247`** and is the
right floor here too — reuse it rather than inventing a second minimum. Below
it on either side, `ratio` and `severity` are `None`.

- [ ] **Step 1: Write the failing test**

```python
"""Winner vs loser holding time -- the disposition ratio, applied to a bot."""
from __future__ import annotations

import pytest

from swingbot.core.analytics import metrics


def _t(status, days):
    return {"status": status,
            "opened_at": "2026-01-01T00:00:00",
            "closed_at": f"2026-01-{1 + int(days):02d}T00:00:00"}


def _many(status, days, k):
    return [_t(status, days) for _ in range(k)]


def test_ratio_is_losers_over_winners():
    closed = _many("win", 4, 5) + _many("loss", 8, 5)
    out = metrics.hold_by_outcome(closed)
    assert out["avg_winner_days"] == pytest.approx(4.0)
    assert out["avg_loser_days"] == pytest.approx(8.0)
    assert out["ratio"] == pytest.approx(2.0)


@pytest.mark.parametrize("w,l,expected", [(4, 8, "high"), (4, 5.2, "medium"), (4, 4, "low")])
def test_severity_bands(w, l, expected):
    closed = _many("win", w, 5) + _many("loss", l, 5)
    assert metrics.hold_by_outcome(closed)["severity"] == expected


def test_below_min_trades_ratio_is_none_not_zero():
    closed = _many("win", 4, 2) + _many("loss", 8, 2)
    out = metrics.hold_by_outcome(closed)
    assert out["ratio"] is None
    assert out["severity"] is None
    assert out["n_winners"] == 2


def test_no_winners_gives_none_rather_than_infinity():
    out = metrics.hold_by_outcome(_many("loss", 8, 6))
    assert out["ratio"] is None
    assert out["avg_winner_days"] is None


def test_scratches_and_timeouts_are_excluded_from_both_sides():
    # They are neither a winner nor a loser; folding them in would make the
    # ratio a statement about horizon length, not exit design.
    closed = _many("win", 4, 5) + _many("loss", 8, 5) + [
        {"status": "closed", "close_reason": "timeout",
         "opened_at": "2026-01-01T00:00:00", "closed_at": "2026-03-01T00:00:00"}]
    out = metrics.hold_by_outcome(closed)
    assert out["n_winners"] == 5 and out["n_losers"] == 5
    assert out["ratio"] == pytest.approx(2.0)


def test_trades_missing_timestamps_are_skipped():
    closed = _many("win", 4, 5) + _many("loss", 8, 5) + [{"status": "loss"}]
    assert metrics.hold_by_outcome(closed)["n_losers"] == 5


def test_empty_input_is_all_none():
    out = metrics.hold_by_outcome([])
    assert out["ratio"] is None and out["n_winners"] == 0
```

- [ ] **Step 2: Implement.**
- [ ] **Step 3: Verify.**

---

# Phase 3 — Surfacing

### Task 4: Two sections in the weekly digest

**Files:**
- Modify: `swingbot/core/analytics/insights.py`
- Test: `tests/analytics/test_insights_attribution.py`

**Interfaces:**
- Consumes: `metrics.exit_reason_split`, `metrics.hold_by_outcome`.
- Produces: no new public function — both render inside `weekly_digest`
  (`insights.py:52`), which already returns `list[str]` chunked for Discord.

Copy rules: state the ratio and its severity, never diagnose. "Losers held 2.0x
longer than winners (high)" is a measurement. "The bot is holding losers too
long" is a conclusion this plan has not earned — one ratio over one window is
not a validated finding, and the repo's convention is that a diagnostic says
what it measured.

- [ ] **Step 1: Write the failing test** — assert the digest contains the R-by-reason
  rows and the ratio line, that a `None` ratio renders as `n/a` rather than
  crashing or printing `0.0x`, that zero-`n` reasons still appear, and that the
  output stays within `DISCORD_MESSAGE_LIMIT` per chunk.
- [ ] **Step 2: Implement** as formatting only — no arithmetic in `insights.py`.
- [ ] **Step 3: Verify** — the new file plus `tests/analytics/test_insights.py`.

---

### Task 5: Close-out

- [ ] **Step 1:** Full suite via the `test-runner` subagent. `0 failed`, `0 xfailed`.
- [ ] **Step 2:** `VERSION.json` bot patch, then regenerate and commit
  `version_history.json` in the same commit — the local gate runs before the
  bump and structurally cannot catch a miss.
- [ ] **Step 3:** Run both statistics over the live closed-trade record and write
  the numbers into `docs/superpowers/results/2026-08-XX-closed-trade-attribution.md`.
  **This is the actual deliverable of the plan** — the code is the instrument;
  the measurement is the point. Record what the exit-reason table and the
  disposition ratio say, without proposing a fix in the same document.
- [ ] **Step 4:** `git mv` this plan into `implemented/`, remove the worktree,
  `git branch -d` (never `-D`; never a `backup*` or `stable-*` branch).

---

## Parallelisation

- **Sequential: Task 1 before everything.** It introduces
  `metrics.resolve_outcome`, which Tasks 2 and 3 both consume — a contract
  dependency, so they wait even though the files differ.
- **Group 1 (parallel): Task 2 and Task 3** — *only* if executed by one agent.
  They are independent in contract but **both edit
  `swingbot/core/analytics/metrics.py`**, and this working tree is shared: two
  agents on one file overwrite rather than merge. Two agents ⇒ run them
  sequentially. Their test files are genuinely disjoint.
- **Sequential:** Task 4 after both (it formats their output), Task 5 last.
