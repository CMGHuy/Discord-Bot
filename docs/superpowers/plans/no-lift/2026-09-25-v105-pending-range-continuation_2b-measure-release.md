# v105 PENDING daily range continuation — Part 2b: measurement, holdout and release (Tasks 8–12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Header, global constraints, review focus and parallelisation live in
`2026-09-25-v105-pending-range-continuation_0-index.md`. Read them first. Parts 1a–2a must be done first; the file map is in Part 2a.

# Phase 2 — Measurement and forward evidence (continued)

### Task 8: Run free TRAIN stages and record the finding

**Files:**
- Create: `docs/superpowers/results/<YYYY-MM-DD>-v105-train.md` (date of the run)
- Data (not committed): `data/v105/pilot.jsonl`, `data/v105/train.jsonl`, `data/v105/*.json`

**Interfaces:**
- Consumes: `scripts/backtest/measure_pending_range.py` (Task 6),
  `scripts/backtest/validate_component.py --stage mde|walkforward`.
- Produces: the result note Task 9 reads (selected cell per direction or
  `no-eligible-cell`, code hash, cache manifest, MDE verdict).

- [ ] **Step 1: Load the gate**

Read `.claude/skills/backtest-gate/SKILL.md` and the v105 as-of note
immediately before running. Confirm that `git status --porcelain -- swingbot scripts`
is empty (a dirty tree makes every arm unscorable: `check_provenance`).

- [ ] **Step 2: Pilot (Stage −1 reachability)**

Dispatch the `backtest-runner` subagent with:

```bash
mkdir -p data/v105
python scripts/backtest/measure_pending_range.py pilot --out data/v105/pilot.jsonl --max-tickers 25 --workers 4
```

Read from the printed JSON: `N*|candidates`, `*|issued`, `*|risk_cap`,
`*|no_target`, `*|target_beyond_band`, `*|proximity_*` and `filled` per
`(path, direction, n, d, pressure)`. Extrapolate the full-universe filled
count as `filled × (universe size / 25)`. Also read the runtime from the last
`eta` line.

**Stop rule:** if the extrapolated filled count for the pressure-on arm is
below 30 in every cell for a direction, that direction is **underpowered**.
Record it in the result note and do not run `collect` for a finding on that
direction. Never loosen geometry, the 2% cap or the RR band to raise N.

- [ ] **Step 3: Full TRAIN collection**

Dispatch `backtest-runner` (expected run: hours; progress shows `[k/N] P%`):

```bash
python scripts/backtest/measure_pending_range.py collect --out data/v105/train.jsonl --workers 4
```

- [ ] **Step 4: Select per direction**

```bash
python scripts/backtest/measure_pending_range.py select --rows data/v105/train.jsonl --direction bullish --out data/v105/select_bullish.json
python scripts/backtest/measure_pending_range.py select --rows data/v105/train.jsonl --direction bearish --out data/v105/select_bearish.json
python scripts/backtest/measure_pending_range.py select --rows data/v105/train.jsonl --direction bullish --path live --out data/v105/select_bullish_live.json
python scripts/backtest/measure_pending_range.py select --rows data/v105/train.jsonl --direction bearish --path live --out data/v105/select_bearish_live.json
```

The `per_horizon` path is the spec's pooled measurement and decides the
cell. The `live` path (first building horizon per bar, one rearm state per
ticker) is reported beside it as the enablement-parity arm.

- [ ] **Step 5: MDE and walk-forward on the selected cell only**

For each direction with a selected cell `(N, d)`:

```bash
python scripts/backtest/measure_pending_range.py arms --rows data/v105/train.jsonl --direction bullish --n <N> --d <d> --stage mde --out data/v105/arms_bullish_mde.json
python scripts/backtest/validate_component.py --stage mde --arms data/v105/arms_bullish_mde.json --title "v105 range pressure bullish N<N> d<d>" --window "2020-01-01..2023-12-31" --train-effect-pp <d_wr from select_bullish.json> --observed-days 1461 --target-days 365
python scripts/backtest/measure_pending_range.py arms --rows data/v105/train.jsonl --direction bullish --n <N> --d <d> --stage walkforward --out data/v105/arms_bullish_wf.json
python scripts/backtest/validate_component.py --stage walkforward --arms data/v105/arms_bullish_wf.json --title "v105 range pressure bullish N<N> d<d>" --window "folds 2021/2022/2023"
```

