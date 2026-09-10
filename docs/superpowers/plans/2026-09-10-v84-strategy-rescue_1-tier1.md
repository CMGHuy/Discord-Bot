# Strategy Rescue v2 — Part 1: Tier 1 (Tasks R1–R14)

**Index:** `docs/superpowers/plans/2026-09-10-v84-strategy-rescue_0-index.md` —
read its Global Constraints first. They apply to every task here and are not
repeated.

**Spec:** `docs/superpowers/specs/2026-09-10-v84-strategy-rescue-v2-design.md`
§4.1 (EMA Crossover), §4.2 (Break & Retest), §4.3 (VWAP).

**Covers:** the three strategies whose rescue needs no new signal logic — one
needs no code change at all, two need only a horizon mask.

---

## Instrument note — READ BEFORE R1 (deviation from spec §2, with cause)

Spec §2 and §4.1–4.3 describe the free fold stage as
`validate_component.py --stage walkforward` / `gate_win_rate`. **That
instrument cannot be used for this campaign, and the plan uses a different one.
This was verified against the code, not assumed:**

1. `validate_component.py` **runs no backtest**. It consumes an arms JSON
   (`{"baseline": [ArmTrade...], "component": [ArmTrade...]}`) that "the
   component's own measurement script wrote" (its module docstring, line 25).
   No such measurement script exists for a per-strategy badge.
2. `gate_win_rate` (`backtest_wf.py:209`) scores **`delta_win_rate_pp` per
   fold** — a *delta between two arms*. It returns FAIL unless
   `sum(d > 0) >= 2`.
3. **For EMA Crossover there is no second arm.** Spec §4.1's whole point is that
   the mechanism is unchanged. Baseline and component would be identical, every
   delta would be exactly `0.0`, `sum(d > 0)` would be `0`, and the gate would
   return **FAIL by construction** — for a strategy that scores 61.8% WR.
4. A badge is an **absolute threshold on a strategy's own population**
   (`win_rate >= 50`, `expectancy_r > 0`), not a delta against a baseline it
   replaces. Scoring it with a delta gate is a category error.

**The instrument this part uses instead — the FOLD-STABILITY RULE.** It is
pre-registered here, before any fold number is seen, and every task below
refers to it by name:

> Run the three anchored fold-test years as custom windows —
> 2021-01-01..2021-12-31, 2022-01-01..2022-12-31, 2023-01-01..2023-12-31
> (`ANCHORED_FOLDS`, `backtest_wf.py:22-26`). **PASS** = the badge clauses
> (`win_rate >= 50` and `expectancy_r > 0`) hold in **at least 2 of the 3**
> fold years, each at `N >= 15` (the min_n `run_backtest_range.py` itself
> applies to a `--from/--to` CUSTOM window, line 342), **and** no fold year has
> `expectancy_r < -0.05` (the existing pre-registered `GATE_MAX_DEGRADATION_R`
> constant, `backtest_wf.py:30`). **Anything else is FAIL** — record the
> strategy closed in `results/`, spend no VALIDATION shot.

Nothing here loosens a threshold: the badge clauses are unchanged, the
≥2-of-3 shape and the −0.05R degradation ceiling are both lifted from existing
pre-registered constants. What changes is only that each fold is scored on the
strategy's **own** win rate instead of a delta against an arm that does not
exist.

**Do not build an arms harness for this part.** If a future task genuinely needs
a feature-vs-baseline comparison, that is a new pre-registration, not a
substitution made mid-plan.

**Also verified, and load-bearing for R5/R10:** `run_backtest` **does** apply
`STRATEGY_GATES` — `_vectorized_entries` calls `entries_for`
(`backtest.py:123-124`), which applies the mask at `entry_filters.py:146`. So
every measurement taken *after* a gate task lands is already gated, and the
pre-gate baseline numbers in the index's table cannot be reproduced afterward.
**Capture the baseline JSON before landing the gate**, which is why R5 and R10
each measure before they modify.

---

### Task R1: Pre-register the EMA Crossover rule

Nothing is measured in this task. The rule goes on disk **before** any fold
number is seen — that is what makes it a pre-registration rather than a
description of a result.

**Files:**
- Create: `docs/superpowers/results/2026-09-10-v84-ema-crossover-preregistration.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the pre-registration doc R3 and R4 append their verdicts to.

- [ ] **Step 1: Write the pre-registration doc**

```markdown
# v84 — EMA Crossover rescue: PRE-REGISTRATION

**Written 2026-09-10, before any fold-year or VALIDATION number was seen.**

**Edge:** none (integrity) — re-measurement of an unchanged mechanism.

## Hypothesis

EMA Crossover's `WEAK` badge (2026-07-18, WR 75.0% vs the then-current 80%
floor, N=36) was measured under the fixed per-strategy reward:risk table that
plan v31 deleted. Its live mechanism — the round-2 pullback entry
(`entry_mode="pullback"`, `pullback_max_bars=15`,
`entry_filters.py:217-228`) — is **unchanged**. Re-measured under current
arithmetic (`--exit-model v2 --scale-out`) its fresh TRAIN score is
**N=55, WR 61.8%, ExpR +0.494**, which clears every badge clause.

This is not a retry of the closed pullback-entry pre-registration. That verdict
was "this mechanism fails under the fixed-R:R arithmetic"; that arithmetic no
longer exists for any strategy. The question asked here — "does this unchanged
mechanism clear the badge floor under the arithmetic that now exists?" — has
never been asked.

