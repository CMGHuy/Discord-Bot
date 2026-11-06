# v191 — Confluence ATR-band stops: Part 4 — docs, the measurement runs, the record, Part B impact, release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V191-21:" -A 260 <this file>`.

**Spec:** [2026-10-24-v191-confluence-atr-band-stops-design.md](../specs/2026-10-24-v191-confluence-atr-band-stops-design.md)
**Index:** [2026-10-24-v191-confluence-atr-band-stops_0-index.md](2026-10-24-v191-confluence-atr-band-stops_0-index.md) — Goal, Architecture, § Global Constraints, § Contracts, § Review Focus, § Parallelisation and the task ledger bind every task below; this part never changes a shared name, signature or path.
**Previous:** [part 3b, V191-16..V191-18](2026-10-24-v191-confluence-atr-band-stops_3b-funnel-tail-driver-and-impact-report.md) — the driver `scripts/backtest/measure_atr_band_stop.py` and the `--side` impact report this part runs.
**Worktree:** `.claude/worktrees/2026-10-24-v191-confluence-atr-band-stops` (branch of the same name, created by V191-1). The controller enters it as the session root (`EnterWorktree`), so every relative path below is a worktree path. Never `cd` in Bash; V191-25 uses `git -C` with absolute paths.

This part covers the docs and their Codex mirror (V191-19) and the pre-registered measurement: Stage −1 for both arms, then arm K's chain and arm R's chain (V191-20..V191-22). The Holm family, the result record, the ledger rows and, on a fail, the closed rows (V191-23), Part B's descriptive impact on the live book (V191-24) and the release with the plan's single full-suite run and the merge (V191-25) are in part 4b, `2026-10-24-v191-confluence-atr-band-stops_4b-record-impact-and-release.md` (split to stay under the 1500-line cap).

Names consumed from earlier parts (all created there, verified against the part files): the driver CLI `--arm K|R --stage -1|0|1|2|3 --family --out-dir --preregistration --tickers --workers --resamples --data-source alpaca --instrument v1`, its output names `2026-10-24-v191-arm{K|R}-stage{M1|0|1|2|3}.json`, `2026-10-24-v191-arm{K|R}-{census-train|train|fold2023|validation}-rows.json`, `2026-10-24-v191-family.json`, all under `docs/superpowers/results/v191/`, and its progress file `logs/measure_atr_band_stop.<arm>.<census|rows>.progress` (V191-17); the stage JSON keys written by `atr_band_funnel` (V191-15, V191-16); `short_gap_sizing_impact.py --side long` (V191-18); the Field help text of `CONFLUENCE_ATR_STOP_FLOOR` ending `"Unmeasured; Keep 0 until the partner decides."` (V191-2); the coupling log text `needs LONG_GAP_SIZING and SHORT_GAP_SIZING both on` (V191-3); the alert copy `ATR-band stop ...` (V191-13).

## Rules for every measurement task (V191-20..V191-23)

- **Invoke the `backtest-gate` skill before every `measure_atr_band_stop.py` command**, not after.
- **Every driver command carries the three variables on the same line** (index § Global Constraints):

  ```bash
  MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py <args>
  ```

  The driver pins `--data-source alpaca` and `--instrument v1` by default and refuses anything else; pass neither flag with another value.
- **Dispatch the `backtest-runner` agent for every stage command** (Stages −1, 0, 1, 2 and 3: each replays bars or bootstraps three cells and can pass 15 minutes). Give it the exact command, the worktree path, the progress file `logs/measure_atr_band_stop.<arm>.<census|rows>.progress` and the wall-time estimate from V191-20 Step 4. **One runner at a time**, never two, never overlapping V191-24's database work on CPU. `--family` (V191-23) reads three small files and runs inline.
- **Frozen code.** From V191-20's first commit to the last stage file of V191-22, make no edit under `swingbot/` or `scripts/`, and never merge `main` into the worktree: the rows depend on the code. Before each run, `git status --short -- swingbot/ scripts/` is empty.
- **A stage that does not advance closes that arm**: `refused:zero-diff` (Stage −1), `UNDERPOWERED` (Stage 0), `NO_ELIGIBLE_CELL` (Stage 1), `FAIL` (Stage 2 or 3). Record it as measured and go where the task says. Never widen a window, add a cell, change a threshold or the MDE ceiling, delete a stage file, or re-run Stage 3. Stages −1..2 are deterministic; re-running one is allowed only to recover from a crash, and the driver then reuses the rows file it already saved.
- **The frozen rules part 3 built, honoured as written:** Stage −1 closes a cell `refused:zero-diff` when its floor moves no plan, and the arm is `REACHABLE` when any cell is; Stage 0 refuses per cell (MDE over +0.10R), and the arm is `POWERED` when any cell is; Stage 1 picks only among Stage 0's powered cells, but every grid cell (0.75, 1.0, 1.5) is a plateau neighbour; the plateau tolerance is `backtest_wf.PLATEAU_TOLERANCE_R` = 0.03R; the decision stratum is floor-moved alone.
- **Numbers come only from the stage JSON files.** Invoke the `pooled-numbers` skill before quoting any ΔExpR, win rate or N in a results doc, a commit message, the closed table or the ledger.
- **Rows files are evidence and are committed** (v139 precedent) when each is under 50 MB. A rows file of 50 MB or more is not committed: add its repo-relative path to `.git/info/exclude` (local only, never a committed change), and record its size and `sha256sum` in the results doc.
- **The driver enforces stage order.** When it prints `refused: ...`, read the message and stop; never work around it.
- No knob goes live and no default changes: `CONFLUENCE_ATR_STOP_FLOOR` stays `"0"`, `CONFLUENCE_ATR_TARGET_MODE` `"rechoose"`, `LONG_GAP_SIZING` `"false"`, whatever the verdicts.

## The stage renderer (used by V191-20..V191-22)

Each measurement task prints its markdown tables with the same throw-away snippet, so numbers reach the results doc mechanically, never retyped. It lives in the session scratchpad, is never committed, and each task repeats it in full.

# Phase 10 — Docs

### Task V191-19: Docs: known-traps, architecture, AGENTS.md

**Model:** haiku — documentation only, with the exact text written below; no code and no judgement beyond placing it.

**Files:**
- Modify: `docs/claude/known-traps.md` (one pointer bullet at the end of `## Stop floor and 2% cap: the empty band, and the v115 clamp`, and a new section directly after it)
- Modify: `docs/claude/architecture.md` (the `## Module map` sentence on `core/market/`, and one bullet in `## Plan engine, registry and scan pipeline`)
- Modify: `AGENTS.md` (the condensed `known-traps.md` line under "Read the `docs/claude/` file before acting")

**Interfaces:**
- Consumes: what V191-2..V191-13 built — `swingbot/core/market/atr_band.py` (V191-7), `builders._plan_geometry` / `confluence_atr_band_stop` (V191-8), `build_scenarios(band=)` and `Scenario.atr14_pct` (V191-9), `analyze._band_live` and the `band_no_atr` log line (V191-10), `gap_sizing.BAND_KEY` / `band_sizing_distance` and `stop_scope.band_sizing_verdict` (V191-11), `analyze._sizing_reject_reason` (V191-12), `presentation/band_stop.band_stop_line` (V191-13), `config.enforce_atr_band_coupling` and `system._coupling_problem` (V191-3), `TradePlanV2.stop_moved_by` (V191-4), the long gap stamp keys (V191-5).
- Produces: nothing a later task reads by name. The new known-traps section points at the results doc for the verdict, so V191-23 never edits it.

Before writing, confirm every name below exists in the worktree (each is created by an earlier task of this plan):

```bash
git grep -n "def raw_atr14_pct\|def band_stop\|def band_for" -- swingbot/core/market/atr_band.py
git grep -n "def _plan_geometry\|def confluence_atr_band_stop\|def arm_k_today_stop" -- swingbot/core/planning/builders.py
git grep -n "def enforce_atr_band_coupling" -- swingbot/config.py
git grep -n "def _coupling_problem" -- swingbot/admin/api_v1/system.py
git grep -n "def band_sizing_verdict" -- swingbot/core/planning/stop_scope.py
git grep -n "BAND_KEY = \|def band_sizing_distance\|def worst_fill_distance" -- swingbot/core/planning/gap_sizing.py
git grep -n "def _band_live\|def _sizing_reject_reason" -- swingbot/core/scanning/analyze.py
git grep -n "def band_stop_line" -- swingbot/core/presentation/band_stop.py
git grep -n "stop_moved_by" -- swingbot/core/planning/plan_types.py
```