Repeat with `bearish`. `--target-days 365` is the prospective holdout length
Task 9 will pre-register. If the MDE stage REFUSES at 365 days, record the
maturity (in days) at which it would resolve. Task 9 uses that figure.
Read each command's complete verdict. Exit code 1 means FAIL/REFUSED.

- [ ] **Step 6: Re-derive the headline numbers independently**

```bash
python - <<'PY'
import json
from swingbot.core.backtesting.acceptance import ArmTrade, win_rate, expectancy_r
for side in ("bullish", "bearish"):
    try:
        arms = json.load(open(f"data/v105/arms_{side}_mde.json"))
    except FileNotFoundError:
        continue
    for arm in ("baseline", "component"):
        t = [ArmTrade(**r) for r in arms[arm]]
        print(side, arm, len(t), win_rate(t), expectancy_r(t))
PY
```

These must equal the `select` output for that cell to the printed precision.
A mismatch stops the task and gets investigated.

- [ ] **Step 7: Write the result note**

`docs/superpowers/results/<date>-v105-train.md` must contain: the code hash,
git commit and cache manifest from `data/v105/train.jsonl.meta.json`; the
reachability funnel counts; per direction the 9-cell table (n, WR, ExpR,
ΔWR, ΔExpR, removed population, planned RR), the selected cell or
`no-eligible-cell`, the MDE verdict and the walk-forward verdict; the
`live`-path figures beside them; sector-cluster counts (distinct
`universe.sector_map("sp500")` sectors among issued tickers, top-3 sector
share); the `unresolved`, `cancelled_risk_cap`, `gap_fill` and
`close_back_inside` rates (labelled diagnostics); and the explicit line
"one-shot holdout budget: unused". Quote no pooled figure from any other
document.

- [ ] **Step 8: Commit**

```bash
git status --short
git add docs/superpowers/results/<date>-v105-train.md
git commit -m "docs(v105): TRAIN stages -- <bullish verdict>; <bearish verdict>; holdout unspent"
```

**Verification:** Step 6's re-derivation matches, and each
`validate_component.py` verdict was read in full. This is a measurement task,
not a test rerun.

### Task 9: Freeze the prospective holdout before it can be scored

Only if at least one direction cleared Task 8's MDE and walk-forward stages.
Otherwise skip to Task 12 with the no-lift close-out.

**Files:**
- Modify: `swingbot/core/backtesting/range_arms.py` (holdout guards)
- Modify: `scripts/backtest/measure_pending_range.py` (`prereg`, `holdout` subcommands)
- Test: `tests/backtesting/test_pending_range_arms.py` (append)
- Create: `docs/superpowers/results/<date>-v105-holdout-prereg.md` and `docs/superpowers/results/v105-holdout-prereg.json`

**Interfaces:**
- Produces:
  - `range_arms.PREREG_KEYS`
  - `range_arms.check_holdout(prereg, *, today, meta, spent_path) -> None` (raises ValueError)
  - `range_arms.holdout_status(arms, prereg) -> str` (`"scorable"` | `"sealed-thin"`)
  - `range_arms.mark_spent(spent_path, *, direction, verdict) -> None`
  - `range_arms.pressure_permutation_p(arms, *, n=200, seed=42) -> dict` (`armed_measurement.permutation_p` shape: `real_delta_win_rate_pp, p_value, n, n_valid`)

- [ ] **Step 1: Write the failing tests** (append to `tests/backtesting/test_pending_range_arms.py`)