## Pre-registered rule

1. **Fold stability:** the FOLD-STABILITY RULE (plan part 1, Instrument note) —
   badge clauses hold in >=2 of 3 fold years (2021/2022/2023) at N>=15 each,
   no fold year with expectancy_r < -0.05.
2. **If and only if (1) PASSES:** spend the single VALIDATION shot
   (2024-01-01..2025-12-31) and record its result as-is.
3. **If (1) FAILS:** EMA Crossover is recorded closed at this stage, stays
   `WEAK`, and **no VALIDATION run is performed**.

No configuration is tuned at any point. There is no grid, because there is no
parameter being chosen.

## Results

(Fold-stability table appended by Task R3; VALIDATION verdict by Task R4.)
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-ema-crossover-preregistration.md
git commit -m "docs(v84): pre-register EMA Crossover rescue rule"
```

---

### Task R2: Measure EMA Crossover fold stability

**Files:**
- Modify: none (measurement only)
- Output: `<scratchpad>/ema_fold_{2021,2022,2023}.json`

**Interfaces:**
- Consumes: the pre-registration from R1.
- Produces: three fold-year JSON summaries R3 scores.

- [ ] **Step 1: Dispatch the three fold runs to `backtest-runner`**

Do not run these inline — each sweeps 77 tickers × 10 horizons. Dispatch one
`backtest-runner` subagent with all three commands, instructing it to run them
as blocking calls and report `N`, `win_rate`, `expectancy_r` per fold year:

```bash
python scripts/backtest/run_backtest_range.py --from 2021-01-01 --to 2021-12-31 \
  --strategy "EMA Crossover" --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratchpad>/ema_fold_2021.json

python scripts/backtest/run_backtest_range.py --from 2022-01-01 --to 2022-12-31 \
  --strategy "EMA Crossover" --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratchpad>/ema_fold_2022.json

python scripts/backtest/run_backtest_range.py --from 2023-01-01 --to 2023-12-31 \
  --strategy "EMA Crossover" --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratchpad>/ema_fold_2023.json
```

Expected stdout shape per run (the `CUSTOM` label confirms the custom window
and its `min_n=15`):

```
== CUSTOM 2021-01-01 .. 2021-12-31 | pass: WR>=50, ExpR>0, N>=30, excl<=50% ==
Strategy                   N   Win%    ExpR  ...  PASS
EMA Crossover             ..   ....  ......  ...  ....
```

**Note the printed header still says `N>=30`** — that is the script's banner
text, while the CUSTOM window's actual `min_n` is 15. The FOLD-STABILITY RULE
governs, not the banner.

- [ ] **Step 2: Record the three rows verbatim**

Copy the `N`, `Win%`, `ExpR` for each fold year into a scratch note. Do not
score them yet — R3 does that against the rule, so the rule cannot be read in
light of the numbers.

---

### Task R3: Score EMA Crossover against the pre-registered rule

**Files:**
- Modify: `docs/superpowers/results/2026-09-10-v84-ema-crossover-preregistration.md`

**Interfaces:**
- Consumes: R2's three fold-year rows.
- Produces: a PASS/FAIL verdict that gates R4.

- [ ] **Step 1: Fill in the results table**

Append under `## Results`:

```markdown
### Fold stability (Task R2/R3)

| Fold year | N | Win rate | ExpR | Badge clauses hold? |
|---|---|---|---|---|
| 2021 | <N> | <WR>% | <ExpR> | yes/no |
| 2022 | <N> | <WR>% | <ExpR> | yes/no |
| 2023 | <N> | <WR>% | <ExpR> | yes/no |

**Fold-stability verdict: PASS / FAIL** — <count> of 3 fold years hold the
badge clauses at N>=15; worst fold expectancy_r = <value>.
```

- [ ] **Step 2: Apply the rule and branch**

- **PASS** (>=2 of 3 hold, no fold below −0.05R): continue to R4.
- **FAIL**: write the honest closing paragraph below, commit, and **skip R4
  entirely**. EMA Crossover stays `WEAK` and its VALIDATION shot stays unspent.

```markdown
**CLOSED at fold stability.** EMA Crossover's fresh TRAIN score did not hold
across fold-test years. The VALIDATION budget was NOT spent and remains
available. Per `docs/claude/backtest-methodology.md`, this closes the
question; reopening it needs a genuinely new mechanism, not a re-run.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-ema-crossover-preregistration.md
git commit -m "docs(v84): EMA Crossover fold-stability verdict"
```

---

### Task R4: Spend EMA Crossover's VALIDATION shot

**Run this task only if R3 returned PASS.** If R3 returned FAIL, this task does
not exist — skip to R5.

**Files:**
- Modify: `swingbot/core/backtesting/validation_registry.json` (machine-written)
- Modify: `docs/superpowers/results/2026-09-10-v84-ema-crossover-preregistration.md`

**Interfaces:**
- Consumes: R3's PASS verdict.
- Produces: EMA Crossover's final registry row.

- [ ] **Step 1: Run the one shot, via `backtest-runner`**

This is irreversible. It runs **once**, whatever it returns.

```bash
python scripts/backtest/run_backtest_range.py --validation --strategy "EMA Crossover" \
  --exit-model v2 --scale-out --pass-wr 50 \
  --emit-registry swingbot/core/backtesting/validation_registry.json \
  --run-date 2026-09-10 \
  --json <scratchpad>/ema_validation.json
```

