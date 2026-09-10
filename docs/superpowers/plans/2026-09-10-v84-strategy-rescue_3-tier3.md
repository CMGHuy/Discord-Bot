# Strategy Rescue v2 — Part 3: Tier 3 (Fibonacci, Elliott Wave)

Header, Global Constraints, shared command forms and baseline numbers live in
`2026-09-10-v84-strategy-rescue_0-index.md`. **Read that first** — every task
below inherits it (`--pass-wr 50`, `--exit-model v2 --scale-out`, one
VALIDATION shot per strategy, plateau-not-spike, record failures as-is).

Spec: `docs/superpowers/specs/2026-09-10-v84-strategy-rescue-v2-design.md`
§4.7 (Fibonacci) and §4.8 (Elliott Wave).

Tier 3 is the honestly speculative tier. Fibonacci is 14.6pp short of the floor
and Elliott Wave 17.3pp. **A clean, well-recorded failure in this part is a
success**, not an error branch — the funnel exists so that a wide gap dies for
free on TRAIN instead of expensively on the one-shot window.

---

## STOP — Elliott Wave's specced mechanism is invalid (read before R36)

**Spec §4.8 cannot be implemented as written. Both halves of its proposed
mechanism already ship in production, and implementing the spec literally
would loosen a closed pre-registration.** Verified 2026-09-10 against source:

| Spec §4.8 claims | Actual state |
|---|---|
| "no retracement-depth validation … today any `p2 > p0` passes, including a 5% or 95% retrace" | **False for the live path.** True only of the raw detector `indicators.elliott_wave3_entries` (`indicators.py:253`). The strategy's real entry function is `entry_filters.elliott_wave_entries` (`entry_filters.py:703`), which applies `w2_min_retrace=0.382`, `w2_max_retrace=0.618`, `w2_max_duration_ratio=0.75` and a wave-0 overlap check (`entry_filters.py:719-746`), plus a separate `depth_min=0.30`/`depth_max=0.80` band (`:748-754`). |
| "add wave-2 retracement validity, band 0.382–0.786" | **Already implemented, and TIGHTER.** Live band is 0.382–**0.618**. The spec's 0.786 is a *loosening*. |
| "add volume confirmation: breakout bar volume > its 20-bar average" | **Already implemented.** `compute_shared_gates` computes `vol_ok = Volume >= vol_avg20 * VOL_OK_MULT` (`entry_filters.py:46,55`, `VOL_OK_MULT = 0.9` at `:29`), and it is already ANDed into both the bullish and bearish series (`:762`, `:765`). |
| "never implemented … no closed pre-registration touches wave-structure validity" | **False.** These gates ARE the round-2 Elliott rescue (Tasks 104/105), whose selected config is recorded in `DEFAULT_PARAMS["Elliott Wave"]` with the comment "Adopted here permanently; Task 106 spends the single VALIDATION-window look against this exact config, no retuning after." Records: `results/2026-07-rescue-elliott-train.md`, `results/2026-07-rescue-elliott-validation.md`. Existing tests: `tests/market/test_rescue_elliott.py` — whose `GATED` fixture at line 7 already uses **`w2_min_retrace: 0.382, w2_max_retrace: 0.786`**, the exact band the spec calls new. |

**Why this stops the work rather than reshaping it.** Widening 0.618 → 0.786
re-runs a closed pre-registration's own question at a looser threshold. That is
the one operation `docs/claude/backtest-methodology.md` names explicitly:
*"Re-running the same question with looser thresholds is the exact failure the
one-shot budget exists to prevent."* Elliott Wave's VALIDATION shot is already
spent. A rescue needs a **genuinely new mechanism**, and choosing one is a
pre-registration decision for the human partner — not something a plan-writing
pass invents to keep a task slot filled.

**Consequence:** R36 records this finding. **R37–R40 are deliberately
unallocated** pending a new pre-registration in the spec. No measurement task
for Elliott Wave appears below, and none may be added without that.

---

# Phase 3A — Fibonacci (R31–R35)

Spec §4.7. Verified sound: `fib_target_candidates` (`targets.py:179-205`) builds
`[swing_high, swing_low] + retracements` then appends only
`for ratio in (1.272, 1.618)` (`:202-204`). There is no 1.0 extension, so a
bullish plan entering mid-retracement sees candidates at `swing_high` and then
nothing until `swing_high + 1.272*diff` — a >3x jump in distance. The 1.0
extension (`swing_high + 1.0*diff`, the standard measured-move projection) sits
in that gap.

