# unified-plan-engine-v2 — reconciling the skipped staged-rollout gates (G217)

**Context:** `unified-plan-engine-v2` Tasks 85, 88, 89 §3-4, 90, 91, 94 were a
staged rollout (manual smoke → ≥5 shadow sessions → cutover → ≥5 clean
sessions → enable scale-out/manager → 1 clean week → delete legacy paths)
with live-verification gates at each step. Per
`docs/superpowers/results/2026-07-v2-final-report.md:88-119`, the user
explicitly chose to skip the staged rollout and deploy straight to
production by flipping the three config defaults in commit `8aef8e5`
(2026-07-18). This doc checks, task by task, whether real production data
accumulated since then can answer the same question retroactively.

## What's available to check against

Checked this local working tree's `data/` directory (2026-07-31):

- `data/trades.json` — `[]`, empty.
- `data/journal.json` — does not exist.
- `data/scan_telemetry.jsonl` — 1908 lines, 2026-07-27 through 2026-07-31,
  but every entry scans **1 ticker** per line (`"tickers": 1`), matching
  individual test-suite scan calls, not real watchlist scans (this repo's
  README/CLAUDE.md describe the live bot scanning the whole watchlist,
  75+ tickers, per session). This is dev/test-generated telemetry from
  this repo's own working tree, not the deployed bot's production data.
- No `data/shadow_plans.jsonl` exists anywhere in history or on disk —
  confirms shadow mode never actually ran (consistent with the final
  report: deployment skipped straight from `off` to `on`).

**Conclusion up front: this local repo cannot answer any of these
retroactively.** Per `DOCKER.md`/`DEPLOY_HETZNER.md`, the bot runs as a
Docker container on a remote Hetzner host with its own `data/` volume —
that is where real production trades/journal/telemetry would live, and
this session has no SSH/deployment access to it. The distinction below is
between "the evidence can never exist" (Task 88 — shadow mode was skipped
entirely, so there is nothing to retrieve, from anywhere, ever) and "the
evidence may exist on the remote deployment but is inaccessible from
here" (Tasks 85, 89 §3-4, 90, 94).

## Task 85 — Phase 6 checkpoint (manual smoke, pre-rollout)

**What it verified:** full suite + `make check` green, and a human manually
ran the bot against a test guild confirming badges/quality/trigger wording
render correctly with no layout overflow.

**Retroactively answerable?** The full-suite/`make check` half is trivially
re-checkable today (and was, repeatedly, throughout this session — green).
The manual-rendering half is not a data question at all — it needs a human
looking at real Discord embeds, which no amount of historical log data
substitutes for.

**Waiver:** Full-suite/`make check` re-verified green as of this doc
(2026-07-31). The manual rendering smoke was never performed and cannot be
reconstructed after the fact — it requires a human to look at the bot live.
**Substitute evidence (weaker):** the bot has been running these embed
code paths continuously since 2026-07-18 without a bug report against
badge/quality/trigger rendering surfacing in this repo's commit history —
absence of a fix commit is weaker than a positive human confirmation, but
it is what's available.

## Task 88 — Run shadow for ≥5 sessions (operational gate)

**What it verified:** `shadow_parity_report.py` over ≥5 real shadow-mode
sessions showing v2 plans track legacy scenario numbers closely, v2 emits
plans for ≥80% of items legacy alerts on, and zero `INVARIANT VIOLATION`
lines.

**Retroactively answerable?** **No, not even in principle.** This is the
one checkpoint the final report already flags: the deployment went
straight from `PLAN_ENGINE_V2=off` to `=on`, so shadow mode never ran for
even one session anywhere, ever. `shadow_parity_report.py` reads
`shadow_plans.jsonl`, which was never written — not lost, never generated.

**Waiver (permanent, not just "data unavailable today"):** This checkpoint
cannot be answered from history under any circumstances, because its
input data structurally never existed. **Substitute evidence (much
weaker):** `plan_numbers_for_display` (the single funnel function gating
which numbers reach the display path, Task 89) is covered by
`tests/test_cutover.py` and has run in production, gating every live alert,
since 2026-07-18 with no reported invariant-style bugs (stop on wrong side
of entry, etc.) surfacing as incident commits. This is not the same
evidence as a parity report — it's evidence the code hasn't visibly broken,
not evidence the v2 numbers are *close to* the legacy numbers they replaced.

## Task 89 §3-4 — Cutover watch session + commit

**What it verified (§3-4 only — §1-2's failing-test-first `plan_numbers_for_display`
implementation genuinely happened and is tested):** a human watching one
live test-guild session after `PLAN_ENGINE_V2=on` to confirm v2-priced
plans render sanely before wider rollout.