Expected tail:

```
== VALIDATION 2024-01-01 .. 2025-12-31 | pass: WR>=50, ExpR>0, N>=30, excl<=50% ==
Strategy                   N   Win%    ExpR  ...  PASS
EMA Crossover             ..   ....  ......  ...  ....
Merged 1 records into swingbot/core/backtesting/validation_registry.json
```

- [ ] **Step 2: Verify the row landed as measured**

```bash
grep -A 9 '"strategy": "EMA Crossover"' swingbot/core/backtesting/validation_registry.json
```

Expected: `"window": "2024-01-01..2025-12-31"`, `"run_date": "2026-09-10"`, and
a `status` matching what the run printed. **If `status` is `WEAK`, that is the
result — do not re-run, do not adjust.**

- [ ] **Step 3: Append the verdict**

```markdown
### VALIDATION (Task R4) — one shot, spent 2026-09-10

| N | Win rate | ExpR | Badge |
|---|---|---|---|
| <N> | <WR>% | <ExpR> | VALIDATED / WEAK |

Recorded as-is. Budget for EMA Crossover is now spent.
```

- [ ] **Step 4: Commit**

```bash
git add swingbot/core/backtesting/validation_registry.json \
        docs/superpowers/results/2026-09-10-v84-ema-crossover-preregistration.md
git commit -m "feat(v84): EMA Crossover VALIDATION shot -- badge re-measured"
```

---

### Task R5: Capture the Break & Retest ungated baseline

**This must run BEFORE R6 lands the gate** — once `STRATEGY_GATES` has a
`"Break & Retest"` key, `run_backtest` applies it and the ungated population
cannot be measured again.

**Files:**
- Output: `<scratchpad>/br_baseline_train.json`

**Interfaces:**
- Consumes: nothing.
- Produces: the ungated per-horizon TRAIN table R6's plateau check reads.

- [ ] **Step 1: Run the ungated TRAIN sweep via `backtest-runner`**

```bash
python scripts/backtest/run_backtest_range.py --train --strategy "Break & Retest" \
  --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratchpad>/br_baseline_train.json
```

Expected: a pooled `FAIL` row near WR 48.0% N=298, followed by the
`-- per strategy x horizon --` table with all ten horizons. Record that table
in full — it is the plateau check's only input.

- [ ] **Step 2: Copy the per-horizon table into the pre-registration draft**

Keep it verbatim in a scratch note for R6. Do not select a horizon subset yet.

---

### Task R6: Pre-register Break & Retest, including the plateau check

**Files:**
- Create: `docs/superpowers/results/2026-09-10-v84-break-retest-preregistration.md`

**Interfaces:**
- Consumes: R5's per-horizon table.
- Produces: the pre-registered subset and rule R7–R9 are scored against.

- [ ] **Step 1: Write the pre-registration**

```markdown
# v84 — Break & Retest rescue: PRE-REGISTRATION

**Written 2026-09-10, before the gated TRAIN, fold or VALIDATION runs.**

**Edge:** expectancy — removes a negative-expectancy sub-population.

## Hypothesis

Break & Retest fails pooled (TRAIN WR 48.0%, N=298) but is **bimodal by
horizon, not uniformly weak**: 2m/3m/4m clear the floor (53.1%/57.1%/51.4%,
ExpR +0.38/+0.32/+0.21) while 6m is the only negative-ExpR cell (27.8%,
-0.157) and 7m/8m/2w sit at 42.9-46.7%. The structural claim: a
breakout-retest works while the break is fresh and decays as the level ages.

Restricting to `{2m, 3m, 4m}` scores **N=105, WR 53.3%, ExpR ~+0.31** on the
population already measured.

**Genuinely new:** no closed pre-registration touches per-strategy horizon
scoping. `STRATEGY_GATES` has no `"Break & Retest"` key today — this ADDS one;
the masking machinery (`entry_filters.entries_for`, line 146) already exists
and is exercised by seven other strategies.

## The overfit risk, stated plainly

The qualifying subset was **identified from the same TRAIN table that scores
it**. The plateau check below exists precisely to catch that, and it is
disqualifying, not advisory.

## Pre-registered rule

1. **Plateau (Stage 1), computed from Task R5's ungated per-horizon table —
   no new run:** pool `{2m,3m,4m}` and its four neighbours-by-one-horizon:
   `{2m,3m}`, `{3m,4m}`, `{2m,3m,4m,5m}`, `{2m,3m,4m,4w}`. **PASS** = the
   chosen `{2m,3m,4m}` clears WR>=50 with N>=30 **and at least two of those
   four neighbours also clear WR>=50 with N>=30**. A chosen subset that is an
   isolated peak among its neighbours is a spike, not a plateau, and is
   **REJECTED here** — no gate is landed and no further run happens.
2. **Gated TRAIN (Task R8):** with the gate live, pooled WR>=50, ExpR>0,
   N>=30, excl<=50%.
3. **Fold stability (Task R8):** the FOLD-STABILITY RULE.
4. **VALIDATION (Task R9):** one shot, only if 1-3 all pass.

Any failure closes Break & Retest at that stage with no VALIDATION spent.

## Results

(Plateau table appended by Task R6; TRAIN and folds by R8; VALIDATION by R9.)
```