`select_structural_target` (`targets.py:10-57`) takes the **nearest** qualifying
candidate, so adding a strictly-closer real candidate is monotonic: it can only
pull a target nearer or leave it unchanged. Never further.

**Pre-registered rule (verbatim from spec §4.7):** *TRAIN win_rate ≥ 50%,
`expectancy_r > 0`, N ≥ 30, excl ≤ 50% with the 1.0 candidate added and nothing
else changed.*

**Gate declaration, required by methodology.** Adding a target candidate moves
geometry by construction, so this change is **NOT eligible for the six-clause
acceptance funnel** — clause 3 (geometry lock: median planned RR and mean win R
may not fall more than 2%) would reject it by design, and rightly so. It is
judged on the **badge threshold** instead (`win_rate >= 50`, `expectancy_r > 0`,
`N >= 30` train / `N >= 15` validation, scratches+timeouts ≤ 50%) — a
strategy-cell measurement of Fibonacci's own population, not a feature-vs-baseline
effect. `backtest-methodology.md` requires a geometry-moving change to *name the
gate it is using* in its own pre-registration; **R33 and R35 must both state this
in the results doc they write.** Expected trade: win rate up, some ExpR spent.
The +0.232 baseline cushion is what funds it, and `expectancy_r > 0` is the hard
floor that stops the trade from going too far.

### Task R31: Config flag + 1.0 extension candidate

**Files:**
- Modify: `swingbot/config.py` (new `Field` near the Trade Filters block ~`:162`; add attr to `_SEARCH_CLASSES["searchable"]` ~`:896`)
- Modify: `.env.example` (sync test `tests/test_env_example_sync.py` enforces this)
- Modify: `swingbot/core/planning/targets.py:179-205` (`fib_target_candidates`)
- Test: `tests/planning/test_plan_engine_sizing.py`

**Interfaces:**
- Consumes: `config.FIB_TARGET_1_0_EXTENSION: bool` (new, default `False`)
- Produces: `fib_target_candidates(df, index, h, entry) -> list[float]` — **signature unchanged**; returns two extra prices when the flag is on. All existing callers (`builders.py`, `backtest.py`, `plan_engine.py:45`) keep working untouched.

**Why a config flag and not a plain edit:** the fold harness's only two-arm
mechanism is `wf_run.py --component-json '{"FLAG": true}'`, which overrides
**`swingbot.config` fields**. A change hard-coded into `fib_target_candidates`
would have no baseline arm and could not be fold-measured at all. Default `False`
also keeps this inert in production until its VALIDATION shot passes — the same
discipline `DEAD_CAT_BOUNCE_VETO` shipped under.

- [ ] **Step 1: Write the failing test**

Add to `tests/planning/test_plan_engine_sizing.py`:

```python
def test_fib_candidates_1_0_extension_flag(df, monkeypatch):
    """The 1.0 extension fills the gap between swing_high and the 1.272
    extension. Flag off = byte-identical to today; flag on = exactly two
    extra prices, one per side."""
    from swingbot import config
    hk = "4w"
    entry, _ = _entry_atr(df, atr_series(df))
    h = HORIZONS[hk]

    monkeypatch.setattr(config, "FIB_TARGET_1_0_EXTENSION", False)
    off = fib_target_candidates(df, I, h, entry)

    monkeypatch.setattr(config, "FIB_TARGET_1_0_EXTENSION", True)
    on = fib_target_candidates(df, I, h, entry)

    assert len(on) == len(off) + 2
    lookback = h["fib_lookback"]
    hist = df.iloc[:I + 1]
    swing_high = float(hist["High"].iloc[-lookback:].max())
    swing_low = float(hist["Low"].iloc[-lookback:].min())
    diff = swing_high - swing_low
    added = [c for c in on if not any(abs(c - o) < 1e-9 for o in off)]
    assert sorted(added) == sorted([swing_high + diff, swing_low - diff])
```

Note: `atr_series` is a fixture in this file; if it is not importable as a
callable here, use the existing `atr_series` fixture argument instead of calling
it — match whatever the neighbouring tests in this file do.

