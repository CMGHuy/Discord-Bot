# v114 Part 2 — Pre-registration, measurement, NO-LIFT or ship

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. The header, Global Constraints and Parallelisation in `2026-09-30-v114-scenario-stop-band_0-index.md` bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-30-v114-scenario-stop-band-design.md`

---

# Phase C — Pre-registration and measurement

### Task V114-09: Pre-register before any run

**Files:**
- Modify: `docs/superpowers/results/2026-09-30-v114-preregistration.md` (on `main`; adds §2-§7)

**Interfaces:**
- Consumes: the branch at the tip after V114-08 (its HEAD becomes the measured commit); production settings, read-only.
- Produces: a committed pre-registration whose path is passed to `measure_arms.py --preregistration` in V114-12, and the baseline config table that V114-10 … V114-12 check before every run.

- [ ] **Step 1: Load the `backtest-gate` skill** and follow it for everything that follows in Phase C.

- [ ] **Step 2: Confirm the gate with the partner.** Use `AskUserQuestion`, one question, recommended option first:

  "Which acceptance gate does v114 pre-register? (1, recommended) The spec's reading: the `acceptance_volume.evaluate_volume` composite. Objective: closed-trade volume gain (> 0). Constraints: win-rate floor (`WIN_RATE_FLOOR_PP` = -2.0pp lower bound), profit floor (`NON_INFERIORITY_R` = -0.01R lower bound) and the geometry lock (2%), all used verbatim. Permutation skipped because no improvement is claimed. Stage 2 uses `backtest_wf`'s fold rules. (2) v72 `acceptance.evaluate` verbatim. Its clause 1 requires ΔWR > 0 at p < 0.05, which a looser stop floor is not expected to deliver, so it is a near-certain NO-LIFT."

  Record the answer verbatim in §4. If the partner picks (2), every `--gate volume` in V114-10 … V114-12 becomes the default `--gate win_rate`, Stage 2 uses `gate_win_rate`, and VALIDATION needs `--permutation-p` from `scripts/backtest/permutation_test.py` (n = 200).

- [ ] **Step 3: Pin the baseline configuration.** The baseline arm (`measure_arms` delta `{}`) reads whatever `.env` the run environment loads. Read production's settings (read-only) and the run environment's settings, and put both in the table:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c 'from swingbot import config as c; print({k: getattr(c, k) for k in (\"MIN_STOP_DISTANCE_PCT\", \"MIN_REWARD_PCT\", \"MIN_RISK_REWARD_RATIO\", \"MAX_RISK_REWARD_RATIO\", \"MIN_TARGET_CONFLUENCE_COUNT\", \"LEVEL_LIFECYCLE_STOPS_ENABLED\", \"AVWAP_LEVELS_ENABLED\", \"VOLUME_PROFILE_NODES_ENABLED\", \"FIB_TARGET_1_0_EXTENSION\", \"RSI_DIV_MIN_CONSECUTIVE_TURN\", \"MA_RIBBON_CONFIRM_BARS\", \"SR_MIN_LEVEL_TOUCHES\", \"ADAPTIVE_RUNNER_TRAIL_ENABLED\")})'"
```

Then run the same `python -c '…'` locally from the **worktree root**. Every key must match production. For any key that does not match, set the local (gitignored) `.env` the worktree loads to production's value, re-run until they match, and note each edit in §3. `MIN_STOP_DISTANCE_PCT` must print `2.0` locally. The branch default is now 1.5, so a `.env` that omits the key would make the baseline equal the candidate.

- [ ] **Step 4: Record the measured commit.** From the worktree: `git rev-parse HEAD` and `git status --porcelain` (which must be empty). Every stage runs at exactly this commit. If code has to change after this point, this pre-registration is void and the partner decides what happens next.

- [ ] **Step 5: Append §2-§7** to `docs/superpowers/results/2026-09-30-v114-preregistration.md`. Put the Step 3 values into the §3 table, the Step 4 hash into §3, and the Step 2 answer into §4. These are measured facts written in at this step:

````markdown
## 2. Hypothesis

Lowering the scenario stop floor (`MIN_STOP_DISTANCE_PCT`) from 2.0% to 1.5%,
with admission capped at the 2.0% planned-loss cap, adds confluence alerts
(`Edge: volume`) without degrading win rate or expectancy beyond the existing
non-inferiority floors. Reward floor, risk:reward band and the cap do not move.
Measured on the production cache on 2026-09-30 this admits 1 scenario today
(one bearish 7m) against 0; the backtest measures ordinary days.