- [ ] **Step 2: Compute the plateau table and append it**

From `<scratchpad>/br_baseline_train.json`, pool each subset (sum `N`, recompute
weighted win rate and expectancy). Append:

```markdown
### Plateau check (Task R6)

| Subset | N | Win rate | Clears WR>=50, N>=30? |
|---|---|---|---|
| {2m,3m,4m} (chosen) | 105 | 53.3% | yes |
| {2m,3m} | <N> | <WR>% | yes/no |
| {3m,4m} | <N> | <WR>% | yes/no |
| {2m,3m,4m,5m} | <N> | <WR>% | yes/no |
| {2m,3m,4m,4w} | <N> | <WR>% | yes/no |

**Plateau verdict: PASS / REJECTED** — <count> of 4 neighbours also clear.
```

- [ ] **Step 3: Branch on the plateau verdict**

- **PASS**: continue to R7.
- **REJECTED**: append the closing note below, commit, and **skip R7–R9**.

```markdown
**CLOSED at the plateau check.** `{2m,3m,4m}` is an isolated peak among its
neighbouring horizon subsets, which is the signature of fitting the TRAIN
table rather than a structural horizon effect. No gate landed, no VALIDATION
spent.
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-break-retest-preregistration.md
git commit -m "docs(v84): pre-register Break & Retest horizon gate + plateau check"
```

---

### Task R7: Add the Break & Retest horizon gate

**Run only if R6's plateau verdict was PASS.**

**Files:**
- Modify: `swingbot/core/market/strategy_types.py:200-219`
- Test: `tests/market/test_entry_filters.py`

**Interfaces:**
- Consumes: R6's PASS verdict.
- Produces: `STRATEGY_GATES["Break & Retest"] == {"horizons": ("2m","3m","4m")}`,
  read by `entry_filters.entries_for` at line 146.

- [ ] **Step 1: Write the failing test**

Append to `tests/market/test_entry_filters.py`:

```python
def test_break_retest_gated_to_short_horizons(monkeypatch, uptrend_df):
    """v84 R7: Break & Retest fires only at 2m/3m/4m. The 6m cell was the
    only negative-expectancy horizon on TRAIN (27.8% WR, -0.157R)."""
    import swingbot.core.market.entry_filters as ef
    from swingbot.core.market.strategy_types import STRATEGY_GATES

    assert STRATEGY_GATES["Break & Retest"]["horizons"] == ("2m", "3m", "4m")

    fired = pd.Series(True, index=uptrend_df.index)
    monkeypatch.setitem(ef.ENTRY_FUNCS, "Break & Retest",
                        lambda df, hk, params=None: (fired.copy(), fired.copy()))

    bull_3m, bear_3m = ef.entries_for("Break & Retest", uptrend_df, "3m")
    assert bull_3m.all() and bear_3m.all()      # inside the gate, both directions

    bull_6m, bear_6m = ef.entries_for("Break & Retest", uptrend_df, "6m")
    assert not bull_6m.any() and not bear_6m.any()   # outside -> fully masked
```

- [ ] **Step 2: Run it and verify it fails**

```bash
python -m pytest tests/market/test_entry_filters.py::test_break_retest_gated_to_short_horizons -v
```

Expected: FAIL with `KeyError: 'Break & Retest'` — the key does not exist yet.

- [ ] **Step 3: Add the gate entry and correct the stale comment**

In `swingbot/core/market/strategy_types.py`, replace the comment block at lines
200-203 and add the new key. The existing comment claims EMA Crossover and
Elliott Wave "could not be gated to a passing train config" citing pre-v31
numbers — it now contradicts the campaign's own findings, so it is corrected
rather than left standing:

```python
# EMA Crossover and Elliott Wave are left ungated deliberately. The pre-v31
# numbers that justified this (EMA Crossover bullish+4w reaching only N=28;
# Elliott Wave firing only on 4w at WR=74.1 ExpR=-0.001) were measured against
# the fixed per-strategy reward:risk table plan v31 deleted -- see v84
# (docs/superpowers/specs/2026-09-10-v84-strategy-rescue-v2-design.md). Under
# current arithmetic EMA Crossover scores WR 61.8% ExpR +0.494 ungated, so no
# gate is needed; Elliott Wave's rescue is a wave-structure change, not a mask.
# NOTE: every WR/ExpR figure in the per-key comments below is likewise pre-v31
# and stale. Only the "Break & Retest" entry was derived under current
# arithmetic.
STRATEGY_GATES: dict[str, dict] = {
    # bullish-only: N=286 WR=81.8 ExpR=+0.106 excl=27% (train, PRE-v31 -- stale)
    "Fibonacci": {"directions": ("bullish",)},
    # bullish-only: N=608 WR=85.2 ExpR=+0.140 excl=28% (train, PRE-v31 -- stale)
    "RSI": {"directions": ("bullish",)},
    # bullish-only: N=259 WR=81.1 ExpR=+0.071 excl=25% (train, PRE-v31 -- stale)
    "MA Ribbon": {"directions": ("bullish",)},
    # bullish + {4w,6m,7m,8m,9m}: N=139 WR=82.0 ExpR=+0.086 excl=20%
    # (train, PRE-v31 -- stale; v84 R10 re-derives this to 4w-only)
    "VWAP": {"directions": ("bullish",), "horizons": ("4w", "6m", "7m", "8m", "9m")},
    # bullish + {2m,3m}: N=273 WR=80.6 ExpR=+0.060 excl=32% (train, PRE-v31 -- stale)
    "Support/Resistance": {"directions": ("bullish",), "horizons": ("2m", "3m")},
    # bullish + {3m,4m,7m,8m,9m}: N=145 WR=83.4 ExpR=+0.094 excl=26% (train, PRE-v31 -- stale)
    "MACD": {"directions": ("bullish",), "horizons": ("3m", "4m", "7m", "8m", "9m")},
    # bullish + {7m}: N=73 WR=82.2 ExpR=+0.106 excl=30% (train, PRE-v31 -- stale)
    "Volume Profile": {"directions": ("bullish",), "horizons": ("7m",)},
    # v84 R7, CURRENT arithmetic (v2 + scale-out): the pooled TRAIN row fails
    # (WR 48.0 N=298) but splits bimodally by horizon -- 2m/3m/4m clear the
    # floor (53.1/57.1/51.4) while 6m is the only negative-ExpR cell
    # (27.8, -0.157). Gated subset: N=105 WR=53.3 ExpR=+0.31. Both directions
    # kept -- only the horizon axis was pre-registered.
    "Break & Retest": {"horizons": ("2m", "3m", "4m")},
}
```

