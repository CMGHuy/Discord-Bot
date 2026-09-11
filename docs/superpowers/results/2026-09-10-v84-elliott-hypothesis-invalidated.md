# v84 — Elliott Wave: hypothesis invalidated at design time

**Written 2026-09-10, Task R36. No code change, no backtest, no VALIDATION
run for this task.** This is the finding, not a measurement.

## Verdict

**NOT ATTEMPTED — hypothesis invalid at design time.** This is distinct
from "tested and failed": Elliott Wave was never measured under a v84
mechanism because the mechanism spec §4.8 proposed already ships in
production, and re-measuring it would have re-run a closed pre-registration
at a loosened threshold.

## What planning found (verified against source, 2026-09-10)

**(a) Both halves of the spec's proposed mechanism already ship**, in
`swingbot/core/market/entry_filters.py`:

- Wave-2 retracement validation: `DEFAULT_PARAMS["Elliott Wave"]` (line 763)
  sets `w2_min_retrace=0.382, w2_max_retrace=0.618, w2_max_duration_ratio=0.75`.
  `elliott_wave_entries` (line 775) applies these plus a wave-0 overlap check
  (`overlap = (lv["wave2"] - lv["wave0"]) * wave1_len <= 0`, line 808) —
  confirmed by direct read, not by trusting the spec's own claim.
- Volume confirmation: `VOL_OK_MULT = 0.9` (line 29), `vol_ok = Volume >=
  vol_avg20 * VOL_OK_MULT` (`compute_shared_gates`, lines 46-55), ANDed into
  both `bullish` and `bearish` (lines 834, 837).

**(b) The live retracement band (0.382–0.618) is *tighter* than the spec's
proposed band (0.382–0.786) — implementing the spec would have been a
loosening, not an addition.** 0.786 > 0.618.

**(c) These gates are the round-2 Elliott Wave rescue (Tasks 104/105) whose
VALIDATION shot is already spent.** Verified: `docs/superpowers/results/2026-07-rescue-elliott-train.md`
(TRAIN selection: N=117, WR=83.8%, ExpR=+0.094, the config now permanently
adopted in `DEFAULT_PARAMS`) and `docs/superpowers/results/2026-07-rescue-elliott-validation.md`
(Task 106's single VALIDATION-window run, 2024-01-01..2025-12-31: WR dropped
to 77.3%, verdict **FAIL — Elliott Wave remains WEAK**, no registry emit
since that step is conditional on PASS). `tests/market/test_rescue_elliott.py:7`'s
`GATED` fixture already uses `w2_min_retrace: 0.382, w2_max_retrace: 0.786`
— the exact band the spec called new, confirming this question has already
been tested, not merely implemented.

**(d) Implementing spec §4.8 as written would have re-run this closed
pre-registration at a looser threshold** — exactly the failure mode
`docs/claude/backtest-methodology.md` names explicitly: re-running the same
question with looser thresholds is what the one-shot VALIDATION budget
exists to prevent. This is why the work stops here rather than being
reshaped into a new measurement task.

**(e) Verdict: NOT ATTEMPTED — hypothesis invalid at design time**, recorded
here to satisfy this plan's Definition of Done item 1 ("every strategy has a
recorded verdict") without any measurement, since no measurement is valid to
run.

**(f) Reopening Elliott Wave needs a genuinely new mechanism and its own
fresh pre-registration** — not a re-run of the retracement band, the
duration ratio, the overlap check, or a volume gate (all four already
ship). None was invented here to fill the slot; per the spec's own words, "a
forced hypothesis is worse than an empty one."

## Adjacent fact for whoever writes that future pre-registration

`elliott_wave_entries` (`entry_filters.py:780-781`) hard-returns no entries
for every horizon except `4w` — `2w` pivots are noise, `>=2m` pivot
approximation degrades (documented in the function's own docstring).
`strategy_types.py:200-208` independently confirms no gated subset reached a
passing TRAIN config for this strategy. **Any future Elliott Wave mechanism
inherits this 4w-only volume ceiling regardless of its own merits** — it is
a structural property of the pivot-detection approach, not something a
different gate choice can route around.

## Why this got past the original research pass (recorded, not just fixed)

The research pass that produced spec §4.8 read only the raw detector
`indicators.elliott_wave3_entries` and never found
`entry_filters.elliott_wave_entries`, the adapter that actually wraps it and
applies the rescue gates. The subsequent symbol-verification pass confirmed
the raw detector *exists* — true — without asking whether the *proposed
change* was already implemented elsewhere in the call chain. Existence is
not the same question as absence-of-the-proposed-change; this is the
specific failure mode to watch for in any future strategy pre-registration.

## Spec status

`docs/superpowers/specs/2026-09-10-v84-strategy-rescue-v2-design.md` §4.8
already carries this finding in full (written during the plan's own
research/pre-registration pass, before this plan's implementation phase
began) — marked **"WITHDRAWN 2026-09-10, before any measurement"**, with the
original proposed text struck through and preserved in a collapsed
`<details>` block rather than deleted, per the spec's own convention that it
is "a record of what was believed at the time, not a document to quietly
rewrite." No further spec edit is needed for this task; this results doc is
the plan-execution-side record the spec's finding already anticipated.