## 3. Arms (both produced by `scripts/backtest/measure_arms.py`, one process, one code hash)

- **Measured commit:** `<branch HEAD from Step 4>` on branch `2026-09-30-v114-scenario-stop-band`.
- **Baseline:** delta `{}`: production's settings (table below), admission ceiling = the 2.0% cap (V114-03).
- **Component:** `--knob MIN_STOP_DISTANCE_PCT=1.5`, nothing else.
- **Engines:** `confluence` + `strategy` (producer default, i.e. the whole alert stream). `MIN_STOP_DISTANCE_PCT` is observed by confluence only (`reachability.py`), so strategy rows are identical in both arms and are reported, not hidden.
- **Universe / horizons:** the full cached universe x `windows.ALL_HORIZONS` (stamp-checked).

| Setting | Production | Run environment | Local `.env` edit made |
|---|---|---|---|
| (one row per key printed in Step 3) | | | |

## 4. Gate (confirmed with the partner on <date>: "<answer verbatim>")

`swingbot/core/backtesting/acceptance_volume.evaluate_volume`: every non-SKIPPED clause must PASS.

| Clause | Threshold | Source (verbatim) |
|---|---|---|
| `volume_gain` (objective) | component closed trades > baseline | `acceptance_volume._clause_volume_gain` |
| `win_rate_floor` | mix-standardised ΔWR lower 95% >= -2.0pp | `acceptance_harvest.WIN_RATE_FLOOR_PP` |
| `profit_floor` | ΔExpR lower 95% > -0.01R | `acceptance.NON_INFERIORITY_R` |
| `geometry` | median planned RR and mean win R each fall <= 2% | `acceptance.GEOMETRY_MAX_DROP_PCT` |
| `not_luck` | SKIPPED (no improvement claimed) | — |

Ticker-cluster bootstrap, 10,000 resamples (`acceptance.BOOTSTRAP_RESAMPLES`), seed 42.

## 5. Funnel (each stage gates the next; a failure ends the spec, budget intact unless stated)

| Stage | Producer stage / window | Rule |
|---|---|---|
| −1 reachability | `pilot` 2018-06-01..2020-12-31, 10 tickers | `validate_component --stage reachability`: REACHABLE, changed outcomes > 0 |
| 0 MDE | `selection` 2018-06-01..2022-12-31 | `validate_component --stage mde --train-effect-pp 2.0`: RESOLVABLE (the sample can resolve a 2.0pp ΔWR, the width of the win-rate floor) |
| TRAIN | same `selection` arms | `validate_component --stage train --gate volume`: PASS |
| 2 walk-forward | `walkforward`, folds 2021 / 2022 / 2023 | `--stage walkforward --gate volume`: >= 2 of 3 folds PASS, every fold >= 30 decided trades (`backtest_wf` constants) |
| 3 VALIDATION | `validation` 2024-01-01..2025-12-31, **one shot, ever** | `--stage validation --gate volume`: PASS |

No grid, so Stage 1 plateau selection does not apply: there is exactly one candidate (1.5).

## 6. Reporting (every stage, pass or fail)

- The full clause table and per-stratum table as rendered.
- **`tight_stop` stratification:** the "By tight_stop" table (tight / not tight / strategy rows) for both arms. Disclosure, not a gate.
- **Volume, stated honestly:** added closed trades in absolute terms, and per calendar year of the window, beside the percentage. A PASS that adds almost no alerts is reported as exactly that (spec § Risk).
- Population split (removed / added / changed / unchanged). The floor change can displace a baseline trade through the per-direction cooldown, so this is not a pure superset, and the split is shown rather than assumed.

## 7. Fallback (spec § Validation, fixed now)

Any stage FAIL or REFUSED -> **NO-LIFT**. The spec closes, production stays at
current behaviour (floor 2.0%, cap 2.0%), and the V114-05 default flip is
never merged. There is no re-run after a failed shot without the partner, and
no threshold is loosened, re-read or re-tuned. The VALIDATION budget is spent
by V114-12's run whatever its verdict.
````

- [ ] **Step 6: Commit on `main`** (before anything is run):