- [ ] **Step 4: Run the test and the shape test together**

```bash
python -m pytest tests/market/test_entry_filters.py::test_break_retest_gated_to_short_horizons \
                 tests/market/test_entry_filters.py::test_strategy_gates_shape -v
```

Expected: both PASS. `test_strategy_gates_shape` asserts every gate's keys are a
subset of `{"directions", "horizons"}` — the new entry has only `horizons`.

- [ ] **Step 5: Run the entry-filter file once**

```bash
python scripts/dev/testrun.py file tests/market/test_entry_filters.py
```

Expected: one-line verdict, `0 failed`. **Not** the full suite — that is R41.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/strategy_types.py tests/market/test_entry_filters.py
git commit -m "feat(v84): gate Break & Retest to 2m/3m/4m horizons"
```

---

### Task R8: Break & Retest gated TRAIN + fold stability

**Files:**
- Modify: `docs/superpowers/results/2026-09-10-v84-break-retest-preregistration.md`

**Interfaces:**
- Consumes: the landed gate from R7.
- Produces: PASS/FAIL that gates R9.

- [ ] **Step 1: Dispatch the gated TRAIN run and three fold runs to `backtest-runner`**

```bash
python scripts/backtest/run_backtest_range.py --train --strategy "Break & Retest" \
  --exit-model v2 --scale-out --pass-wr 50 --json <scratchpad>/br_gated_train.json

python scripts/backtest/run_backtest_range.py --from 2021-01-01 --to 2021-12-31 \
  --strategy "Break & Retest" --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratchpad>/br_fold_2021.json

python scripts/backtest/run_backtest_range.py --from 2022-01-01 --to 2022-12-31 \
  --strategy "Break & Retest" --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratchpad>/br_fold_2022.json

python scripts/backtest/run_backtest_range.py --from 2023-01-01 --to 2023-12-31 \
  --strategy "Break & Retest" --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratchpad>/br_fold_2023.json
```

Expected in the gated TRAIN output: the per-horizon table now lists **only**
2m/3m/4m — the gate is live and the other seven horizons produce no trades. If
any other horizon still appears, the gate is not being applied; stop and fix
before proceeding.

- [ ] **Step 2: Append both tables and score them**

```markdown
### Gated TRAIN (Task R8)

| N | Win rate | ExpR | excl% | Clears rule 2? |
|---|---|---|---|---|
| <N> | <WR>% | <ExpR> | <excl>% | yes/no |

### Fold stability (Task R8)

| Fold year | N | Win rate | ExpR | Badge clauses hold? |
|---|---|---|---|---|
| 2021 | <N> | <WR>% | <ExpR> | yes/no |
| 2022 | <N> | <WR>% | <ExpR> | yes/no |
| 2023 | <N> | <WR>% | <ExpR> | yes/no |

**Verdict: PASS / FAIL**
```

- [ ] **Step 3: Branch**

- **PASS** (rule 2 clears **and** the FOLD-STABILITY RULE passes): continue to R9.
- **FAIL**: append the closing note, commit, skip R9. **Leave the gate landed** —
  it removes a measured negative-expectancy population (6m at −0.157R) and is
  an improvement even where the badge does not flip. State that explicitly:

```markdown
**CLOSED before VALIDATION.** The gate stays landed: it removes a horizon
population measured negative on TRAIN, which is worth keeping independently of
the badge outcome. The VALIDATION budget was NOT spent and remains available.
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-break-retest-preregistration.md
git commit -m "docs(v84): Break & Retest gated TRAIN + fold verdict"
```

---

### Task R9: Spend Break & Retest's VALIDATION shot

**Run only if R8 returned PASS.**

**Files:**
- Modify: `swingbot/core/backtesting/validation_registry.json` (machine-written)
- Modify: `docs/superpowers/results/2026-09-10-v84-break-retest-preregistration.md`

**Interfaces:**
- Consumes: R8's PASS verdict.
- Produces: Break & Retest's final registry row.

- [ ] **Step 1: Run the one shot, via `backtest-runner`**

```bash
python scripts/backtest/run_backtest_range.py --validation --strategy "Break & Retest" \
  --exit-model v2 --scale-out --pass-wr 50 \
  --emit-registry swingbot/core/backtesting/validation_registry.json \
  --run-date 2026-09-10 \
  --json <scratchpad>/br_validation.json