- [ ] **Step 2: Run it and confirm it fails**

```bash
python -m pytest tests/planning/test_plan_engine_sizing.py::test_fib_candidates_1_0_extension_flag -v
```

Expected: FAIL — `AttributeError: module 'swingbot.config' has no attribute 'FIB_TARGET_1_0_EXTENSION'`.

- [ ] **Step 3: Add the config field**

In `swingbot/config.py`, alongside the other Trade Filters fields:

```python
    Field("FIB_TARGET_1_0_EXTENSION", "FIB_TARGET_1_0_EXTENSION", "Trade Filters & Risk",
          "Fibonacci 1.0 extension as a target candidate",
          type="checkbox", default="false",
          help="Adds the 1.0 (measured-move) extension of the anchoring swing to the "
               "Fibonacci strategy's target candidates, filling the gap between the swing "
               "high/low and the 1.272 extension. Ships OFF: it is a pre-registered "
               "measurement (v84), not a demonstrated edge, and flips on only if its one "
               "VALIDATION shot passes."),
```

Then add the attr to the `searchable` set in `_SEARCH_CLASSES` (~`:896`):

```python
        "MAX_ALERTS_PER_SCAN", "DATA_DRIVEN_STOPS_ENABLED",
        "DEAD_CAT_BOUNCE_VETO", "DCB_DECLINE_PCT", "DCB_GAP_REQUIRED",
        "DCB_VOLUME_RATIO", "FIB_TARGET_1_0_EXTENSION",
```

- [ ] **Step 4: Sync `.env.example`**

Add near the other Trade Filters entries:

```
FIB_TARGET_1_0_EXTENSION=false
```

- [ ] **Step 5: Wire the candidate**

In `swingbot/core/planning/targets.py`, `fib_target_candidates`, replace the
extension loop (`:202-204`):

```python
    from swingbot import config
    ratios = (1.0, 1.272, 1.618) if config.FIB_TARGET_1_0_EXTENSION else (1.272, 1.618)
    for ratio in ratios:
        candidates.append(swing_high + ratio * diff)
        candidates.append(swing_low - ratio * diff)
    return candidates
```

Update the docstring's second sentence to read "…and the 1.272/1.618 extensions
of the same swing (plus the 1.0 extension when `FIB_TARGET_1_0_EXTENSION` is
on)."

- [ ] **Step 6: Run the tests**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_engine_sizing.py
python scripts/dev/testrun.py file tests/test_env_example_sync.py
python scripts/dev/testrun.py file tests/test_config_flags.py
```

Expected: all pass, `0 failed`.

- [ ] **Step 7: Commit**

```bash
git add swingbot/config.py .env.example swingbot/core/planning/targets.py tests/planning/test_plan_engine_sizing.py
git commit -m "feat(v84): FIB_TARGET_1_0_EXTENSION flag, off by default"
```

### Task R32: Arms-measurement harness for the Fibonacci flag

**Files:**
- Create: `scripts/backtest/measure_fib_extension.py`
- Test: `tests/scripts/test_measure_fib_extension.py`

**Interfaces:**
- Consumes: `config.FIB_TARGET_1_0_EXTENSION`; `swingbot.core.backtesting.acceptance.ArmTrade(ticker, entry_date, outcome, r_multiple, planned_rr)`
- Produces: a JSON file in the shape `validate_component.py` requires — `{"baseline": [...], "component": [...]}` for `--stage mde`, and `{"folds": [{"test_year": "2021", "baseline": [...], "component": [...]}, ...]}` for `--stage walkforward`.

**Why this task exists (verified tooling gap).** `validate_component.py` does
**not** run backtests — its docstring says *"Arms come from a JSON file the
component's own measurement script wrote."* And `wf_run.py --json` writes a
*summary* dict (`{"overrides", "result", "gate"}`), not the per-trade `ArmTrade`
lists the funnel consumes. Nothing in `scripts/backtest/` currently emits arms
for a per-strategy target change. This is the same gap v34 and v68 filled with
purpose-built scripts (`measure_rs_gate_effect.py`, `measure_dcb_veto.py`) — follow
those two as the house pattern. **Do not invent flags on the existing scripts.**

- [ ] **Step 1: Read both precedents before writing anything**

```bash
sed -n '1,80p' scripts/backtest/measure_dcb_veto.py
sed -n '1,80p' scripts/backtest/measure_rs_gate_effect.py
```

Copy their structure: argparse surface, per-arm replay, `ArmTrade` construction,
JSON emission. Match whichever one already produces `folds` output if either does.

- [ ] **Step 2: Write the failing test**

Create `tests/scripts/test_measure_fib_extension.py`:

```python
import json
import subprocess
import sys