```bash
git add docs/superpowers/results/2026-09-30-v114-preregistration.md
git commit -m "docs(v114): pre-registration -- arms, gate, funnel, fallback (before any run)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Record the resulting commit hash in the progress file. V114-12 cites it.

### Task V114-10: Stage −1, Stage 0 and TRAIN (free stages)

**Files:**
- Create (on `main`): `docs/superpowers/results/<run-date>-v114-train.md` and `.json` (validate_component output), with §0/§1 summary lines added by hand
- Arms (not committed): `logs/v114/pilot.json`, `logs/v114/selection.json` in the worktree

**Interfaces:**
- Consumes: V114-09's committed pre-registration; the worktree at the pre-registered HEAD.
- Produces: the TRAIN verdict, which gates V114-11.

- [ ] **Step 1: Pre-flight (every run).** In the worktree: `git rev-parse HEAD` equals the pre-registered hash, and the Step-3 config one-liner prints the pre-registered values. On any mismatch, stop and do not run.

- [ ] **Step 2: Dispatch `backtest-runner`** (run in the background, polled by its progress file) with these commands from the worktree root. `measure_arms.py` writes `logs/measure_arms.<id>.progress` with a percent figure and deletes it on completion.

```bash
mkdir -p logs/v114
python scripts/backtest/measure_arms.py --stage pilot --knob MIN_STOP_DISTANCE_PCT=1.5 --out logs/v114/pilot.json
python scripts/backtest/validate_component.py --stage reachability --arms logs/v114/pilot.json --title "v114 stop floor 1.5" --window "2018-06-01..2020-12-31"
```

  If the result is `refused:zero-diff` or `refused:unreachable:*`, stop and go to V114-13 with "Stage −1 refused, budget intact". Otherwise:

```bash
python scripts/backtest/measure_arms.py --stage selection --knob MIN_STOP_DISTANCE_PCT=1.5 --out logs/v114/selection.json
python scripts/backtest/validate_component.py --stage mde --arms logs/v114/selection.json --train-effect-pp 2.0 --title "v114 stop floor 1.5" --window "2018-06-01..2022-12-31"
```

  If the result is `REFUSED`, go to V114-13 with "Stage 0 refused, budget intact". Otherwise:

```bash
python scripts/backtest/validate_component.py --stage train --gate volume --arms logs/v114/selection.json --title "v114 stop floor 1.5" --window "2018-06-01..2022-12-31" --out-md logs/v114/train.md --out-json logs/v114/train.json
```

- [ ] **Step 3: Record on `main`.** Copy `logs/v114/train.md` and `train.json` to `docs/superpowers/results/<run-date>-v114-train.{md,json}`. Add a header section quoting the pre-registered TRAIN rule (§5), the Stage −1 line (baseline N, component N, changed outcomes), the Stage 0 lines (observed N, paired and unpaired MDE, verdict), and §6's honest-volume lines: added trades in absolute terms and per year of 2018-06..2022-12. Also add an **Observations** section that states failures as failures. Do not round the verdict into a softer word. Commit:

```bash
git add docs/superpowers/results/<run-date>-v114-train.md docs/superpowers/results/<run-date>-v114-train.json
git commit -m "docs(v114): Stage -1/0 and TRAIN -- <PASS|FAIL>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Gate.** TRAIN `FAIL` -> V114-13, and no walk-forward or VALIDATION run. TRAIN `PASS` -> V114-11.

### Task V114-11: Stage 2 walk-forward (free)

**Files:**
- Create (on `main`): `docs/superpowers/results/<run-date>-v114-walkforward.{md,json}`
- Arms (not committed): `logs/v114/walkforward.json`

**Interfaces:**
- Consumes: V114-10 PASS.
- Produces: the Stage 2 verdict, which gates V114-12.

- [ ] **Step 1: Pre-flight** exactly as in V114-10 Step 1.

- [ ] **Step 2: Dispatch `backtest-runner`:**

```bash
python scripts/backtest/measure_arms.py --stage walkforward --knob MIN_STOP_DISTANCE_PCT=1.5 --out logs/v114/walkforward.json
python scripts/backtest/validate_component.py --stage walkforward --gate volume --arms logs/v114/walkforward.json --title "v114 stop floor 1.5" --window "2021-01-01..2023-12-31" --out-md logs/v114/walkforward.md --out-json logs/v114/walkforward.verdict.json
```