```

- [ ] **Step 2: Verify the row**

```bash
grep -A 9 '"strategy": "Break & Retest"' swingbot/core/backtesting/validation_registry.json
```

Expected: `"window": "2024-01-01..2025-12-31"`, `"run_date": "2026-09-10"`.
Whatever `status` says is the result.

- [ ] **Step 3: Append the verdict and commit**

```bash
git add swingbot/core/backtesting/validation_registry.json \
        docs/superpowers/results/2026-09-10-v84-break-retest-preregistration.md
git commit -m "feat(v84): Break & Retest VALIDATION shot"
```

---

### Task R10: Capture the VWAP ungated-at-4w baseline

**Must run BEFORE R11 narrows the gate** — afterwards the 6m/7m/8m/9m rows
cannot be reproduced.

**Files:**
- Output: `<scratchpad>/vwap_baseline_train.json`

**Interfaces:**
- Consumes: nothing.
- Produces: the five-horizon TRAIN table R11 scores.

- [ ] **Step 1: Run the current-gate TRAIN sweep via `backtest-runner`**

```bash
python scripts/backtest/run_backtest_range.py --train --strategy "VWAP" \
  --exit-model v2 --scale-out --pass-wr 50 --json <scratchpad>/vwap_baseline_train.json
```

Expected per-horizon table covering exactly the five currently-gated horizons
(`4w,6m,7m,8m,9m`), near: 4w N=68 WR 52.9% ExpR +0.335; 6m 35.7% −0.078;
7m 40.0%; 8m 38.5%; 9m 11.1% (N=9). The 2w/2m/3m/4m/5m/6m rows are absent
because the live gate already excludes them.

---

### Task R11: Pre-register and narrow the VWAP gate to 4w

**Files:**
- Create: `docs/superpowers/results/2026-09-10-v84-vwap-preregistration.md`
- Modify: `swingbot/core/market/strategy_types.py:212`
- Test: `tests/market/test_entry_filters.py`

**Interfaces:**
- Consumes: R10's per-horizon table.
- Produces: `STRATEGY_GATES["VWAP"]["horizons"] == ("4w",)`.

- [ ] **Step 1: Write the pre-registration**

```markdown
# v84 — VWAP rescue: PRE-REGISTRATION

**Written 2026-09-10, before the narrowed TRAIN, fold or VALIDATION runs.**

**Edge:** expectancy — removes a negative-expectancy sub-population.

## Hypothesis

VWAP's live gate (`strategy_types.py:212`, bullish + `{4w,6m,7m,8m,9m}`) was
hand-calibrated against the pre-v31 fixed reward:risk table and never
re-derived -- its own source comment cites WR=82.0, a number from the deleted
80%-floor era. Under current arithmetic the pooled row fails (44.5%) but the
failure is entirely the four long horizons: 4w alone scores **N=68, WR 52.9%,
ExpR +0.335**, while 9m sits at 11.1% (N=9, -0.519R).

Narrowing the gate to bullish + `{4w}` is a re-derivation of an existing,
admittedly-stale mask -- not a new mechanism.

## Pre-registered rule

1. **TRAIN (Task R12):** with the narrowed gate, WR>=50, ExpR>0, N>=30,
   excl<=50%.
2. **Fold stability (Task R12):** the FOLD-STABILITY RULE.
3. **VALIDATION (Task R13):** one shot, only if 1-2 pass.
4. **Fallback (Task R14) -- runs ONLY if rule 1 or 2 FAILS:** the
   slope-persistence gate (spec 4.3), tested on the same 4w population. If the
   fallback's own TRAIN + fold check fails, VWAP is closed permanently with no
   VALIDATION spent.

N=68 at 4w on TRAIN is the whole sample; at VALIDATION the badge floor is
N>=15. If the narrowed TRAIN N falls below 30, rule 1 fails and the fallback
is what gets tested -- shrinking N to reach a win rate is explicitly not
allowed.
```

- [ ] **Step 2: Write the failing test**

```python
def test_vwap_gated_to_4w_only(monkeypatch, uptrend_df):
    """v84 R11: VWAP narrowed to 4w. 6m/7m/8m/9m were all sub-floor under
    current arithmetic (35.7/40.0/38.5/11.1), 9m at -0.519R."""
    import swingbot.core.market.entry_filters as ef
    from swingbot.core.market.strategy_types import STRATEGY_GATES

    assert STRATEGY_GATES["VWAP"]["horizons"] == ("4w",)
    assert STRATEGY_GATES["VWAP"]["directions"] == ("bullish",)

    fired = pd.Series(True, index=uptrend_df.index)
    monkeypatch.setitem(ef.ENTRY_FUNCS, "VWAP",
                        lambda df, hk, params=None: (fired.copy(), fired.copy()))

    bull_4w, bear_4w = ef.entries_for("VWAP", uptrend_df, "4w")
    assert bull_4w.all()                 # inside the gate
    assert not bear_4w.any()             # bearish still masked by directions

    bull_9m, bear_9m = ef.entries_for("VWAP", uptrend_df, "9m")
    assert not bull_9m.any() and not bear_9m.any()