```python
def _prereg(**kw):
    base = dict(direction="bullish", cell=[20, 0.5], holdout_start="2027-01-04",
                holdout_end="2027-12-31", min_decided=60, code_hash="c" * 64,
                cache_manifest_train="m" * 64, decision_rule="validate_component --stage validation, all six clauses",
                prereg_commit="b" * 40)
    base.update(kw)
    return base


def test_holdout_refuses_before_the_window_ends(tmp_path):
    with pytest.raises(ValueError, match="not finished"):
        ra.check_holdout(_prereg(), today="2027-12-31", meta=_meta(code_hash="c" * 64),
                         spent_path=tmp_path / "spent.json")


def test_holdout_refuses_a_second_shot(tmp_path):
    spent = tmp_path / "spent.json"
    ra.mark_spent(spent, direction="bullish", verdict="FAIL")
    with pytest.raises(ValueError, match="already spent"):
        ra.check_holdout(_prereg(), today="2028-01-10", meta=_meta(code_hash="c" * 64), spent_path=spent)


def test_holdout_refuses_changed_code(tmp_path):
    with pytest.raises(ValueError, match="code hash"):
        ra.check_holdout(_prereg(), today="2028-01-10", meta=_meta(code_hash="d" * 64),
                         spent_path=tmp_path / "spent.json")


def test_holdout_refuses_a_forbidden_or_pre_commit_window(tmp_path):
    with pytest.raises(ValueError, match="forbidden"):
        ra.check_holdout(_prereg(holdout_start="2026-10-01", holdout_end="2026-12-31"),
                         today="2027-02-01", meta=_meta(code_hash="c" * 64),
                         spent_path=tmp_path / "spent.json")


def test_thin_holdout_is_sealed_not_scored():
    arms = {"baseline": [], "component": [dict(ticker="A", strategy="s", horizon_key="4w",
                                               entry_date="2027-02-01", outcome="win",
                                               r_multiple=1.0, planned_rr=2.0)] * 10}
    assert ra.holdout_status(arms, _prereg(min_decided=60)) == "sealed-thin"
    assert ra.holdout_status(arms, _prereg(min_decided=5)) == "scorable"


def test_other_direction_shot_is_independent(tmp_path):
    spent = tmp_path / "spent.json"
    ra.mark_spent(spent, direction="bearish", verdict="FAIL")
    ra.check_holdout(_prereg(), today="2028-01-10", meta=_meta(code_hash="c" * 64), spent_path=spent)


def _trade(i, outcome):
    return dict(ticker=f"T{i}", strategy="s", horizon_key="4w", entry_date="2027-02-01",
                outcome=outcome, r_multiple=1.0 if outcome == "win" else -1.0, planned_rr=2.0)


def test_pressure_permutation_p_is_deterministic_and_directional():
    baseline = [_trade(i, "win" if i % 2 else "loss") for i in range(80)]
    winners = [t for t in baseline if t["outcome"] == "win"][:30]
    arms = {"baseline": baseline, "component": winners}
    first, second = ra.pressure_permutation_p(arms), ra.pressure_permutation_p(arms)
    assert first == second
    assert first["p_value"] is not None and first["p_value"] < 0.05
    random_half = {"baseline": baseline, "component": baseline[:40]}
    assert ra.pressure_permutation_p(random_half)["p_value"] > 0.05
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_pending_range_arms.py`
Expected: FAIL, `AttributeError: module ... has no attribute 'check_holdout'`.

- [ ] **Step 3: Implement the guards** (append to `range_arms.py`)

```python
import json  # add to the imports at the top

PREREG_KEYS = ("direction", "cell", "holdout_start", "holdout_end", "min_decided",
               "code_hash", "cache_manifest_train", "decision_rule", "prereg_commit")


def _spent(spent_path) -> dict:
    path = Path(spent_path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def check_holdout(prereg: dict, *, today: str, meta: dict, spent_path) -> None:
    """Refuse every way a holdout shot can be wasted or contaminated."""
    missing = [k for k in PREREG_KEYS if prereg.get(k) in (None, "", [])]
    if missing:
        raise ValueError(f"pre-registration missing {missing}")
    refuse_forbidden((prereg["holdout_start"], prereg["holdout_end"]))
    if prereg["direction"] in _spent(spent_path):
        raise ValueError(f"{prereg['direction']} holdout shot already spent")
    if today <= prereg["holdout_end"]:
        raise ValueError(f"holdout window not finished (ends {prereg['holdout_end']})")
    if meta.get("code_hash") != prereg["code_hash"]:
        raise ValueError("code hash differs from the pre-registered code: re-register, do not score")


def holdout_status(arms: dict, prereg: dict) -> str:
    decided = sum(t["outcome"] in ("win", "loss") for t in arms["component"])
    return "scorable" if decided >= prereg["min_decided"] else "sealed-thin"


def mark_spent(spent_path, *, direction: str, verdict: str) -> None:
    from datetime import datetime, timezone
    spent = _spent(spent_path)
    spent[direction] = {"verdict": verdict, "at": datetime.now(timezone.utc).isoformat()}
    Path(spent_path).write_text(json.dumps(spent, indent=1), encoding="utf-8")


PERMUTATION_N, PERMUTATION_SEED = 200, 42


def pressure_permutation_p(arms: dict, *, n: int = PERMUTATION_N, seed: int = PERMUTATION_SEED) -> dict:
    """Null: pressure is a random filter over the baseline candidates. Draw
    len(component) baseline trades without replacement, n times; p = share of
    draws whose mix-standardised dWR >= the real one (armed_measurement's
    v90 permutation, reused unchanged)."""
    import random
    from swingbot.core.backtesting.armed_measurement import permutation_p
    base = [ArmTrade(**t) for t in arms["baseline"]]
    comp = [ArmTrade(**t) for t in arms["component"]]
    rng = random.Random(seed)
    size = min(len(comp), len(base))
    return permutation_p(base, comp, [rng.sample(base, size) for _ in range(n)])
```