def test_emits_both_arms(tmp_path):
    out = tmp_path / "arms.json"
    r = subprocess.run(
        [sys.executable, "scripts/backtest/measure_fib_extension.py",
         "--stage", "mde", "--tickers", "AAPL", "--out", str(out)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    arms = json.loads(out.read_text())
    assert set(arms) == {"baseline", "component"}
    assert arms["baseline"] and arms["component"]
    for t in arms["baseline"] + arms["component"]:
        assert set(t) >= {"ticker", "entry_date", "outcome", "r_multiple", "planned_rr"}
        assert t["outcome"] in {"win", "loss", "scratch", "timeout", "not_triggered"}
```

- [ ] **Step 3: Run it and confirm it fails**

```bash
python -m pytest tests/scripts/test_measure_fib_extension.py -v
```

Expected: FAIL — script does not exist (non-zero returncode, `can't open file`).

- [ ] **Step 4: Implement the harness**

Requirements it must satisfy — write these into the script's own docstring:
- Runs the Fibonacci strategy only, over the cached universe, with
  `--exit-model v2 --scale-out` economics, once per arm.
- Baseline arm: `config.FIB_TARGET_1_0_EXTENSION = False`. Component arm:
  `True`. Set it via the same override mechanism `wf_run.py` uses
  (`_default_run`'s `over` dict), not by mutating a module global mid-replay.
- `--stage mde` emits `{"baseline", "component"}`; `--stage walkforward` emits
  `{"folds": [...]}` with **exactly three** folds whose `test_year` values are
  distinct — `validate_component.py` REFUSES otherwise (`:116`). Take the fold
  windows from `backtest_wf.ANCHORED_FOLDS`, do not hard-code years.
- Prints flushed per-ticker progress (`[i/N] TICKER`) — this run takes minutes.

- [ ] **Step 5: Verify it passes**

```bash
python -m pytest tests/scripts/test_measure_fib_extension.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/measure_fib_extension.py tests/scripts/test_measure_fib_extension.py
git commit -m "test(v84): arms harness for the Fibonacci 1.0 extension"
```

### Task R33: TRAIN measurement — the pre-registered badge rule

**Files:**
- Create: `docs/superpowers/results/2026-09-10-v84-fib-extension-train.md`

**Interfaces:**
- Consumes: `FIB_TARGET_1_0_EXTENSION` from R31
- Produces: the PASS/FAIL that decides whether R34 runs at all

- [ ] **Step 1: Write the pre-registration section FIRST, before running**

Create the results doc with the rule and the gate declaration written down
*before* any number exists. It must contain, in this order: the pre-registered
rule quoted from spec §4.7; the explicit statement that this is judged on the
**badge threshold, not the six-clause funnel**, because the change moves geometry
and clause 3 would reject it by design; and the baseline row
(`N=246, WR=35.4%, ExpR=+0.232`). Commit this before Step 2.

- [ ] **Step 2: Dispatch the measurement to `backtest-runner`**

Two runs, flag off then on. Give the subagent this exact pair and tell it to
block on each (no `run_in_background`, no check-and-return):

```bash
FIB_TARGET_1_0_EXTENSION=false python scripts/backtest/run_backtest_range.py \
  --train --strategy "Fibonacci" --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratch>/fib_train_off.json

FIB_TARGET_1_0_EXTENSION=true python scripts/backtest/run_backtest_range.py \
  --train --strategy "Fibonacci" --exit-model v2 --scale-out --pass-wr 50 \
  --json <scratch>/fib_train_on.json
```

- [ ] **Step 3: Record the result as-is**

Append the two rows (N, Win%, ExpR, Excl%, PASS/FAIL) and the per-horizon table
to the results doc. **Record whatever came back.** If the flag-on arm fails the
rule, write that down and say the component is closed — do not adjust the ratio,
do not try 0.786 or 1.5, do not re-run. A wider target set that fails is a
finished measurement.

- [ ] **Step 4: Decide the branch, in writing**

- Flag-on clears `WR ≥ 50, ExpR > 0, N ≥ 30, excl ≤ 50%` → proceed to R34.
- Otherwise → **stop here.** Mark Fibonacci CLOSED in the doc, skip R34 and R35,
  and carry the negative result into R42/R45. The VALIDATION shot stays unspent.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-fib-extension-train.md
git commit -m "docs(v84): Fibonacci 1.0 extension TRAIN result"
```

### Task R34: Stage 2 walkforward (free, repeatable)

**Only run if R33 passed.**

**Files:**
- Create: `docs/superpowers/results/2026-09-10-v84-fib-extension-walkforward.md`

- [ ] **Step 1: Produce the three-fold arms file**

```bash
python scripts/backtest/measure_fib_extension.py --stage walkforward \
  --out <scratch>/fib_folds.json
```

Expected: three folds, distinct `test_year`s drawn from `ANCHORED_FOLDS`.

- [ ] **Step 2: Run the pre-registered gate**

```bash
python scripts/backtest/validate_component.py --stage walkforward \
  --arms <scratch>/fib_folds.json \
  --title "v84 Fibonacci 1.0 extension" \
  --window "fold-test 2021/2022/2023" \
  --out-md docs/superpowers/results/2026-09-10-v84-fib-extension-walkforward.md
```

Expected output: one `fold <year>: dWR=<±x.xx>pp n=<N>` line per fold, then
`PASS` or `FAIL -- stage 2 walkforward win-rate consistency gate`. Exit code 0 on
PASS, 1 on FAIL/REFUSED. The rule is `gate_win_rate`: ≥2 of 3 folds improving,
no fold worse than the degradation ceiling, per-fold N ≥ 30.

- [ ] **Step 3: Branch, in writing**

PASS → R35 may spend the shot. FAIL or REFUSED → Fibonacci is CLOSED at stage 2,
**no VALIDATION run**, budget intact. Record it and move on.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-fib-extension-walkforward.md
git commit -m "docs(v84): Fibonacci 1.0 extension walkforward verdict"
```

### Task R35: VALIDATION — one shot, ever

**Only run if BOTH R33 and R34 passed.** This is irreversible.

**Files:**
- Create: `docs/superpowers/results/2026-09-10-v84-fib-extension-validation.md`
- Modify: `swingbot/core/backtesting/validation_registry.json` (via `--emit-registry` only)
- Modify: `swingbot/config.py` (default flip, only on PASS)

- [ ] **Step 1: Write the pre-registration and arm the once-guard**

Create the validation results doc containing the rule and the gate declaration
(badge threshold, not the six-clause funnel — same wording as R33) **with no
`## Result` section yet**. `wf_run.py --once-guard` refuses to run against a file
that already has one, which is the mechanism that makes "one shot" real.

- [ ] **Step 2: Confirm no VALIDATION row exists yet for this component**

```bash
git log --oneline -- docs/superpowers/results/2026-09-10-v84-fib-extension-validation.md
grep -n '"strategy": "Fibonacci"' -A 8 swingbot/core/backtesting/validation_registry.json
```

Expected: the current row is the 2026-09-10 TRAIN-window `WEAK` row. If any
2024–25-window Fibonacci row dated after 2026-09-10 already exists, **stop** —
the shot has been spent and this task must not run.

- [ ] **Step 3: Spend the shot (dispatch to `backtest-runner`, blocking)**

```bash
FIB_TARGET_1_0_EXTENSION=true python scripts/backtest/run_backtest_range.py \
  --validation --strategy "Fibonacci" --exit-model v2 --scale-out --pass-wr 50 \
  --emit-registry swingbot/core/backtesting/validation_registry.json \
  --run-date 2026-09-10 \
  --json <scratch>/fib_validation.json
```

- [ ] **Step 4: Record the outcome exactly as it came back**

Append `## Result` with N, win rate, ExpR, excl%, and the emitted badge status.
No retuning after, whatever it says — spec §2 and `backtest-methodology.md`.

- [ ] **Step 5: Flip the default only if it passed**

On PASS, change `default="false"` → `default="true"` in the
`FIB_TARGET_1_0_EXTENSION` Field and update `.env.example` to match. On FAIL the
flag **stays off** and the code ships inert, exactly as `DEAD_CAT_BOUNCE_VETO`
did after v68.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-fib-extension-validation.md \
        swingbot/core/backtesting/validation_registry.json swingbot/config.py .env.example
git commit -m "docs(v84): Fibonacci 1.0 extension VALIDATION result, budget spent"
```

---

# Phase 3B — Elliott Wave (R36; R37–R40 withheld)

### Task R36: Record the invalidated hypothesis and stop

**Files:**
- Create: `docs/superpowers/results/2026-09-10-v84-elliott-hypothesis-invalidated.md`
- Modify: `docs/superpowers/specs/2026-09-10-v84-strategy-rescue-v2-design.md` (§4.8 correction note)

**Interfaces:**
- Consumes: nothing
- Produces: a written verdict for Elliott Wave that satisfies the plan's
  Definition of Done item 1 ("every strategy has a recorded verdict") **without**
  any measurement

**No code change, no backtest, no VALIDATION.** This task exists because the
spec's mechanism turned out to already be shipped; the honest output is the
finding, not a measurement.

- [ ] **Step 1: Verify each claim yourself before writing it down**

Do not take the table at the top of this file on trust — re-check:

```bash
sed -n '691,700p' swingbot/core/market/entry_filters.py   # DEFAULT_PARAMS w2_* + depth_*
sed -n '714,754p' swingbot/core/market/entry_filters.py   # the live gate
sed -n '27,29p;46,55p' swingbot/core/market/entry_filters.py  # VOL_OK_MULT, vol_ok
sed -n '1,12p' tests/market/test_rescue_elliott.py        # the 0.382/0.786 fixture
ls docs/superpowers/results/ | grep elliott
```

- [ ] **Step 2: Write the findings doc**

It must state: (a) both specced gates already ship, with the file:line evidence
above; (b) the live retracement band is 0.382–0.618, so the spec's 0.382–0.786
is a **loosening**, not an addition; (c) these gates are the round-2 rescue whose
VALIDATION shot is already spent (`results/2026-07-rescue-elliott-validation.md`);
(d) therefore implementing §4.8 would re-run a closed pre-registration at a
looser threshold, which `backtest-methodology.md` forbids; (e) Elliott Wave's
verdict for this campaign is **NOT ATTEMPTED — hypothesis invalid at design
time**, distinct from "tested and failed"; (f) reopening needs a genuinely new
mechanism and a new pre-registration.

Also record the adjacent fact worth knowing for whoever writes that
pre-registration: `elliott_wave_entries` hard-returns no entries for every
horizon except `4w` (`entry_filters.py:708-709`), and
`strategy_types.py:200-203` documents that no gated subset reached a passing
train config. Any future mechanism inherits that volume ceiling.

- [ ] **Step 3: Correct the spec**

Add a dated note under §4.8 pointing at the findings doc and marking the section
**superseded — do not implement**. Leave the original text in place; the spec is
a record of what was believed at the time, not a document to quietly rewrite.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-elliott-hypothesis-invalidated.md \
        docs/superpowers/specs/2026-09-10-v84-strategy-rescue-v2-design.md
git commit -m "docs(v84): Elliott Wave hypothesis invalid -- gates already ship"
```

### Tasks R37–R40: deliberately unallocated

Reserved for an Elliott Wave rescue **if and when** a new mechanism is
pre-registered in the spec. Leaving these IDs empty is intentional — it keeps the
index's task map honest rather than back-filling busywork into slots that a
failed premise emptied.

Anyone adding tasks here must first: name a mechanism that is not the wave-2
retracement band, not the duration ratio, not the overlap check, and not a
volume gate (all four already ship); get it into the spec as a pre-registration;
and account for the 4w-only volume ceiling above.

---

## Part 3 close-out

Carry into R42/R45:

| Strategy | Expected artefact |
|---|---|
| Fibonacci | TRAIN result (always), plus walkforward + VALIDATION only if each prior gate passed |
| Elliott Wave | Findings doc only — verdict **NOT ATTEMPTED (hypothesis invalid)**, budget unspent |

Neither strategy runs the full pytest suite here; that is Task R41.