```

- [ ] **Step 3: Run it and verify it fails**

```bash
python -m pytest tests/market/test_entry_filters.py::test_vwap_gated_to_4w_only -v
```

Expected: FAIL — `assert ('4w', '6m', '7m', '8m', '9m') == ('4w',)`.

- [ ] **Step 4: Narrow the gate**

In `swingbot/core/market/strategy_types.py`, replace the `"VWAP"` entry:

```python
    # v84 R11, CURRENT arithmetic (v2 + scale-out): the pre-v31 five-horizon
    # mask was never re-derived after v31 replaced the fixed reward:risk table.
    # 4w alone: N=68 WR=52.9 ExpR=+0.335. The dropped horizons were 6m 35.7
    # (-0.078), 7m 40.0, 8m 38.5, 9m 11.1 (N=9, -0.519).
    "VWAP": {"directions": ("bullish",), "horizons": ("4w",)},
```

- [ ] **Step 5: Verify it passes**

```bash
python -m pytest tests/market/test_entry_filters.py::test_vwap_gated_to_4w_only -v
python scripts/dev/testrun.py file tests/market/test_entry_filters.py
```

Expected: PASS, then `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/strategy_types.py tests/market/test_entry_filters.py \
        docs/superpowers/results/2026-09-10-v84-vwap-preregistration.md
git commit -m "feat(v84): narrow VWAP gate to 4w -- re-derive stale pre-v31 mask"
```

---

### Task R12: VWAP narrowed TRAIN + fold stability

**Files:**
- Modify: `docs/superpowers/results/2026-09-10-v84-vwap-preregistration.md`

**Interfaces:**
- Consumes: the narrowed gate from R11.
- Produces: PASS/FAIL gating R13 vs R14.

- [ ] **Step 1: Dispatch TRAIN + three folds to `backtest-runner`**

```bash
python scripts/backtest/run_backtest_range.py --train --strategy "VWAP" \
  --exit-model v2 --scale-out --pass-wr 50 --json <scratchpad>/vwap_gated_train.json

python scripts/backtest/run_backtest_range.py --from 2021-01-01 --to 2021-12-31 \
  --strategy "VWAP" --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratchpad>/vwap_fold_2021.json

python scripts/backtest/run_backtest_range.py --from 2022-01-01 --to 2022-12-31 \
  --strategy "VWAP" --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratchpad>/vwap_fold_2022.json

python scripts/backtest/run_backtest_range.py --from 2023-01-01 --to 2023-12-31 \
  --strategy "VWAP" --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratchpad>/vwap_fold_2023.json
```

Expected: the per-horizon table now shows a single `4w` row.

- [ ] **Step 2: Append both tables, score against rules 1 and 2, and branch**

- Rule 1 **and** rule 2 pass → continue to **R13**.
- Either fails → skip R13, go to **R14** (the fallback).

Record which branch was taken and why, verbatim.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-vwap-preregistration.md
git commit -m "docs(v84): VWAP narrowed TRAIN + fold verdict"
```

---

### Task R13: Spend VWAP's VALIDATION shot

**Run only if R12 passed both rules.**

**Files:**
- Modify: `swingbot/core/backtesting/validation_registry.json` (machine-written)
- Modify: `docs/superpowers/results/2026-09-10-v84-vwap-preregistration.md`

**Interfaces:**
- Consumes: R12's PASS.
- Produces: VWAP's final registry row. **Also produces the skip-signal for R14.**

- [ ] **Step 1: Run the one shot, via `backtest-runner`**

```bash
python scripts/backtest/run_backtest_range.py --validation --strategy "VWAP" \
  --exit-model v2 --scale-out --pass-wr 50 \
  --emit-registry swingbot/core/backtesting/validation_registry.json \
  --run-date 2026-09-10 \
  --json <scratchpad>/vwap_validation.json
```

- [ ] **Step 2: Verify the row and append the verdict**

```bash
grep -A 9 '"strategy": "VWAP"' swingbot/core/backtesting/validation_registry.json
```

- [ ] **Step 3: Record that R14 is now skipped**

Append verbatim — this is the explicit skip-gate R14 checks:

```markdown
**R14 (slope-persistence fallback) is SKIPPED.** It exists only for the branch
where the 4w re-gate failed its free stages. VWAP's one VALIDATION shot is now
spent; testing a second mechanism afterwards would be a second look at the same
window for the same strategy.
```

- [ ] **Step 4: Commit**

```bash
git add swingbot/core/backtesting/validation_registry.json \
        docs/superpowers/results/2026-09-10-v84-vwap-preregistration.md
git commit -m "feat(v84): VWAP VALIDATION shot -- 4w-only gate"
```

---

### Task R14: VWAP slope-persistence fallback — CONDITIONAL

> **SKIP THIS TASK ENTIRELY IF R13 RAN.** Check the pre-registration doc for the
> "R14 ... is SKIPPED" line before starting. This task exists only for the
> branch where R12 failed and R13 never happened. Running it after a spent
> VALIDATION shot would be a second look at the same window for the same
> strategy — exactly what the one-shot budget forbids.

**Files:**
- Modify: `swingbot/core/market/entry_filters.py:283-313`
- Test: `tests/market/test_entry_filters.py`
- Modify: `docs/superpowers/results/2026-09-10-v84-vwap-preregistration.md`