`check_holdout` compares ISO date strings, which order correctly.

- [ ] **Step 4: Add the CLI subcommands** (in `measure_pending_range.py`)

```python
PREREG = ROOT / "docs" / "superpowers" / "results" / "v105-holdout-prereg.json"
SPENT = ROOT / "docs" / "superpowers" / "results" / "v105-holdout-spent.json"


def _cmd_holdout(args):
    prereg = next(p for p in json.loads(PREREG.read_text(encoding="utf-8")) if p["direction"] == args.direction)
    window = (prereg["holdout_start"], prereg["holdout_end"])
    today = pd.Timestamp.now(tz="UTC").date().isoformat()
    tickers = _universe(args.tickers)
    meta_probe = {"code_hash": ra.code_hash(ROOT)}
    ra.check_holdout(prereg, today=today, meta=meta_probe, spent_path=SPENT)
    meta = _collect(tickers, window, args.out, args.workers)
    rows, _ = _load(args.out)
    n, d = prereg["cell"]
    arms = ra.paired_arms(rows, meta, cell=(n, d), direction=args.direction, window=window)
    status = ra.holdout_status(arms, prereg)
    Path(args.arms_out).write_text(json.dumps(arms, indent=1), encoding="utf-8")
    print(f"holdout {args.direction}: {status}", flush=True)
    if status == "scorable":
        perm = ra.pressure_permutation_p(arms)
        Path(f"{args.arms_out}.perm.json").write_text(json.dumps(perm, indent=1), encoding="utf-8")
        print(f"permutation p: {perm['p_value']} (n_valid={perm['n_valid']})", flush=True)
```

and register it:

```python
COMMANDS["holdout"] = _cmd_holdout
# in _parser(), after the arms parser:
    holdout = sub.add_parser("holdout")
    holdout.add_argument("--direction", required=True, choices=("bullish", "bearish"))
    holdout.add_argument("--out", required=True)
    holdout.add_argument("--arms-out", required=True)
    holdout.add_argument("--tickers")
    holdout.add_argument("--workers", type=int, default=4)
```

`_collect` calls `ra.refuse_forbidden(window)`, so the holdout window is
checked twice. `mark_spent` is called by hand in Task 10, only after
`validate_component --stage validation` has actually run on scorable arms.
A sealed-thin result never marks the shot spent.