Expected: at least one hit per command. A command with no hit means an earlier task is missing from this worktree: stop and report it.

- [ ] **Step 1: Add the pointer to the v115 section**

In `docs/claude/known-traps.md`, at the end of `## Stop floor and 2% cap: the empty band, and the v115 clamp` (after the bullet that starts `- v114 (a 1.5-2.0 band, measured before shipping)`), append this bullet:

```markdown
- **v191 can replace this band on confluence plans.** With
  `CONFLUENCE_ATR_STOP_FLOOR` above 0 the percent band, the admission floor
  and the clamp above all step aside for that plan, and an ATR band plus a
  dollar rule take their place: next section.
```

- [ ] **Step 2: Add the v191 section directly after it**

Insert this section between the end of the v115 section and `## Futures skipped for dollar volume is deliberate (v115)`:

```markdown
## Confluence ATR-band stops (v191): inert by default, coupled to gap sizing

Three knobs, all off by default: `CONFLUENCE_ATR_STOP_FLOOR` (`k`, `"0"`),
`CONFLUENCE_ATR_TARGET_MODE` (`rechoose` = arm R, `keep` = arm K) and
`LONG_GAP_SIZING` (`"false"`). With all three at default, replay rows and
plan dicts are byte-identical to before v191, pinned by the goldens in
`tests/fixtures/v191/`. A golden that moves is a behaviour change, never a
fixture to refresh.

- **The ATR is raw Wilder ATR14 of completed bars**
  (`market/atr_band.raw_atr14_pct`), never `levels.atr_floor_pct` or
  `Scenario.atr_floor_pct`: those are already multiplied by the horizon's
  `atr_stop_multiple` and would make the band 1.5-2x too wide. Live reads
  `strategy_pass.completed_frame(df, now)` (`analyze._band_live`); replay
  reads `window`. The value rides on `Scenario.atr14_pct` from admission to
  the builder, so the two always agree.
- **Band stop:** `d < k x a` moves the stop out to the floor, `d > 2 x a`
  pulls it in to the ceiling, otherwise the level stands
  (`stop_moved_by` = `floor` / `ceiling` / `untouched` on the plan doc).
  Moved stops round away from entry to the tick (0.01, or 0.0001 under $1).
  Computed once at creation: a SIGHUP or knob flip never rewrites an open or
  pending plan.
- **What steps aside for a band plan:** `MIN_STOP_DISTANCE_PCT`, the max-stop
  gate `max(MAX_STOP_LOSS_PCT, horizon max_risk_pct)`, the v115 clamp, and
  the 2% `risk_cap` reject in `attach_plan_v2`. The plan stores
  `stop_ceiling_pct = band distance + 0.25`, which `plan_stop_ceiling` and
  `PlanManager._step_pending` already read. A stop-entry fill past that
  headroom is still cancelled `risk_cap`, as in v115.
- **The dollar rule replaces the price caps.** Shares are sized on
  `gap_sizing.band_sizing_distance`: the larger of the worst accepted fill to
  the stop (`stop x c / (100 - c)` long, `stop x c / (100 + c)` short) and
  the p99 gap allowance, floored to 0.01 shares. A size of 0.00 is
  `band_size_zero`; a non-`risk_pct` sizing mode, a sizing error or an
  overshoot is `risk_sizing`. The distance rides in the `gap_sizing` stamp
  (`band_sizing_distance` key), so alert, engine and paper book share one
  number. A band long gets a stamp even with `LONG_GAP_SIZING` off (rule
  `stop`).
- **Rejections log the usual line.** `band_no_target` (arm R),
  `band_rr_drop` (arm K), `band_size_zero` and `risk_sizing` print
  `plan rejected (<reason>, ...)` through `scan_run._skip_rejected_plan`.
  `band_no_atr` (ATR missing: today's admission and geometry apply) logs its
  own INFO line containing `plan rejected (band_no_atr`. On a quiet day with
  the floor on, grep `plan rejected (band_` before suspecting data.
- **Coupling.** A live floor is honoured only with `LONG_GAP_SIZING` and
  `SHORT_GAP_SIZING` both on. At import and at every SIGHUP reload
  `config.enforce_atr_band_coupling()` sets the floor to 0 and logs an ERROR
  containing `needs LONG_GAP_SIZING and SHORT_GAP_SIZING both on`; the admin
  settings save and preview return 400 `invalid` (`system._coupling_problem`).
  A floor that "does nothing" in production is this guard first.
  Replay and measurement set knobs through `arms.knobs.apply_knobs`, which
  skips the load hook, so measurement is uncoupled by design.
- **Legacy replay gates.** Under `CONFLUENCE_GATES` the replay builds plans
  with `ScanParams.from_config()`, so the band knobs reach the builder only
  through config globals (`apply_knobs`), never through a
  `dataclasses.replace(params, ...)`.
- **Heat is unchanged.** Candidate heat and the correlated cap still count the
  configured `risk_pct`, and open trades count `|entry - stop| x shares`, so
  a wider stop with fewer shares buys no extra heat. Heat does not add the gap
  allowance (disclosed in the spec).
- **v114 is overridden for the measurement only.** The partner decides again
  before any band knob goes live; the verdict is in
  `docs/superpowers/results/2026-10-24-v191-atr-band-stops.md`.
- **Part B (`LONG_GAP_SIZING`)** mirrors v183 for longs with the p99
  *down*-gap (`gap_stats` keys `p99_down_gap_pct`, `n_down`; stamp keys
  `down_gap_p99_pct`, `n_down_gaps`; fewer than 60 down-gaps: sized on the
  stop). R stays measured on the stop; only the share count shrinks. A gap
  beyond the ticker's own p99 can still exceed the budget (accepted by the
  partner). The alert shows `ATR-band stop ...` on band plans and the gap
  line on gap-sized longs.
```

- [ ] **Step 3: Architecture**

In `docs/claude/architecture.md`, `## Module map`, replace

```markdown
  (everything computed from bars — indicators, levels, strategies, entry
  filters), `core/planning/` (plan construction, lifecycle and sizing —
```

with

```markdown
  (everything computed from bars — indicators, levels, strategies, entry
  filters; v191 `atr_band.py` is the pure ATR-band stop arithmetic shared by
  admission, the builder, the live scan and the replay), `core/planning/`
  (plan construction, lifecycle and sizing —
```

In `## Plan engine, registry and scan pipeline`, directly before the bullet that starts `- **Badges/registry:**`, insert:

```markdown
- **Confluence ATR-band path (v191, off by default).** With
  `CONFLUENCE_ATR_STOP_FLOOR` above 0, `levels.build_scenarios(..., band=)`
  drops the percent stop gates and stamps `Scenario.atr14_pct`;
  `builders.build_confluence_plan` asks `_plan_geometry` for the band stop
  (arm R re-selects TP1, arm K keeps today's TP1 and drops under the minimum
  R:R); `analyze.attach_plan_v2` stamps the band sizing before its dollar
  check (`_sizing_reject_reason`). Trap list and coupling:
  `known-traps.md` § Confluence ATR-band stops (v191).
```

- [ ] **Step 4: The Codex mirror**

In `AGENTS.md`, replace

```markdown
- `known-traps.md`: data caching (v171: every provider call goes through
  `core/marketdata/shared/`, guard test), scan output, embeds, the 2% stop
  cap/clamp, the liquidity floor, production `.env` (never `sed -i`).
```

with

```markdown
- `known-traps.md`: data caching (v171: every provider call goes through
  `core/marketdata/shared/`, guard test), scan output, embeds, the 2% stop
  cap/clamp and the v191 ATR-band stop path (a live floor needs both
  gap-sizing flags, else it is zeroed at load), the liquidity floor,
  production `.env` (never `sed -i`).
```

- [ ] **Step 5: Verify**

```bash
python scripts/dev/doc_section.py docs/claude/known-traps.md "Confluence ATR-band stops (v191): inert by default, coupled to gap sizing" | head -3
python scripts/dev/doc_section.py docs/claude/architecture.md "Plan engine, registry and scan pipeline" | grep -c "Confluence ATR-band path (v191"
grep -c "v191 ATR-band stop path" AGENTS.md
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py changed
```

Expected: the section heading prints; `1`; `1`; `0 failed` in both runs (`changed` selects whatever tests read these docs).

- [ ] **Step 6: Commit**

```bash
git add docs/claude/known-traps.md docs/claude/architecture.md AGENTS.md
git commit -m "docs(v191): known-traps and architecture for the ATR-band stop path and its coupling; AGENTS.md mirror

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 11 — Measurement runs

Order: V191-20 first (the frozen-block record, then the census for both arms). Then arm K's chain, V191-21, because arm K is the primary arm. Then arm R's chain, V191-22. One `backtest-runner` at a time throughout. An arm closed at Stage −1 skips its whole chain, and its record is written in V191-23.

### Task V191-20: Stage −1 for both arms via `backtest-runner`

**Model:** sonnet — runs a finished driver and copies its output through a fixed renderer; the judgement is limited to the stop-and-report sanity checks spelt out below.

**Files:**
- Create: `docs/superpowers/results/2026-10-24-v191-atr-band-stops.md` (the frozen block and the Stage −1 section; V191-21..V191-23 append to it)
- Create (generated by the driver): `docs/superpowers/results/v191/2026-10-24-v191-armK-census-train-rows.json`, `docs/superpowers/results/v191/2026-10-24-v191-armK-stageM1.json`, `docs/superpowers/results/v191/2026-10-24-v191-armR-census-train-rows.json`, `docs/superpowers/results/v191/2026-10-24-v191-armR-stageM1.json`
- Scratch, never committed (`logs/` is git-ignored): `logs/v191/render_stage.py`, `logs/v191/smoke/`

**Interfaces:**
- Consumes: the driver `scripts/backtest/measure_atr_band_stop.py` (V191-17) and `atr_band_funnel.stage_minus1` output keys (V191-15): `stage`, `arm`, `verdict`, `reachable_cells`, `cell_verdicts`, `cells`, `totals` (`plans_today`, `arm_s_overlap`, `atr_buckets`, `atr_missing`, `cells.<key>` with `plans`, `floor`, `ceiling`, `untouched`, `newly_admitted`, `removed`, `band_rr_drop`, `band_no_target`, `band_size_zero`, `baseline_stop_exits`, `reversal`, `concurrency` {`max`, `p95`, `heat_slots`, `days_over_heat_slots`}), `by_stratum`, `identical_adjacent`, plus `instrument` and `data_source` stamped by `run_stage`.
- Produces: each arm's Stage −1 verdict file, which V191-21 and V191-22 consume through the driver's `REQUIRES` chain; the results doc that V191-21..V191-23 extend.

- [ ] **Step 1: Pre-flight — the code is complete and nothing closed covers this**

```bash
git status --short                                   # expected: empty
git log --oneline main..HEAD | head -30              # expected: the V191-1..V191-19 commits
git grep -n "PLATEAU_TOLERANCE_R = 0.03" -- swingbot/core/backtesting/backtest_wf.py
git grep -n "DATA_SOURCE = \"alpaca\"\|INSTRUMENT = \"v1\"\|MDE_CEILING_R = 0.10" -- swingbot/core/backtesting/atr_band_funnel.py
python scripts/backtest/measure_atr_band_stop.py --help
ls docs/superpowers/results/v191/ 2>/dev/null       # expected: absent or empty
```

Expected: every grep hits; `--help` lists `--arm`, `--stage`, `--family`, `--preregistration`, `--data-source {alpaca}` and `--instrument`; no v191 stage file exists yet. A stage file that already exists means a run happened outside this task: stop and report it.

Invoke `backtest-gate`. Then check the closed table:

```bash
grep -n "ATR14 floor\|ATR floor\|k x ATR\|k × ATR\|v191" docs/claude/backtest-methodology.md
```

Expected: no row closes "an ATR14 floor `k × ATR` with a `2 × ATR` ceiling on confluence plans". The spec's § Not a re-run argues why v139 arm S, v139 arm D, v114, v104 Part A and v103 A are different mechanisms. If another row does close this mechanism, stop and ask the partner (`AskUserQuestion`, one question, recommended option first: "Stop: v191 is a re-run of <row>").

- [ ] **Step 2: Write the renderer (scratch)**

Create `logs/v191/render_stage.py` with exactly this content. It prints the markdown tables for one stage JSON file, so no number is ever retyped:

```python
"""v191 stage renderer (scratch, never committed): markdown tables from one stage JSON."""
import json
import sys

CENSUS = ("plans", "floor", "ceiling", "untouched", "newly_admitted", "removed", "band_rr_drop",
          "band_no_target", "band_size_zero", "baseline_stop_exits", "reversal")
SPLITS = ("by_moved_by", "by_direction", "by_horizon")


def fmt(value):
    if value is None:
        return "—"
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def table(head, rows):
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for row in rows:
        print("| " + " | ".join(fmt(x) for x in row) + " |")
    print()


def census(totals, verdicts):
    print(f"plans today {totals['plans_today']}; arm S overlap {totals['arm_s_overlap']}; "
          f"ATR missing {totals['atr_missing']}\n")
    table(("cell", "verdict", *CENSUS, "conc max", "conc p95", "days over heat slots"),
          [(key, verdicts.get(key, ""), *(cell[x] for x in CENSUS), cell["concurrency"]["max"],
            cell["concurrency"]["p95"], cell["concurrency"]["days_over_heat_slots"])
           for key, cell in totals["cells"].items()])
    table(("ATR14 % bucket", "rows"), list(totals["atr_buckets"].items()))


def reports(reps):
    rows = []
    for rep in reps:
        fm, dollars = rep["floor_moved"], rep["dollars"]["component"]
        rows.append((rep["cell"], fm["n_baseline"], fm["n_component"], fm["delta_expr"],
                     fm["delta_expr_lo95"], fm["delta_expr_hi95"], fm["delta_wr_pp"],
                     rep["volume"]["change_pct"], rep["median_planned_rr"]["baseline"],
                     rep["median_planned_rr"]["component"],
                     rep["stop_distance"]["median_atr"]["baseline"],
                     rep["stop_distance"]["median_atr"]["component"],
                     rep["exits"]["component"]["early_stops"],
                     rep["exits"]["component"]["fill_beyond_ceiling"],
                     dollars["exceed_bullish"], dollars["exceed_bearish"]))
    table(("cell", "N base", "N cell", "ΔExpR", "lo95", "hi95", "ΔWR pp", "volume %", "RR base",
           "RR cell", "stop ATR base", "stop ATR cell", "early stops", "fill beyond ceiling",
           "$ exceed long", "$ exceed short"), rows)
    for rep in reps:
        for split in SPLITS:
            table((f"{rep['cell']} {split}", "N base", "N cell", "ΔExpR", "ΔWR pp"),
                  [(name, s["n_baseline"], s["n_component"], s["delta_expr"], s["delta_wr_pp"])
                   for name, s in rep[split].items()])


def stage0(d):
    table(("cell", "stratum N", "paired N", "newly admitted", "observed N", "target N", "MDE R"),
          [(c["cell"], c["stratum_n"], c["paired_n"], c["newly_admitted_n"], c["observed_n"],
            c["target_n"], c["mde_r"]) for c in d["cells"]])
    print(f"powered cells {d['powered_cells']} (ceiling {d['mde_ceiling_r']}R, power {d['power']})")


def stage1(d):
    rows = []
    for c in d["cells"]:
        clause = {x["name"]: x["verdict"] for x in c["gate"]["clauses"]}
        rows.append((c["cell"], c["n_baseline"], c["n_component"], c["delta_expr"],
                     clause.get("expectancy_gain"), clause.get("win_rate_floor"),
                     clause.get("volume"), c["candidate"], c["eligible"], c["plateau"]))
    table(("cell", "N base", "N cell", "ΔExpR", "expectancy_gain", "win_rate_floor", "volume",
           "candidate", "eligible", "plateau"), rows)
    print(f"selected {d['selected']}; tolerance {d['tolerance_r']}R\n")
    reports(d["reports"])


def stage2(d):
    table(("year", "N", "ΔExpR", "measurable", "positive"),
          [(f["year"], f["n"], f["delta_expr"], f["measurable"], f["positive"]) for f in d["folds"]])
    print(f"positive folds {d['positive']} of {len(d['folds'])} (needs {d['min_positive']})")


def stage3(d):
    table(("clause", "verdict", "value", "threshold", "detail"),
          [(x["name"], x["verdict"], x["value"], x["threshold"], x["detail"])
           for x in d["gate"]["clauses"]])
    print(f"permutation p {d['permutation_p']} (n {d['n_permutations']})\n")
    reports([d["report"]])


def main(path):
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    print(f"**arm {d.get('arm')} stage {d['stage']}: {d['verdict']}** "
          f"(instrument {d.get('instrument')}, data {d.get('data_source')})\n")
    if d["stage"] == -1:
        census(d["totals"], d["cell_verdicts"])
        print(f"reachable cells {d['reachable_cells']}; identical adjacent {d['identical_adjacent']}")
    else:
        {0: stage0, 1: stage1, 2: stage2, 3: stage3}[d["stage"]](d)


if __name__ == "__main__":
    main(sys.argv[1])
```

- [ ] **Step 3: Write the frozen block into the results doc, and commit it before any run**

```bash
git log -1 --format=%h -- docs/superpowers/specs/2026-10-24-v191-confluence-atr-band-stops-design.md
```

Create `docs/superpowers/results/2026-10-24-v191-atr-band-stops.md` with this content, filling `<spec hash>` from the command above (a value read from git, not a choice):

```markdown
# v191 — Confluence ATR-band stops: results

**Spec (the pre-registration):** `docs/superpowers/specs/2026-10-24-v191-confluence-atr-band-stops-design.md`, last changed in `<spec hash>`. Stage 3 runs only with `--preregistration` naming that file.
**Plan:** `docs/superpowers/plans/2026-10-24-v191-confluence-atr-band-stops_0-index.md` (§ Global Constraints carries the frozen block below).
**Driver:** `scripts/backtest/measure_atr_band_stop.py`; stage files under `docs/superpowers/results/v191/`.

## Frozen before any run

- Claim: on confluence plans whose stop the floor moves, an ATR band (floor `k × ATR14`, ceiling `2 × ATR14`) with fixed-dollar sizing raises expectancy under the v92 harvest gate. Two arms, never pooled: arm K (keep TP1, drop under the minimum R:R) is primary; arm R (re-choose TP1) is second; Holm across the two on each arm's Stage 3 permutation p, an arm that never reached Stage 3 entering as p = 1.0; BH q reported, never gating.
- Prediction (falsifiable, per cell on the floor-moved stratum): ΔWR ≥ +4pp; arm K ΔExpR > 0; arm R ΔExpR < 0. A contradiction is recorded as a missed prediction.
- Grid `k ∈ {0.75, 1.0, 1.5}` (the partner's, uneven steps kept); ceiling `2.0 × a`, `a` = raw Wilder ATR14 / entry × 100 of completed bars through the creating bar.
- Decision stratum: floor-moved alone. Untouched and ceiling strata are reported, never counted towards a pass.
- Gate: v92 harvest (`acceptance_harvest.evaluate_harvest`): ΔExpR lower 95% bound > 0; Δ standardised WR lower bound ≥ −2.0pp; closed-trade cut ≤ 25%; permutation n = 200, p < 0.05, VALIDATION only. Week-clustered bootstrap.
- Stage −1: per-cell `refused:zero-diff` when the floor moves no plan; the arm is REACHABLE when any cell is. Stage 0: paired ΔExpR MDE on fold-train, a cell over +0.10R at power 0.80 refused; the arm is POWERED when any cell is. Stage 1: only powered cells are candidates; winner = highest ΔExpR with clauses 1–3 passing on fold-train and every existing grid neighbour within `plateau_report`'s 0.03R tolerance (all three cells are neighbours whether powered or not; an edge cell is adoptable with its one neighbour). Stage 2: folds 2021 / 2022 / 2023, at least 2 of 3 with positive ΔExpR at N ≥ 30. Stage 3: one VALIDATION shot per arm.
- Windows: fold-train 2018-06-01..2022-12-31; fold 2023 2023-01-01..2023-12-31; VALIDATION 2024-01-01..2025-12-31.
- Instrument v1; `data_source` alpaca (the v162 training-data store); universe `measure_arms.cached_universe()` with `MEASURE_ARMS_UNIVERSE=cache`; replay `gates=None` (live `ScanParams` through config).
- Frictions identical on both sides; a gap through a stop fills at the open; a fill past the stored ceiling is disclosed as `fill_beyond_ceiling`, never silently kept.
- Disclosed spec inconsistency: the spec's panel log says "0.05R tolerance frozen", while its § Gate (the binding text, after the plan-briefer correction) freezes `plateau_report`'s existing 0.03R. The § Gate text governs; the code uses 0.03R unchanged.

## Stage −1 (census, plans only, no outcome read)
```

Commit it alone:

```bash
git add docs/superpowers/results/2026-10-24-v191-atr-band-stops.md
git commit -m "docs(v191): results record -- frozen block written before any run

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Smoke run and wall-time estimate (scratch output, not evidence)**

Invoke `backtest-gate`. Run inline (three tickers, a scratch directory the driver allows):

```bash
time MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py --arm K --stage -1 --tickers 3 --out-dir logs/v191/smoke
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python -c "import sys; sys.path[:0] = ['.', 'scripts/backtest', 'scripts/data']; import measure_arms; print(len(measure_arms.cached_universe()))"
```

Expected: three `[arm K census 2018-06-01..2022-12-31] i/3 <TICKER>: <n> entries` lines with non-zero counts, a last line `arm K stage -1: <verdict> -> logs/v191/smoke/...`, and the universe size. Zero entries on all three tickers means the alpaca store is not being read (wrong `HISTORY_STORE_DIR`): stop and report.

Estimate: `census minutes ≈ smoke seconds / 3 × universe size / 60 / workers`, where `workers` is the pool size the driver printed. The full fold-train rows replay of Stage 0 runs each ticker four times (baseline and three cells, with exits), so budget about 4× the census time for it. Write both estimates into the runner briefs below.

- [ ] **Step 5: Arm K Stage −1**

Dispatch `backtest-runner` with the worktree path, the progress file `logs/measure_atr_band_stop.K.census.progress`, the estimate from Step 4, and:

```bash
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py --arm K --stage -1
```

Expected last line: `arm K stage -1: REACHABLE -> .../docs/superpowers/results/v191/2026-10-24-v191-armK-stageM1.json` (exit 0) or `arm K stage -1: refused:zero-diff -> ...` (exit 1).

- [ ] **Step 6: Arm R Stage −1**

After the arm K runner has returned, dispatch `backtest-runner` the same way with the progress file `logs/measure_atr_band_stop.R.census.progress` and:

```bash
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py --arm R --stage -1
```

Expected last line: `arm R stage -1: REACHABLE -> ...armR-stageM1.json` (exit 0) or `refused:zero-diff` (exit 1).

- [ ] **Step 7: Sanity-check both census files before anything else is read**

```bash
python - <<'PYEOF'
import json
base = "docs/superpowers/results/v191/2026-10-24-v191-arm{}-stageM1.json"
k, r = (json.load(open(base.format(a), encoding="utf-8")) for a in "KR")
problems = []
for name, d in (("K", k), ("R", r)):
    t = d["totals"]
    if (d["instrument"], d["data_source"]) != ("v1", "alpaca"):
        problems.append(f"{name}: instrument/data_source {d['instrument']}/{d['data_source']}")
    if t["plans_today"] <= 0:
        problems.append(f"{name}: no confluence plans today -- the replay found nothing")
    if d["cells"] != ["k0.75", "k1", "k1.5"]:
        problems.append(f"{name}: cells {d['cells']} are not the frozen grid")
    for key, c in t["cells"].items():
        if c["floor"] + c["ceiling"] + c["untouched"] > c["plans"]:
            problems.append(f"{name} {key}: moved counts exceed plans")
        if c["reversal"] > c["baseline_stop_exits"]:
            problems.append(f"{name} {key}: more reversals than baseline stop exits")
        if c["concurrency"]["p95"] > c["concurrency"]["max"]:
            problems.append(f"{name} {key}: concurrency p95 above max")
for field in ("plans_today", "arm_s_overlap"):
    if k["totals"][field] != r["totals"][field]:
        problems.append(f"{field} differs between arms ({k['totals'][field]} vs {r['totals'][field]}): the baseline is arm-independent")
print("\n".join(problems) or "census sane")
PYEOF
```

Expected: `census sane`. Any other line is a code bug, not a result: stop, report the lines, and run nothing further. The baseline (floor 0) does not depend on the arm, so `plans_today` and `arm_s_overlap` must match across the two files.

Then read each file's verdicts:
- `verdict == "refused:zero-diff"` closes that arm at Stage −1, budget intact: its chain (V191-21 for K, V191-22 for R) is skipped, and V191-23 records it.
- A cell whose `cell_verdicts` entry is `refused:zero-diff` is closed alone; the driver runs Stage 0 on `reachable_cells` only.
- A non-empty `identical_adjacent` is disclosed, not asked about: the spec froze the partner's grid as it is, and the plateau rule treats identical neighbours as one shape.
- `reversal` (stop exits that later reached TP1 without first breaching `k × ATR`) is outcome-adjacent: it is read once, here, and never selects `k`.

- [ ] **Step 8: Write the Stage −1 section**

```bash
python logs/v191/render_stage.py docs/superpowers/results/v191/2026-10-24-v191-armK-stageM1.json
python logs/v191/render_stage.py docs/superpowers/results/v191/2026-10-24-v191-armR-stageM1.json
ls -l docs/superpowers/results/v191/
```

Under `## Stage −1 (census, plans only, no outcome read)` in the results doc, add `### Arm K` and `### Arm R`, each with the renderer's output pasted as printed, then one sentence per arm naming its verdict, its `reachable_cells`, and that per-horizon/direction counts are in the file's `by_stratum`. Note any rows file of 50 MB or more (part rule: excluded locally, size and `sha256sum` recorded here).

- [ ] **Step 9: Commit**

```bash
git add docs/superpowers/results/v191/2026-10-24-v191-armK-census-train-rows.json docs/superpowers/results/v191/2026-10-24-v191-armK-stageM1.json docs/superpowers/results/v191/2026-10-24-v191-armR-census-train-rows.json docs/superpowers/results/v191/2026-10-24-v191-armR-stageM1.json docs/superpowers/results/2026-10-24-v191-atr-band-stops.md
git commit -m "docs(v191): Stage -1 census -- arm K <verdict> (cells <list>), arm R <verdict> (cells <list>)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

The `<verdict>` and `<list>` values are copied from the two stageM1 files. Leave out of `git add` any rows file over 50 MB (part rule).

### Task V191-21: Arm K chain, Stages 0→3

**Model:** sonnet — runs a finished driver stage by stage with fixed stop rules; the one-shot Stage 3 discipline is procedural, not a design call.

Skip this task entirely if `docs/superpowers/results/v191/2026-10-24-v191-armK-stageM1.json` carries `"verdict": "refused:zero-diff"`; V191-23 records the closed arm.

**Files:**
- Create (generated by the driver): `docs/superpowers/results/v191/2026-10-24-v191-armK-train-rows.json`, `docs/superpowers/results/v191/2026-10-24-v191-armK-stage0.json`, `docs/superpowers/results/v191/2026-10-24-v191-armK-stage1.json`, `docs/superpowers/results/v191/2026-10-24-v191-armK-fold2023-rows.json`, `docs/superpowers/results/v191/2026-10-24-v191-armK-stage2.json`, `docs/superpowers/results/v191/2026-10-24-v191-armK-validation-rows.json`, `docs/superpowers/results/v191/2026-10-24-v191-armK-stage3.json` (only the files of stages that run)
- Modify: `docs/superpowers/results/2026-10-24-v191-atr-band-stops.md` (an `## Arm K (primary)` section)
- Scratch: `logs/v191/render_stage.py` (re-created in Step 1 if absent)

**Interfaces:**
- Consumes: arm K's `stageM1.json` (`REACHABLE`, `reachable_cells`) from V191-20; the driver's stage chain (`REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}`); stage output keys from `atr_band_funnel` — Stage 0 `powered_cells`, `cells[]` {`cell`, `stratum_n`, `paired_n`, `newly_admitted_n`, `observed_n`, `target_n`, `mde_r`}; Stage 1 `selected` {`cell`, `k`} | None, `tolerance_r`, `cells[]` {`candidate`, `eligible`, `plateau`, `delta_expr`, `gate`}, `reports[]`; Stage 2 `folds[]` {`year`, `n`, `delta_expr`, `measurable`, `positive`}, `positive`; Stage 3 `gate.clauses[]`, `permutation_p`, `n_permutations`, `report`.
- Produces: arm K's last stage file, which V191-23's `--family` reads (`_closed`, `_stage3_or_none` in the driver).

- [ ] **Step 1: Re-create the renderer if it is missing**

`ls logs/v191/render_stage.py`. If absent, create it with exactly this content:

```python
"""v191 stage renderer (scratch, never committed): markdown tables from one stage JSON."""
import json
import sys

CENSUS = ("plans", "floor", "ceiling", "untouched", "newly_admitted", "removed", "band_rr_drop",
          "band_no_target", "band_size_zero", "baseline_stop_exits", "reversal")
SPLITS = ("by_moved_by", "by_direction", "by_horizon")


def fmt(value):
    if value is None:
        return "—"
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def table(head, rows):
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for row in rows:
        print("| " + " | ".join(fmt(x) for x in row) + " |")
    print()


def census(totals, verdicts):
    print(f"plans today {totals['plans_today']}; arm S overlap {totals['arm_s_overlap']}; "
          f"ATR missing {totals['atr_missing']}\n")
    table(("cell", "verdict", *CENSUS, "conc max", "conc p95", "days over heat slots"),
          [(key, verdicts.get(key, ""), *(cell[x] for x in CENSUS), cell["concurrency"]["max"],
            cell["concurrency"]["p95"], cell["concurrency"]["days_over_heat_slots"])
           for key, cell in totals["cells"].items()])
    table(("ATR14 % bucket", "rows"), list(totals["atr_buckets"].items()))


def reports(reps):
    rows = []
    for rep in reps:
        fm, dollars = rep["floor_moved"], rep["dollars"]["component"]
        rows.append((rep["cell"], fm["n_baseline"], fm["n_component"], fm["delta_expr"],
                     fm["delta_expr_lo95"], fm["delta_expr_hi95"], fm["delta_wr_pp"],
                     rep["volume"]["change_pct"], rep["median_planned_rr"]["baseline"],
                     rep["median_planned_rr"]["component"],
                     rep["stop_distance"]["median_atr"]["baseline"],
                     rep["stop_distance"]["median_atr"]["component"],
                     rep["exits"]["component"]["early_stops"],
                     rep["exits"]["component"]["fill_beyond_ceiling"],
                     dollars["exceed_bullish"], dollars["exceed_bearish"]))
    table(("cell", "N base", "N cell", "ΔExpR", "lo95", "hi95", "ΔWR pp", "volume %", "RR base",
           "RR cell", "stop ATR base", "stop ATR cell", "early stops", "fill beyond ceiling",
           "$ exceed long", "$ exceed short"), rows)
    for rep in reps:
        for split in SPLITS:
            table((f"{rep['cell']} {split}", "N base", "N cell", "ΔExpR", "ΔWR pp"),
                  [(name, s["n_baseline"], s["n_component"], s["delta_expr"], s["delta_wr_pp"])
                   for name, s in rep[split].items()])


def stage0(d):
    table(("cell", "stratum N", "paired N", "newly admitted", "observed N", "target N", "MDE R"),
          [(c["cell"], c["stratum_n"], c["paired_n"], c["newly_admitted_n"], c["observed_n"],
            c["target_n"], c["mde_r"]) for c in d["cells"]])
    print(f"powered cells {d['powered_cells']} (ceiling {d['mde_ceiling_r']}R, power {d['power']})")


def stage1(d):
    rows = []
    for c in d["cells"]:
        clause = {x["name"]: x["verdict"] for x in c["gate"]["clauses"]}
        rows.append((c["cell"], c["n_baseline"], c["n_component"], c["delta_expr"],
                     clause.get("expectancy_gain"), clause.get("win_rate_floor"),
                     clause.get("volume"), c["candidate"], c["eligible"], c["plateau"]))
    table(("cell", "N base", "N cell", "ΔExpR", "expectancy_gain", "win_rate_floor", "volume",
           "candidate", "eligible", "plateau"), rows)
    print(f"selected {d['selected']}; tolerance {d['tolerance_r']}R\n")
    reports(d["reports"])


def stage2(d):
    table(("year", "N", "ΔExpR", "measurable", "positive"),
          [(f["year"], f["n"], f["delta_expr"], f["measurable"], f["positive"]) for f in d["folds"]])
    print(f"positive folds {d['positive']} of {len(d['folds'])} (needs {d['min_positive']})")


def stage3(d):
    table(("clause", "verdict", "value", "threshold", "detail"),
          [(x["name"], x["verdict"], x["value"], x["threshold"], x["detail"])
           for x in d["gate"]["clauses"]])
    print(f"permutation p {d['permutation_p']} (n {d['n_permutations']})\n")
    reports([d["report"]])


def main(path):
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    print(f"**arm {d.get('arm')} stage {d['stage']}: {d['verdict']}** "
          f"(instrument {d.get('instrument')}, data {d.get('data_source')})\n")
    if d["stage"] == -1:
        census(d["totals"], d["cell_verdicts"])
        print(f"reachable cells {d['reachable_cells']}; identical adjacent {d['identical_adjacent']}")
    else:
        {0: stage0, 1: stage1, 2: stage2, 3: stage3}[d["stage"]](d)


if __name__ == "__main__":
    main(sys.argv[1])
```

- [ ] **Step 2: Stage 0 (the fold-train rows replay, the long run)**

`git status --short -- swingbot/ scripts/` is empty. Invoke `backtest-gate`. Dispatch `backtest-runner` with the worktree path, the progress file `logs/measure_atr_band_stop.K.rows.progress`, the Stage 0 estimate from V191-20 Step 4, and:

```bash
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py --arm K --stage 0
```

Expected last line: `arm K stage 0: POWERED -> ...armK-stage0.json` (exit 0) or `UNDERPOWERED` (exit 1). Then:

```bash
python logs/v191/render_stage.py docs/superpowers/results/v191/2026-10-24-v191-armK-stage0.json
```

Stop-and-report-a-bug conditions (never results): a cell with `paired_n > stratum_n`; `observed_n == 0` on a reachable cell; a `cells[]` entry for a cell not in Stage −1's `reachable_cells`. `UNDERPOWERED` closes arm K at Stage 0, budget intact: go to Step 7, then Step 9.

- [ ] **Step 3: Stage 1 (bootstrap over the saved train rows)**

Invoke `backtest-gate`. Dispatch `backtest-runner` (progress: the driver's per-cell lines; no replay happens) with:

```bash
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py --arm K --stage 1
```

Expected last line: `arm K stage 1: SELECTED -> ...` (exit 0) or `NO_ELIGIBLE_CELL` (exit 1). Render it:

```bash
python logs/v191/render_stage.py docs/superpowers/results/v191/2026-10-24-v191-armK-stage1.json
```

Stop-and-report-a-bug conditions: `tolerance_r != 0.03`; `cells` does not list all three of `k0.75`, `k1`, `k1.5`; `candidate` is True for a cell not in Stage 0's `powered_cells` (or False for one in it); `selected` names a cell that is not `candidate`, `eligible` and `plateau` all at once; a `reports[]` entry whose `floor_moved.n_component` is 0 while its Stage −1 `floor` count is non-zero (the rows are not the census replay).

`NO_ELIGIBLE_CELL` closes arm K at Stage 1, budget intact: go to Step 7, then Step 9.

- [ ] **Step 4: Commit Stages 0 and 1 before Stage 2**

```bash
ls -l docs/superpowers/results/v191/
git add docs/superpowers/results/v191/2026-10-24-v191-armK-train-rows.json docs/superpowers/results/v191/2026-10-24-v191-armK-stage0.json docs/superpowers/results/v191/2026-10-24-v191-armK-stage1.json
git commit -m "docs(v191): arm K Stage 0 <verdict>, Stage 1 <verdict, selected cell>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Leave a rows file of 50 MB or more out of `git add` (part rule). Add only files that exist.

- [ ] **Step 5: Stage 2 (the 2023 fold replays the selected k only)**

Invoke `backtest-gate`. Dispatch `backtest-runner` with the progress file `logs/measure_atr_band_stop.K.rows.progress` and:

```bash
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py --arm K --stage 2
```

Expected last line: `arm K stage 2: PASS -> ...` (exit 0) or `FAIL` (exit 1). Render:

```bash
python logs/v191/render_stage.py docs/superpowers/results/v191/2026-10-24-v191-armK-stage2.json
```

Stop-and-report-a-bug: `folds` years other than 2021, 2022, 2023; a fold with `positive` True and `measurable` False. Commit:

```bash
git add docs/superpowers/results/v191/2026-10-24-v191-armK-fold2023-rows.json docs/superpowers/results/v191/2026-10-24-v191-armK-stage2.json
git commit -m "docs(v191): arm K Stage 2 walk-forward -- <PASS|FAIL>, <positive> of 3 folds positive

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

`FAIL` closes arm K at Stage 2, budget intact: go to Step 7, then Step 9.

- [ ] **Step 6: Stage 3 — arm K's one VALIDATION shot**

Pre-flight (nothing here reads VALIDATION):

```bash
git status --short docs/superpowers/results/v191/          # expected: empty, every earlier stage file committed
ls docs/superpowers/results/v191/ | grep "armK-stage3"     # expected: nothing
git log --oneline -1 -- docs/superpowers/specs/2026-10-24-v191-confluence-atr-band-stops-design.md   # expected: the hash named in the results doc's header
```

Invoke `backtest-gate` and state in the session: the selected cell and `k` (from `armK-stage1.json` `selected`), and that this is arm K's single VALIDATION shot. Dispatch `backtest-runner` with the progress file `logs/measure_atr_band_stop.K.rows.progress` and:

```bash
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py --arm K --stage 3 --preregistration docs/superpowers/specs/2026-10-24-v191-confluence-atr-band-stops-design.md
```

Expected last line: `arm K stage 3: PASS -> ...` (exit 0) or `FAIL` (exit 1). **Whatever it prints is final.**
- A crash after `armK-validation-rows.json` was written: run the same command again; the driver reuses the saved rows and replays nothing.
- A crash before that file exists: nothing was read; run it again.
- `refused: ... one VALIDATION shot is spent`: the shot already ran. Stop and report; never delete the file.

Commit the generated files before interpreting them:

```bash
git add docs/superpowers/results/v191/2026-10-24-v191-armK-validation-rows.json docs/superpowers/results/v191/2026-10-24-v191-armK-stage3.json
git commit -m "docs(v191): arm K Stage 3 VALIDATION -- <PASS|FAIL>, shot spent

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Check the prediction (recorded, never gating)**

```bash
python - <<'PYEOF'
import json, pathlib
d = pathlib.Path("docs/superpowers/results/v191")
reps = []
s1 = d / "2026-10-24-v191-armK-stage1.json"
if s1.exists():
    reps += [("fold-train", r) for r in json.loads(s1.read_text(encoding="utf-8"))["reports"]]
s3 = d / "2026-10-24-v191-armK-stage3.json"
if s3.exists():
    reps.append(("VALIDATION", json.loads(s3.read_text(encoding="utf-8"))["report"]))
for window, r in reps:
    fm = r["floor_moved"]
    wr, dx = fm["delta_wr_pp"], fm["delta_expr"]
    hit_wr = "hit" if wr is not None and wr >= 4.0 else "MISSED"
    hit_x = "hit" if dx is not None and dx > 0 else "MISSED"
    print(f"{window} {r['cell']}: dWR {wr} pp (>= +4: {hit_wr}); dExpR {dx} R (arm K > 0: {hit_x})")
PYEOF
```

If Stage 0 closed the arm (no Stage 1 file), the script prints nothing: write "prediction not scored (closed before Stage 1)".

- [ ] **Step 8: Sanity of the dollar invariant on the component side (disclosure)**

In each rendered report, `$ exceed long` / `$ exceed short` on the component side counts band trades whose dollar loss went past the fixed budget. Under the dollar rule that can only come from a gap through the stop beyond the p99 allowance. If a cell shows exceedances while its `exits.component.gap_through` is 0, that is a sizing bug: stop and report. Otherwise disclose the counts as they are.

- [ ] **Step 9: Write the arm K section and commit**

Invoke `pooled-numbers`. Append `## Arm K (primary)` to `docs/superpowers/results/2026-10-24-v191-atr-band-stops.md` with:
- **Verdict line:** the stage arm K ended at, its verdict, and whether its VALIDATION shot is spent.
- `### Stage 0`, `### Stage 1`, `### Stage 2`, `### Stage 3`: the renderer output for each stage that ran, pasted as printed (`python logs/v191/render_stage.py <file>`), with the selection rule quoted from the frozen block under Stage 1.
- `### Prediction`: the Step 7 lines, and "missed" spelt out wherever a line says MISSED.
- `### Disclosures`: the Step 8 counts; the newly admitted count and per-day alert count (`report.newly_admitted`); the top-two-horizon share; the regime2 cut (descriptive). Point to the JSON for anything not tabled.
- **Observations**, plainly: 1R is wider on a floor-moved plan, so the same price move is a smaller R, and ΔExpR in R equals ΔExpR in dollars only under the fixed-dollar sizing the rule enforces; whether one horizon carries the result; how many component fills went past the stored ceiling (live would cancel them).

```bash
git add docs/superpowers/results/2026-10-24-v191-atr-band-stops.md
git commit -m "docs(v191): arm K record -- <verdict at stage>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V191-22: Arm R chain, Stages 0→3

**Model:** sonnet — runs a finished driver stage by stage with fixed stop rules; the one-shot Stage 3 discipline is procedural, not a design call.

Runs after V191-21 has finished (one runner at a time; arm K, the primary arm, runs first). Skip this task entirely if `docs/superpowers/results/v191/2026-10-24-v191-armR-stageM1.json` carries `"verdict": "refused:zero-diff"`; V191-23 records the closed arm.

**Files:**
- Create (generated by the driver): `docs/superpowers/results/v191/2026-10-24-v191-armR-train-rows.json`, `docs/superpowers/results/v191/2026-10-24-v191-armR-stage0.json`, `docs/superpowers/results/v191/2026-10-24-v191-armR-stage1.json`, `docs/superpowers/results/v191/2026-10-24-v191-armR-fold2023-rows.json`, `docs/superpowers/results/v191/2026-10-24-v191-armR-stage2.json`, `docs/superpowers/results/v191/2026-10-24-v191-armR-validation-rows.json`, `docs/superpowers/results/v191/2026-10-24-v191-armR-stage3.json` (only the files of stages that run)
- Modify: `docs/superpowers/results/2026-10-24-v191-atr-band-stops.md` (an `## Arm R (second)` section)
- Scratch: `logs/v191/render_stage.py` (re-created in Step 1 if absent)

**Interfaces:**
- Consumes: arm R's `stageM1.json` (`REACHABLE`, `reachable_cells`) from V191-20; the driver's stage chain (`REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}`); stage output keys from `atr_band_funnel` — Stage 0 `powered_cells`, `cells[]` {`cell`, `stratum_n`, `paired_n`, `newly_admitted_n`, `observed_n`, `target_n`, `mde_r`}; Stage 1 `selected` {`cell`, `k`} | None, `tolerance_r`, `cells[]` {`candidate`, `eligible`, `plateau`, `delta_expr`, `gate`}, `reports[]`; Stage 2 `folds[]` {`year`, `n`, `delta_expr`, `measurable`, `positive`}, `positive`; Stage 3 `gate.clauses[]`, `permutation_p`, `n_permutations`, `report`.
- Produces: arm R's last stage file, which V191-23's `--family` reads (`_closed`, `_stage3_or_none` in the driver).

- [ ] **Step 1: Re-create the renderer if it is missing**

`ls logs/v191/render_stage.py`. If absent, create it with exactly this content:

```python
"""v191 stage renderer (scratch, never committed): markdown tables from one stage JSON."""
import json
import sys

CENSUS = ("plans", "floor", "ceiling", "untouched", "newly_admitted", "removed", "band_rr_drop",
          "band_no_target", "band_size_zero", "baseline_stop_exits", "reversal")
SPLITS = ("by_moved_by", "by_direction", "by_horizon")


def fmt(value):
    if value is None:
        return "—"
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def table(head, rows):
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for row in rows:
        print("| " + " | ".join(fmt(x) for x in row) + " |")
    print()


def census(totals, verdicts):
    print(f"plans today {totals['plans_today']}; arm S overlap {totals['arm_s_overlap']}; "
          f"ATR missing {totals['atr_missing']}\n")
    table(("cell", "verdict", *CENSUS, "conc max", "conc p95", "days over heat slots"),
          [(key, verdicts.get(key, ""), *(cell[x] for x in CENSUS), cell["concurrency"]["max"],
            cell["concurrency"]["p95"], cell["concurrency"]["days_over_heat_slots"])
           for key, cell in totals["cells"].items()])
    table(("ATR14 % bucket", "rows"), list(totals["atr_buckets"].items()))


def reports(reps):
    rows = []
    for rep in reps:
        fm, dollars = rep["floor_moved"], rep["dollars"]["component"]
        rows.append((rep["cell"], fm["n_baseline"], fm["n_component"], fm["delta_expr"],
                     fm["delta_expr_lo95"], fm["delta_expr_hi95"], fm["delta_wr_pp"],
                     rep["volume"]["change_pct"], rep["median_planned_rr"]["baseline"],
                     rep["median_planned_rr"]["component"],
                     rep["stop_distance"]["median_atr"]["baseline"],
                     rep["stop_distance"]["median_atr"]["component"],
                     rep["exits"]["component"]["early_stops"],
                     rep["exits"]["component"]["fill_beyond_ceiling"],
                     dollars["exceed_bullish"], dollars["exceed_bearish"]))
    table(("cell", "N base", "N cell", "ΔExpR", "lo95", "hi95", "ΔWR pp", "volume %", "RR base",
           "RR cell", "stop ATR base", "stop ATR cell", "early stops", "fill beyond ceiling",
           "$ exceed long", "$ exceed short"), rows)
    for rep in reps:
        for split in SPLITS:
            table((f"{rep['cell']} {split}", "N base", "N cell", "ΔExpR", "ΔWR pp"),
                  [(name, s["n_baseline"], s["n_component"], s["delta_expr"], s["delta_wr_pp"])
                   for name, s in rep[split].items()])


def stage0(d):
    table(("cell", "stratum N", "paired N", "newly admitted", "observed N", "target N", "MDE R"),
          [(c["cell"], c["stratum_n"], c["paired_n"], c["newly_admitted_n"], c["observed_n"],
            c["target_n"], c["mde_r"]) for c in d["cells"]])
    print(f"powered cells {d['powered_cells']} (ceiling {d['mde_ceiling_r']}R, power {d['power']})")


def stage1(d):
    rows = []
    for c in d["cells"]:
        clause = {x["name"]: x["verdict"] for x in c["gate"]["clauses"]}
        rows.append((c["cell"], c["n_baseline"], c["n_component"], c["delta_expr"],
                     clause.get("expectancy_gain"), clause.get("win_rate_floor"),
                     clause.get("volume"), c["candidate"], c["eligible"], c["plateau"]))
    table(("cell", "N base", "N cell", "ΔExpR", "expectancy_gain", "win_rate_floor", "volume",
           "candidate", "eligible", "plateau"), rows)
    print(f"selected {d['selected']}; tolerance {d['tolerance_r']}R\n")
    reports(d["reports"])


def stage2(d):
    table(("year", "N", "ΔExpR", "measurable", "positive"),
          [(f["year"], f["n"], f["delta_expr"], f["measurable"], f["positive"]) for f in d["folds"]])
    print(f"positive folds {d['positive']} of {len(d['folds'])} (needs {d['min_positive']})")


def stage3(d):
    table(("clause", "verdict", "value", "threshold", "detail"),
          [(x["name"], x["verdict"], x["value"], x["threshold"], x["detail"])
           for x in d["gate"]["clauses"]])
    print(f"permutation p {d['permutation_p']} (n {d['n_permutations']})\n")
    reports([d["report"]])


def main(path):
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    print(f"**arm {d.get('arm')} stage {d['stage']}: {d['verdict']}** "
          f"(instrument {d.get('instrument')}, data {d.get('data_source')})\n")
    if d["stage"] == -1:
        census(d["totals"], d["cell_verdicts"])
        print(f"reachable cells {d['reachable_cells']}; identical adjacent {d['identical_adjacent']}")
    else:
        {0: stage0, 1: stage1, 2: stage2, 3: stage3}[d["stage"]](d)


if __name__ == "__main__":
    main(sys.argv[1])
```

- [ ] **Step 2: Stage 0 (the fold-train rows replay, the long run)**

`git status --short -- swingbot/ scripts/` is empty. Invoke `backtest-gate`. Dispatch `backtest-runner` with the worktree path, the progress file `logs/measure_atr_band_stop.R.rows.progress`, the Stage 0 estimate from V191-20 Step 4, and:

```bash
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py --arm R --stage 0
```

Expected last line: `arm R stage 0: POWERED -> ...armR-stage0.json` (exit 0) or `UNDERPOWERED` (exit 1). Then:

```bash
python logs/v191/render_stage.py docs/superpowers/results/v191/2026-10-24-v191-armR-stage0.json
```

Stop-and-report-a-bug conditions (never results): a cell with `paired_n > stratum_n`; `observed_n == 0` on a reachable cell; a `cells[]` entry for a cell not in Stage −1's `reachable_cells`. `UNDERPOWERED` closes arm R at Stage 0, budget intact: go to Step 7, then Step 9.

- [ ] **Step 3: Stage 1 (bootstrap over the saved train rows)**

Invoke `backtest-gate`. Dispatch `backtest-runner` (progress: the driver's per-cell lines; no replay happens) with:

```bash
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py --arm R --stage 1
```

Expected last line: `arm R stage 1: SELECTED -> ...` (exit 0) or `NO_ELIGIBLE_CELL` (exit 1). Render it:

```bash
python logs/v191/render_stage.py docs/superpowers/results/v191/2026-10-24-v191-armR-stage1.json
```

Stop-and-report-a-bug conditions: `tolerance_r != 0.03`; `cells` does not list all three of `k0.75`, `k1`, `k1.5`; `candidate` is True for a cell not in Stage 0's `powered_cells` (or False for one in it); `selected` names a cell that is not `candidate`, `eligible` and `plateau` all at once; a `reports[]` entry whose `floor_moved.n_component` is 0 while its Stage −1 `floor` count is non-zero (the rows are not the census replay).

`NO_ELIGIBLE_CELL` closes arm R at Stage 1, budget intact: go to Step 7, then Step 9.

- [ ] **Step 4: Commit Stages 0 and 1 before Stage 2**

```bash
ls -l docs/superpowers/results/v191/
git add docs/superpowers/results/v191/2026-10-24-v191-armR-train-rows.json docs/superpowers/results/v191/2026-10-24-v191-armR-stage0.json docs/superpowers/results/v191/2026-10-24-v191-armR-stage1.json
git commit -m "docs(v191): arm R Stage 0 <verdict>, Stage 1 <verdict, selected cell>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Leave a rows file of 50 MB or more out of `git add` (part rule). Add only files that exist.

- [ ] **Step 5: Stage 2 (the 2023 fold replays the selected k only)**

Invoke `backtest-gate`. Dispatch `backtest-runner` with the progress file `logs/measure_atr_band_stop.R.rows.progress` and:

```bash
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py --arm R --stage 2
```

Expected last line: `arm R stage 2: PASS -> ...` (exit 0) or `FAIL` (exit 1). Render:

```bash
python logs/v191/render_stage.py docs/superpowers/results/v191/2026-10-24-v191-armR-stage2.json
```

Stop-and-report-a-bug: `folds` years other than 2021, 2022, 2023; a fold with `positive` True and `measurable` False. Commit:

```bash
git add docs/superpowers/results/v191/2026-10-24-v191-armR-fold2023-rows.json docs/superpowers/results/v191/2026-10-24-v191-armR-stage2.json
git commit -m "docs(v191): arm R Stage 2 walk-forward -- <PASS|FAIL>, <positive> of 3 folds positive

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

`FAIL` closes arm R at Stage 2, budget intact: go to Step 7, then Step 9.

- [ ] **Step 6: Stage 3 — arm R's one VALIDATION shot**

Pre-flight (nothing here reads VALIDATION):

```bash
git status --short docs/superpowers/results/v191/          # expected: empty, every earlier stage file committed
ls docs/superpowers/results/v191/ | grep "armR-stage3"     # expected: nothing
git log --oneline -1 -- docs/superpowers/specs/2026-10-24-v191-confluence-atr-band-stops-design.md   # expected: the hash named in the results doc's header
```

Invoke `backtest-gate` and state in the session: the selected cell and `k` (from `armR-stage1.json` `selected`), and that this is arm R's single VALIDATION shot. Dispatch `backtest-runner` with the progress file `logs/measure_atr_band_stop.R.rows.progress` and:

```bash
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_atr_band_stop.py --arm R --stage 3 --preregistration docs/superpowers/specs/2026-10-24-v191-confluence-atr-band-stops-design.md
```

Expected last line: `arm R stage 3: PASS -> ...` (exit 0) or `FAIL` (exit 1). **Whatever it prints is final.**
- A crash after `armR-validation-rows.json` was written: run the same command again; the driver reuses the saved rows and replays nothing.
- A crash before that file exists: nothing was read; run it again.
- `refused: ... one VALIDATION shot is spent`: the shot already ran. Stop and report; never delete the file.

Commit the generated files before interpreting them:

```bash
git add docs/superpowers/results/v191/2026-10-24-v191-armR-validation-rows.json docs/superpowers/results/v191/2026-10-24-v191-armR-stage3.json
git commit -m "docs(v191): arm R Stage 3 VALIDATION -- <PASS|FAIL>, shot spent

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Check the prediction (recorded, never gating)**

```bash
python - <<'PYEOF'
import json, pathlib
d = pathlib.Path("docs/superpowers/results/v191")
reps = []
s1 = d / "2026-10-24-v191-armR-stage1.json"
if s1.exists():
    reps += [("fold-train", r) for r in json.loads(s1.read_text(encoding="utf-8"))["reports"]]
s3 = d / "2026-10-24-v191-armR-stage3.json"
if s3.exists():
    reps.append(("VALIDATION", json.loads(s3.read_text(encoding="utf-8"))["report"]))
for window, r in reps:
    fm = r["floor_moved"]
    wr, dx = fm["delta_wr_pp"], fm["delta_expr"]
    hit_wr = "hit" if wr is not None and wr >= 4.0 else "MISSED"
    hit_x = "hit" if dx is not None and dx < 0 else "MISSED"
    print(f"{window} {r['cell']}: dWR {wr} pp (>= +4: {hit_wr}); dExpR {dx} R (arm R < 0: {hit_x})")
PYEOF
```

If Stage 0 closed the arm (no Stage 1 file), the script prints nothing: write "prediction not scored (closed before Stage 1)".

- [ ] **Step 8: Sanity of the dollar invariant on the component side (disclosure)**

In each rendered report, `$ exceed long` / `$ exceed short` on the component side counts band trades whose dollar loss went past the fixed budget. Under the dollar rule that can only come from a gap through the stop beyond the p99 allowance. If a cell shows exceedances while its `exits.component.gap_through` is 0, that is a sizing bug: stop and report. Otherwise disclose the counts as they are.

- [ ] **Step 9: Write the arm R section and commit**

Invoke `pooled-numbers`. Append `## Arm R (second)` to `docs/superpowers/results/2026-10-24-v191-atr-band-stops.md` with:
- **Verdict line:** the stage arm R ended at, its verdict, and whether its VALIDATION shot is spent.
- `### Stage 0`, `### Stage 1`, `### Stage 2`, `### Stage 3`: the renderer output for each stage that ran, pasted as printed (`python logs/v191/render_stage.py <file>`), with the selection rule quoted from the frozen block under Stage 1.
- `### Prediction`: the Step 7 lines, and "missed" spelt out wherever a line says MISSED.
- `### Disclosures`: the Step 8 counts; the newly admitted count and per-day alert count (`report.newly_admitted`); the top-two-horizon share; the regime2 cut (descriptive). Point to the JSON for anything not tabled.
- **Observations**, plainly: arm R re-chose TP1 against the wider stop, as v139 arm S did (which lost 0.03R), so its median planned RR and its `band_no_target` count are the first things to read; 1R is wider on a floor-moved plan, so the same price move is a smaller R, and ΔExpR in R equals ΔExpR in dollars only under the fixed-dollar sizing the rule enforces; whether one horizon carries the result; how many component fills went past the stored ceiling (live would cancel them).

```bash
git add docs/superpowers/results/2026-10-24-v191-atr-band-stops.md
git commit -m "docs(v191): arm R record -- <verdict at stage>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