- [ ] **Step 3: Record on `main`.** Copy the rendered table and verdict JSON to `docs/superpowers/results/<run-date>-v114-walkforward.{md,json}`. Add the pre-registered rule, the per-fold added-trade counts, and an Observations section. Commit `docs(v114): Stage 2 walk-forward -- <PASS|FAIL>` with the trailer.

- [ ] **Step 4: Gate.** `FAIL` -> V114-13 (VALIDATION budget intact). `PASS` -> V114-12.

### Task V114-12: Stage 3 VALIDATION — the one shot

**Files:**
- Create (on `main`): `docs/superpowers/results/<run-date>-v114-validation.{md,json}`
- Arms (not committed): `logs/v114/validation.json`

**Interfaces:**
- Consumes: V114-11 PASS; the pre-registration's absolute path in the main tree.
- Produces: the final verdict, which selects V114-13 (FAIL) or V114-14 (PASS).

- [ ] **Step 1: Pre-flight** exactly as in V114-10 Step 1. Also confirm that no `docs/superpowers/results/*-v114-validation.*` exists yet. If one exists, the shot is spent: stop and report.

- [ ] **Step 2: Dispatch `backtest-runner`, once.** The `--preregistration` path is the main tree's committed file:

```bash
python scripts/backtest/measure_arms.py --stage validation --knob MIN_STOP_DISTANCE_PCT=1.5 --preregistration "E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/2026-09-30-v114-preregistration.md" --out logs/v114/validation.json
python scripts/backtest/validate_component.py --stage validation --gate volume --arms logs/v114/validation.json --title "v114 stop floor 1.5" --window "2024-01-01..2025-12-31" --out-md logs/v114/validation.md --out-json logs/v114/validation.verdict.json
```

  If the producer crashes before writing `logs/v114/validation.json`, no outcome has been read and the shot is not spent. Fix the environment only (not code, not thresholds) and re-run Step 2 once. Record that in the results doc. A crash after the verdict was printed is a spent shot.

- [ ] **Step 3: Record on `main`, as-is.** Copy to `docs/superpowers/results/<run-date>-v114-validation.{md,json}`. Add the pre-registration commit hash, the quoted rule, the tight_stop table, the honest volume lines (added trades, and per year of 2024-2025), and Observations. Commit `docs(v114): VALIDATION (one shot) -- <PASS|FAIL>` with the trailer.

- [ ] **Step 4: Gate.** `FAIL` -> V114-13. `PASS` -> V114-14. Neither verdict is re-run.

# Phase D — Close-out: NO-LIFT or ship

### Task V114-13: NO-LIFT close-out (only if any stage failed or was refused)

**Files:**
- Modify (on `main`): `docs/claude/backtest-methodology.md` (closed pre-registrations table)
- Modify (on `main`): the spec (`**Status:**` line)

**Interfaces:**
- Consumes: the failing stage's results doc.
- Produces: the closed-row record. Production and the `.env` files are unchanged.

- [ ] **Step 1: Add the closed row** to the table in `docs/claude/backtest-methodology.md`, after the last row:

```markdown
| Scenario stop floor 2.0% -> 1.5%, admission capped at the 2.0% planned-loss cap (v114) | **NO-LIFT at <stage> — <one-line reason with the failing clause and its number>. VALIDATION budget <spent | not spent, remains available>.** Volume-edge gate (`acceptance_volume.evaluate_volume`: volume gain objective, `WIN_RATE_FLOOR_PP` / `NON_INFERIORITY_R` / geometry as non-inferiority), full universe x all horizons. Production stays at floor 2.0% and cap 2.0%; the default flip (V114-05) stays on branch `2026-09-30-v114-scenario-stop-band`, unmerged. Reopening needs a new hypothesis, not a re-read of this table | `results/2026-09-30-v114-preregistration.md`, `results/<run-date>-v114-<stage>.md` |
```

  Run `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`. `AGENTS.md` does not list closed rows, so it needs no change unless that test says otherwise.

- [ ] **Step 2: Ask the partner about the integrity half.** Use `AskUserQuestion`, one question, recommended first: "v114 is NO-LIFT. Land its integrity half on `main` without the floor change? (1, recommended) Yes. Cherry-pick V114-02, V114-03, V114-04, V114-06, V114-07 and V114-08 (cap tests, the shared admission function with ceiling = cap, band text, tight_stop, the volume gate), and leave V114-05 (the 1.5 default) unmerged. Production's band stays [2.0, 2.0]. (2) No, leave everything on the branch." On (1), cherry-pick those commits onto `main` in order. Run `python scripts/dev/testrun.py fast` and fix forward. The plan then closes to `implemented/` (code reached `main`, inert for production). On (2), it closes to `no-lift/`.