- [ ] **Step 5: Run the tests, then write the pre-registration**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_pending_range_arms.py`. Expected: `0 failed`.

Commit the code first:

```bash
git add swingbot/core/backtesting/range_arms.py scripts/backtest/measure_pending_range.py tests/backtesting/test_pending_range_arms.py
git commit -m "feat(v105): holdout guards -- unfinished, spent, changed-code and forbidden-window refusals"
```

Then write `docs/superpowers/results/v105-holdout-prereg.json`, one object per
direction that cleared Task 8:

```json
[
  {"direction": "bullish", "cell": [<N>, <d>],
   "holdout_start": "<first complete session after this commit AND after 2026-12-31>",
   "holdout_end": "<start + the Task 8 MDE maturity, at least 365 days>",
   "min_decided": <decided trades at which Task 8's MDE resolved>,
   "code_hash": "<python -c \"from pathlib import Path; from swingbot.core.backtesting import range_arms as ra; print(ra.code_hash(Path('.')))\">",
   "cache_manifest_train": "<from data/v105/train.jsonl.meta.json>",
   "decision_rule": "validate_component.py --stage validation on pressure-off vs pressure-on arms; all six v72 clauses; permutation p required; badge gate separately",
   "prereg_commit": "<git rev-parse HEAD before this commit>"}
]
```

Plus `docs/superpowers/results/<date>-v105-holdout-prereg.md`, restating the
JSON in prose, citing the Task 8 note, and recording the Task 7 shadow report
(`python scripts/reports/range_shadow_report.py`) as the forward
execution-evidence baseline. If shadow telemetry has no `trigger_observed`
events yet, say so: missing execution evidence keeps alerts masked
regardless of TRAIN.

- [ ] **Step 6: Inspect the diff, then commit**

```bash
git diff --cached --stat
git add docs/superpowers/results/v105-holdout-prereg.json docs/superpowers/results/<date>-v105-holdout-prereg.md
git commit -m "docs(v105): pre-register the prospective holdout -- <directions>, <start>..<end>, one shot each"
```

**Verification:** the narrow holdout-refusal tests, plus a read of the frozen
pre-registration diff before committing. No validation outcome is read.

### Task 10: Score one powered holdout shot and execution feed

Runs only after `holdout_end` has passed.

**Files:**
- Create: `docs/superpowers/results/<date>-v105-holdout.md`
- Modify: `docs/superpowers/results/v105-holdout-spent.json` (via `mark_spent`)

- [ ] **Step 1: Collect and check power (refuses early automatically)**

```bash
python scripts/backtest/measure_pending_range.py holdout --direction bullish --out data/v105/holdout_bullish.jsonl --arms-out data/v105/arms_bullish_holdout.json
```

If it prints `sealed-thin`, record the decided count in the result note, stop
for this direction, and do not mark it spent. Resume at the pre-registered
maturity condition.

- [ ] **Step 2: One validation shot on scorable arms**

Take `<p>` from the `permutation p:` line Step 1 printed (also saved in
`data/v105/arms_bullish_holdout.json.perm.json`). If it printed `None`,
omit `--permutation-p`. The validation stage then FAILS by rule. Record
that; do not invent a p.

```bash
python scripts/backtest/validate_component.py --stage validation --arms data/v105/arms_bullish_holdout.json --title "v105 range pressure bullish N<N> d<d> HOLDOUT" --window "<start>..<end>" --permutation-p <p> --out-md docs/superpowers/results/<date>-v105-holdout-bullish.md
python -c "from swingbot.core.backtesting import range_arms as ra; ra.mark_spent('docs/superpowers/results/v105-holdout-spent.json', direction='bullish', verdict='<PASS|FAIL>')"
```

- [ ] **Step 3: Re-derive and report**

Re-derive WR/ExpR per arm from `arms_bullish_holdout.json` (Task 8 Step 6
snippet with the holdout path), and require a match. Add to the note:
sector concentration, `close_back_inside` / `unresolved` /
`cancelled_risk_cap` rates, the strategy-badge absolute gate for the
pressure-on source (n, WR, ExpR against the registry's VALIDATED threshold in
`swingbot/core/backtesting/registry.py`), and the shadow report's lead-time,
late-rate and delivery-parity figures. Do not tune a failed result.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/<date>-v105-holdout*.md docs/superpowers/results/v105-holdout-spent.json
git commit -m "docs(v105): holdout shot -- <direction> <PASS|FAIL>; shot spent"
```

A failure ends the direction as no-lift or shadow-only. A pass makes Task 11
eligible, not automatic.

**Verification:** aggregates re-derived from the sealed rows, and the
acceptance script's complete verdict read once.

# Phase 3 — Release and verification

### Task 11: Decide direction-specific alert enablement