**Interfaces:**
- Consumes: R12's FAIL verdict.
- Produces: `DEFAULT_PARAMS["VWAP"]["min_vwap_slope_atr"]`, consumed by
  `vwap_entries`.

- [ ] **Step 1: Write the failing test**

```python
def test_vwap_slope_persistence_gate_suppresses_flat_vwap():
    """v84 R14 fallback: a reclaim while VWAP itself is flat is filtered.
    Current vwap_up is a magnitude-free 3-bar direction check, so a
    barely-rising VWAP passes it."""
    from swingbot.core.market.entry_filters import vwap_entries
    from tests.conftest import make_trend_df

    flat = make_trend_df(400, +0.005)     # near-flat: VWAP slope ~ 0
    on, _ = vwap_entries(flat, "4w", params={"min_vwap_slope_atr": 0.25})
    off, _ = vwap_entries(flat, "4w", params={"min_vwap_slope_atr": None})
    assert off.sum() >= on.sum()
    assert on.sum() < off.sum()           # the gate must actually bite here

    strong = make_trend_df(400, +0.30)    # steep trend: VWAP clearly rising
    s_on, _ = vwap_entries(strong, "4w", params={"min_vwap_slope_atr": 0.25})
    s_off, _ = vwap_entries(strong, "4w", params={"min_vwap_slope_atr": None})
    assert s_on.sum() == s_off.sum()      # unaffected where VWAP genuinely trends


def test_vwap_slope_gate_off_is_byte_identical():
    from swingbot.core.market.entry_filters import vwap_entries
    from tests.conftest import make_trend_df

    df = make_trend_df(300, +0.2)
    a, b = vwap_entries(df, "4w")
    c, d = vwap_entries(df, "4w", params={"min_vwap_slope_atr": None})
    assert (a == c).all() and (b == d).all()
```

- [ ] **Step 2: Run and verify both fail**

```bash
python -m pytest tests/market/test_entry_filters.py -k vwap_slope -v
```

Expected: FAIL — `min_vwap_slope_atr` is not a recognised param, so the gate
never bites and `on.sum() < off.sum()` is false.

- [ ] **Step 3: Implement the gate**

Replace `DEFAULT_PARAMS["VWAP"]` and add the slope term inside `vwap_entries`:

```python
DEFAULT_PARAMS["VWAP"] = {
    "ext_pct": 1.5, "hold_bars_2w": 3, "hold_bars_other": 2,
    # v84 R14 fallback. None = gate off (the shipped default until its own
    # TRAIN + fold check passes). Units: VWAP's 8-bar rise per ATR.
    "min_vwap_slope_atr": None,
}
```

Inside `vwap_entries`, after the existing `vwap_up`/`vwap_down` lines
(currently 301-302), add:

```python
    slope_min = p.get("min_vwap_slope_atr")
    if slope_min is not None:
        atr14 = g["atr14"]
        slope = (vwap - vwap.shift(8)) / atr14.replace(0, np.nan)
        vwap_up = vwap_up & (slope >= slope_min)
        vwap_down = vwap_down & (slope <= -slope_min)
```

`g["atr14"]` is available — `compute_shared_gates` computes `atr14 = atr(df, 14)`
and returns it in its dict alongside `atr_floor`/`atr_calm` (verified
2026-09-10, `entry_filters.py:39-58`). **Use `g["atr14"]`, never a locally
recomputed ATR** — two ATR definitions that disagree is a correctness bug, not
a style choice.

- [ ] **Step 4: Verify the tests pass**

```bash
python -m pytest tests/market/test_entry_filters.py -k vwap_slope -v
python scripts/dev/testrun.py file tests/market/test_entry_filters.py
```

- [ ] **Step 5: Grid the gate on TRAIN, via `backtest-runner`**

The param is off by default, so a grid needs `tune_strategy.py`:

```bash
python scripts/backtest/tune_strategy.py --strategy "VWAP" \
  --grid min_vwap_slope_atr=0.15,0.25,0.35 --exit-model v2 --scale-out
```

**Pre-registered rule:** a config qualifies at WR>=50, ExpR>0, N>=30,
excl<=50% **and must sit in a plateau** — at least two of the three grid points
qualifying. A single qualifying point between two failures is a spike and is
rejected. 0 or 1 qualifying ⇒ VWAP is closed permanently, no VALIDATION spent.

- [ ] **Step 6: Record the verdict and commit**

If the grid passes, run the FOLD-STABILITY RULE on the winning config before
any VALIDATION shot; if it fails, append:

```markdown
**CLOSED.** Neither the 4w re-gate nor the slope-persistence fallback cleared
its free stages. VWAP stays WEAK; its VALIDATION budget was never spent and
remains available. Reopening needs a genuinely new mechanism.
```

```bash
git add swingbot/core/market/entry_filters.py tests/market/test_entry_filters.py \
        docs/superpowers/results/2026-09-10-v84-vwap-preregistration.md
git commit -m "feat(v84): VWAP slope-persistence fallback gate"
```

---

## Part 1 exit state

Before moving to Part 2, each of the three strategies must be in exactly one of:

- **Rescued** — a fresh `run_date: 2026-09-10` registry row from a VALIDATION
  shot, and a completed pre-registration doc.
- **Closed** — a pre-registration doc whose final section states the stage it
  failed at and that no VALIDATION was spent.

No strategy may be left mid-branch. Task R42 collects these docs; R44
reconciles the registry.