- [ ] **Step 3: Spec status.** Add `**Status:** Closed NO-LIFT <date> at <stage>; VALIDATION <spent | not spent>; integrity half <landed | on branch>.` under the spec's header. Commit Steps 1 and 3 on `main`:

```bash
git add docs/claude/backtest-methodology.md docs/superpowers/specs/2026-09-30-v114-scenario-stop-band-design.md
git commit -m "docs(v114): NO-LIFT at <stage> -- closed pre-registration row

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4:** Skip V114-14 and go to V114-15.

### Task V114-14: Ship preparation — merge, `.env.example`, docs (only on a VALIDATION PASS)

**Files:**
- Merge: branch `2026-09-30-v114-scenario-stop-band` -> `main`
- Modify (on `main`): `.env.example:78-80`, `docs/strategy/strategy-plans.md:41`, `docs/claude/backtest-methodology.md` (closed row), the spec (`**Status:**`)

**Interfaces:**
- Consumes: V114-12 PASS.
- Produces: `main` carrying the code, the 1.5 default and the mirrored example config. Production is still untouched until V114-15.

- [ ] **Step 1: Fast tier on the branch.** From the worktree: `python scripts/dev/testrun.py fast`, which must show `0 failed`. Fix forward if it does not.

- [ ] **Step 2: Merge.** Load `worktree-lifecycle`, then merge the branch into `main` (another session may be working in the main tree, so follow the skill's concurrency check). If the merge resolves conflicts, note it: V114-15's full run then covers the resolution, which is the one exception to not re-running after a merge.

- [ ] **Step 3: `.env.example`.** Replace the floor block with:

```
# Hard filter: dropped entirely if the stop sits closer than this to
# entry -- too exposed to ordinary daily noise. No exceptions.
# The band's ceiling is the 2% planned-loss cap (v114): stops 1.5-2.0%.
MIN_STOP_DISTANCE_PCT=1.5
```

- [ ] **Step 4: Docs that state the old floor.** Run `git grep -n "MIN_STOP_DISTANCE_PCT\|stop distance" -- docs/ AGENTS.md CLAUDE.md README.md ':!docs/superpowers'` and correct every statement of a 2% floor. The known one is `docs/strategy/strategy-plans.md:41`: change "default **2%**" to "default **1.5%**", and add after that sentence: "The stop must also sit no further than the 2% planned-loss cap, so the admitted band is 1.5-2.0% (v114)." Leave `docs/superpowers/` (historical specs, plans, results) untouched.

- [ ] **Step 5: Closed-row record and spec status.** Add to the table in `docs/claude/backtest-methodology.md`:

```markdown
| Scenario stop floor 2.0% -> 1.5%, admission capped at the 2.0% planned-loss cap (v114) | **PASS, budget spent — ships on by default.** Volume-edge gate (`acceptance_volume.evaluate_volume`): <volume_gain detail>, win-rate floor lower bound <x>pp (>= -2.0), ExpR lower bound <y>R (> -0.01), geometry <z>%. Added <n> closed trades over 2024-2025 (<k>/year). tight_stop: <one line>. On because it adds alerts without breaching the non-inferiority floors, **not** because an edge was measured. Do not re-run | `results/2026-09-30-v114-preregistration.md`, `results/<run-date>-v114-validation.md` |
```

  Fill in the bracketed values from the validation JSON, copying numbers without re-deriving them from memory (`pooled-numbers` skill). Add `**Status:** Shipped <date>; VALIDATION spent (PASS).` to the spec. Run `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`.

- [ ] **Step 6: Commit (three commits on `main`).**

```bash
git add .env.example
git commit -m "config(v114): .env.example stop floor 1.5 -- mirrors the production edit in V114-15

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add docs/strategy/strategy-plans.md
git commit -m "docs(v114): strategy plans state the 1.5-2.0% stop band

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add docs/claude/backtest-methodology.md docs/superpowers/specs/2026-09-30-v114-scenario-stop-band-design.md
git commit -m "docs(v114): VALIDATION PASS -- closed pre-registration row, spec status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V114-15: Full-suite verification, release, production `.env`, close-out