**Files:**
- Modify: `swingbot/core/backtesting/validation_registry.json` (only via the registry's own emit path, if a direction passes)
- Modify: `.env.example` (defaults stay `off`; comments name the passing cell)
- Modify: `docs/strategy/strategy.md`, `docs/features/features.md` (user-facing description)
- Test: `tests/scanning/test_pending_range_alerts.py` (append the integration test)

- [ ] **Step 1: Record the per-direction decision**

A direction is enabled only if all four hold. (1) The Task 10 validation
passed. (2) The source badge cleared its absolute gate. (3) The shadow
report shows timely PENDING delivery: `late_rate` and `delivery_parity`
reported with n ≥ 30 triggers. (4) The risk-cap divergence notice was
observed at least once in shadow, or the absence is explicitly accepted by
the human partner. Write the decision table into the Task 10 note. A failing
direction stays out of `RANGE_ALERTS_LIVE_DIRECTIONS`.

- [ ] **Step 2: Write the failing integration test** (append)

```python
def test_scan_to_pending_to_fill_links_the_paper_trade(env, monkeypatch):
    from unittest.mock import MagicMock
    frame, trig, plan = _issue(env)
    assert env.calls and env.calls[0]["plan_id"] == plan.plan_id
    trade_log = MagicMock()
    manager = PlanManager(env.store, lambda t: trig + 0.02, trade_log=trade_log)
    [event] = manager.poll()
    assert event.transition == "filled"
    assert env.store.get(plan.plan_id).status == PlanStatus.ACTIVE
    assert env.store.get(plan.plan_id).pending_notice["transition"] == "filled"
    assert trade_log.record_plan_fill.called


def test_scan_to_pending_to_expiry_discards_the_placeholder(env):
    from unittest.mock import MagicMock
    _, trig, plan = _issue(env)
    trade_log = MagicMock()
    manager = PlanManager(env.store, lambda t: trig - 0.5, bar_count_fn=lambda t, c: 6, trade_log=trade_log)
    [event] = manager.poll()
    assert event.transition == "cancelled_expired"
    assert trade_log.discard_plan_placeholder.called
    assert env.store.get(plan.plan_id).pending_notice["transition"] == "cancelled_expired"
```

If `_on_event` calls these hooks with names other than `record_plan_fill` /
`discard_plan_placeholder`, read `plan_manager.py:_on_event` (~L394) and use
its exact names. Do not change `_on_event`.

- [ ] **Step 3: Run it**

Run: `python scripts/dev/testrun.py file tests/scanning/test_pending_range_alerts.py`
Expected: `0 failed`. Then
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_pending.py`. Expected: `0 failed`.

- [ ] **Step 4: v104 overlap and docs**

If v104 B1/B2 code has landed, add a scan-level dedupe test. The same ticker
must not receive both a v104 short and a range SHORT plan on one scan, since
`_prior_state` only sees range plans. The rule is: skip the range plan when
`trade_log.open_trade_for_ticker` is set, which `_issue` already does. Pin it
with a test that stubs an open v104 trade. Update `docs/strategy/strategy.md`
(one section: geometry, trigger, stop, TP, expiry, broker workflow, what the
paper plan cannot do) and `docs/features/features.md` (the three config
keys). Keep `.env.example` defaults `off`/empty. Enabling is an operator
action on production, out of scope here.

- [ ] **Step 5: Commit**

```bash
git add tests/scanning/test_pending_range_alerts.py docs/strategy/strategy.md docs/features/features.md .env.example
git commit -m "feat(v105): <direction> enablement decision, scan-to-trade integration test, user docs"
```

**Verification:** the narrow runs above. If no direction passes, record
no-lift here, commit only the decision note, and skip the version bump.

### Task 12: Run the one final suite and close out

- [ ] **Step 1: Full suite, once**

Dispatch the `test-runner` subagent with `python scripts/dev/testrun.py full`.
Require `0 failed`, `0 xfailed`. **If not green, fix forward from those
failures.** They are this plan's regressions.

- [ ] **Step 2: Static gates**

```bash
python -m radon cc -s -n C swingbot/core/market/range_candidate.py swingbot/core/planning/range_builder.py swingbot/core/planning/range_source.py swingbot/core/backtesting/range_replay.py swingbot/core/backtesting/range_arms.py swingbot/core/scanning/range_pass.py swingbot/core/scanning/range_embeds.py swingbot/core/scanning/range_shadow.py swingbot/core/presentation/instructions.py swingbot/core/scanning/scan_run.py swingbot/config.py scripts/backtest/measure_pending_range.py
python -m py_compile bot.py admin_ui.py swingbot/core/market/range_candidate.py swingbot/core/planning/range_builder.py swingbot/core/planning/range_source.py swingbot/core/backtesting/range_replay.py swingbot/core/backtesting/range_arms.py swingbot/core/scanning/range_pass.py swingbot/core/scanning/range_embeds.py swingbot/core/scanning/range_shadow.py
```

Expected: no new function at ≥ 15. No compile error.

- [ ] **Step 3: Close out**

Follow `docs/claude/document-lifecycle.md`. Move the spec and all five plan
parts to `implemented/` if a direction shipped, or to `no-lift/` if the
measured work cannot ship (the code stays inert behind `RANGE_ALERTS_MODE=off`).
Write the final evidence summary and actual limitations: daily replay cannot
order entry-bar events, and there is no broker integration. Amend `Bump:` and
`Edge:` with one clause if the outcome differed from the prediction.

- [ ] **Step 4: Release (only if live alert behaviour shipped)**

Read `VERSION.json`, bump the `bot` line one minor, set `bot_updated` to now,
and commit that alone. Then run `python scripts/dev/build_version_matrix.py`
and commit the regenerated `swingbot/admin/version_history.json` in a second
commit. Run its narrow version-matrix test with `testrun.py file`. If
shadow-only, there is no release commit.

**Verification:** preserve the exact final suite verdict line, the radon
output, any release commits, and the per-direction gate decisions in the
close-out note.