**Retroactively answerable?** No — same as Task 85's manual half, this
needs a human watching a live session at the time, not reconstructable
from logs after the fact.

**Waiver:** Never performed as specified. **Substitute evidence (weaker):**
the code this step was gating (`plan_numbers_for_display`) has been the
live display-number funnel for every alert since 2026-07-18, is unit
tested (`tests/test_cutover.py::test_flag_on_display_numbers_come_from_plan`,
`test_flag_shadow_display_numbers_stay_legacy`), and no revert or
emergency-fix commit targeting it appears in `git log` since `8aef8e5`.

## Task 90 — Enable scale-out + intraday manager (operational)

**What it verified:** after ≥5 clean Task-89 sessions, `SCALE_OUT_ENABLED`
and `INTRADAY_MANAGER_V2` flipped on, then a live test-guild session
confirmed a fill alert, a BE move, and (market-permitting) a TP1 partial
all appear correctly, `!plans` reflects live state, and `trades.json`
grows legs.

**Retroactively answerable?** In principle yes — `trades.json` growing legs
correctly is a data-shape question a script could check. In practice, no:
this local repo's `data/trades.json` is `[]` (empty), so there is no trade
history here to check against. The real answer, if it exists, is in the
remote deployment's `data/trades.json`/`data/journal.json`, which this
session cannot reach.

**Waiver:** Cannot be answered from this environment. **Substitute
evidence (weaker):** `SCALE_OUT_ENABLED`/`INTRADAY_MANAGER_V2` have
defaulted to `true` since `8aef8e5` (2026-07-18) and the scale-out/manager
code paths are covered by their own unit test suites (`tests/test_*scale*`,
`tests/test_trade_monitor*`), currently green as part of every full-suite
run in this session (one known pre-existing, wall-clock-dependent failure
excepted — see `CLAUDE.md`). No revert or emergency-fix commit targeting
scale-out/manager logic appears in `git log` since the cutover.
**Recommendation:** if a real answer is wanted, pull `data/trades.json`
and `data/journal.json` from the production deployment and re-run this
check — this doc explicitly does not fabricate a pass against data that
isn't there.

## Task 91 — Delete legacy paths

**Status per the final report: genuinely not done, not silently
substituted.** `swingbot/core/trade_plan.py` and `backtest.py`'s v1 exit
loop are still present and reachable via `exit_model="v1"` — confirmed
still on disk in this session (`swingbot/core/trade_plan.py` exists,
`tests/test_trade_plan.py` exists). This is not a checkpoint to
retroactively verify; it's an action that was correctly deferred pending
Task 90's "one clean week" precondition, which (per Task 90's own waiver
above) has never been confirmed either. **No waiver needed — nothing to
reconcile here**, this task's undone status is already honestly tracked.

## Task 94 — Phase 7 checkpoint

**What it verified:** full suite + `make check` green, live bot healthy
≥1 week, registry/docs/reports all committed.

**Retroactively answerable?** The suite/`make check` half: yes, and it's
green today. The "live bot healthy ≥1 week" half needs the same production
telemetry Task 90 needs and this session doesn't have.

**Waiver:** Full-suite/`make check` re-verified green (2026-07-31). "Live
bot healthy ≥1 week" cannot be confirmed from this environment.
**Substitute evidence (weaker):** the bot has been running v2-on in
production for 13 days (2026-07-18 to 2026-07-31) by wall-clock alone,
per the cutover commit date and today's date, with no rollback commit
(`PLAN_ENGINE_V2` flipped back to `off`/`shadow`) anywhere in `git log`
since `8aef8e5`.

## Summary

| Task | In-principle answerable from data? | Answered here? | Substitute evidence strength |
|---|---|---|---|
| 85 | Partial (suite: yes; manual smoke: no) | Suite only | Weak (no bug-report commits) |
| 88 | **No, structurally** — shadow log never generated | No | Weakest — different question entirely |
| 89 §3-4 | No (needs live human observation) | No | Weak (tested code, no revert commits) |
| 90 | Yes, in principle (needs remote `data/`) | No — data inaccessible here | Weak (flags on 13 days, tests green, no revert) |
| 91 | N/A — action task, correctly still pending | N/A | N/A |
| 94 | Partial (suite: yes; live-health: needs remote data) | Suite only | Weak (13 days wall-clock, no rollback) |

No checkpoint here is fabricated as a pass. Where real production data
could answer the question but isn't accessible from this session, that is
stated plainly rather than approximated, per this task's own instructions.