**Files:**
- Modify (PASS only): `VERSION.json`, `swingbot/admin/version_history.json`; production `/opt/swing-bot/.env` (mirrored by V114-14's `.env.example`)

**Interfaces:**
- Consumes: everything above. On a PASS that is `main`. On a NO-LIFT it is `main` if the integrity half landed, otherwise the branch.
- Produces: a green suite. On a PASS it also produces a `bot minor` release, production scanning with the 1.5-2.0% band, and the plan closed to `implemented/`. On a NO-LIFT, the plan is closed to `implemented/` or `no-lift/`.

- [ ] **Step 1: Full suite, once.** Dispatch `test-runner` for `python scripts/dev/testrun.py full` on the tree named above. Require `0 failed` and `0 xfailed`. (This plan touches no `frontend/`.) **If it is not green, fix forward from the failures it names.** They are this plan's regressions. A failure that passes in isolation and sits in code v114 never touched is reported with both outputs, and the suite is not called green.

- [ ] **Step 2 (PASS only): Release.** Invoke `/close-out v114`. It reads `VERSION.json` from disk at that moment, bumps the **bot** line by a **minor** step, stamps `bot_updated`, commits `release(bot): <version> -- scenario stop band 1.5-2.0%`, runs `python scripts/dev/build_version_matrix.py`, commits `chore(bot): <version> -- scenario stop band 1.5-2.0%`, moves the spec and this plan to `implemented/`, and removes the worktree. Then run `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`, which must pass. (NO-LIFT: `/close-out v114` with no bump. It moves to `implemented/` or `no-lift/` per V114-13 Step 2, and keeps the worktree on a `no-lift/` close.)

- [ ] **Step 3 (PASS only): Deploy the code.** Load the `deploy` skill and push `main`. Wait until production runs the new image. This must happen before Step 4, so that production's admission ceiling is the cap when the floor drops.

- [ ] **Step 4 (PASS only): Production `.env`, via `mirror-prod`.** Load the `mirror-prod` skill. Then:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && cp .env .env.bak-v114-$(date -u +%Y%m%dT%H%M%SZ) && ls -1 .env.bak-v114-* && grep -n '^MIN_STOP_DISTANCE_PCT=' .env"
```
Expected: the backup is listed, and the grep prints `MIN_STOP_DISTANCE_PCT=2.0`. If the grep prints anything else, stop and ask the partner.

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && sed -i 's/^MIN_STOP_DISTANCE_PCT=2.0$/MIN_STOP_DISTANCE_PCT=1.5/' .env && grep -n '^MIN_STOP_DISTANCE_PCT=\|^MIN_REWARD_PCT=\|^MIN_RISK_REWARD_RATIO=' .env"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose kill -s SIGHUP bot"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c 'from swingbot import config; print(config.MIN_STOP_DISTANCE_PCT, config.MIN_REWARD_PCT, config.MIN_RISK_REWARD_RATIO); from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT as c; print(c)'"
```
Expected: `MIN_STOP_DISTANCE_PCT=1.5`, `MIN_REWARD_PCT=2.0`, `MIN_RISK_REWARD_RATIO=1.5` in the file; then `1.5 2.0 1.5` and `2.0`. The scan also re-reads `.env` before every run (`scan_run._reload_config_before_scan`).

- [ ] **Step 5 (PASS only): Verify with the funnel line.** After the next scheduled scan completes (inside session hours), dispatch `prod-inspector` read-only to run:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --since 90m bot | grep -E 'Signal funnel|reload' | tail -5"
```
Expected: a `Signal funnel:` line timestamped after the SIGHUP, with its `-> N scenario(s) found` and `-> M shown/posted` figures. Record them in the validation results doc's Observations (commit `docs(v114): first production funnel after the flip`). On data like 2026-09-30's, expect N >= 1. A small N is the measured answer the spec anticipated (1 scenario today). Do not change any threshold because of it. If the scan errors, or `found` is 0 across a full session while the replay predicted otherwise, restore the backup (`cp .env.bak-v114-<stamp> .env && docker compose kill -s SIGHUP bot`) and ask the partner.

- [ ] **Step 6 (PASS only): Mirror check.** The production edit is mirrored by V114-14's `.env.example` commit. Confirm that `grep -n "^MIN_STOP_DISTANCE_PCT=" .env.example` prints `1.5` on `main`, and that no other production file was changed. The task is done only after this check.
