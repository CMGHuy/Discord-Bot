# v192 — Wait for a reclaim when a market plan's next open gaps toward its stop, Part 4: docs, the disclosure and the fold-train runs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot patch
**Edge:** expectancy — see the index.
**Spec:** [2026-10-24-v192-gap-toward-stop-reclaim-design.md](../specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md)
**Index:** [2026-10-24-v192-gap-toward-stop-reclaim_0-index.md](2026-10-24-v192-gap-toward-stop-reclaim_0-index.md) — Goal, Global Constraints, § Contracts, Review Focus, Parallelisation and the task ledger live there and bind every task below; this part never changes a shared name, signature or path. **Never read a part whole:** `grep -n "^### Task V192-23:" -A 320 <this file>`.
**Next:** [part 4b, V192-24..V192-26](2026-10-24-v192-gap-toward-stop-reclaim_4b-validation-record-and-release.md) — Stage 2, the one VALIDATION shot, the record and ledger row, the release with the plan's single full-suite run and the merge (split off to stay under the 1500-line cap). Its tasks follow the rules below.

**Scope of this part (V192-20..V192-23):** the docs and their Codex mirror (V192-20); the pre-TRAIN disclosure, the 2026-10-21 autopsy re-cut to market plans (V192-21); Stage −1 reachability for the three `g` cells (V192-22); Stages 0 and 1 on fold-train, with the next-open vs close-fill basis and the per-cell fold-train reports (V192-23).

**Names consumed from earlier parts** (all created there; verified against the part files):
- `measure_arms.py --knob ATTR=value (repeatable) --baseline-knob ATTR=value (repeatable) --stage pilot|selection|walkforward|validation --out F [--workers N] [--preregistration F] --data-source alpaca` (V192-14). It writes `F`, `F`'s training-data provenance and, when the component delta sets `GAP_RECLAIM_ATR > 0`, the census sidecar `<F stem>.gap_reclaim.json` (V192-15; keys `knob_delta`, `baseline_knob_delta`, `signal_window`, `universe_count`, `summary`, `repriced_in_component`, `repriced_absent_from_component`, `rows`). On the pilot stage it exits 1 with `refused:zero-diff` when no outcome changed, after writing `F`. The census replays the component arm once more, so each veto run costs about one extra arm of wall time.
- `summary` (`gap_reclaim_census.reachability_summary`): `cells` (per `horizon_key` × `direction`: `market_plans`, `filled_at_open`, `armed`, `reclaimed`, `ambiguous`, `gap_no_reclaim`, `open_through_stop`, `risk_cap`, `no_bar`, `reclaim_rate`, `ambiguous_share`), `total` (the same counts), `gap_atr` (`n`, quantiles `q10`..`q90`, `share_at_or_above` keyed `"0.1"`, `"0.25"`, `"0.5"`), `verdict` `REACHABLE` | `refused:zero-diff`.
- `validate_component.py --gap-reclaim` (V192-18): `--stage reachability` prints the existing `knobs:` / `baseline knobs:` / `split` lines, then the census summary as JSON (also written with `--out-json`), then `REACHABLE -- the veto arms on market plans; Stage 0 may proceed.` (exit 0) or a `refused:zero-diff -- ...` line (exit 1). `--stage mde` gates the paired MDE with `cluster="week"` and prints `train effect (standardised, from --arms): <x>pp`, `observed N`, `projected target N`, `paired MDE   (dWR)`, `unpaired MDE (dWR)`, `gating on:`, then `RESOLVABLE -- ...` (exit 0) or `REFUSED -- ...` (exit 1). `--stage selection --grid-arms g=F (three times) [--mde-refused g]` scores each cell with `selection_cell` (eligible iff point ΔExpR ≥ −0.01R and resolvable) and prints one `g=<v> eligible=... dWR=... ExpR=... failed=... disclosure=...` line per cell, then `verdict=<selected|no-eligible-cell|spike> selected=<g|None>`. Any stage that reads the census refuses `refused:no-gap-reclaim-sidecar`. `--gap-reclaim` with `--gate harvest`, a mechanism flag or `--wr-statistic pooled` is a parser error.
- `scripts/reports/gap_reclaim_report.py --arms F [--basis F] --out-json F --out-md F [--resamples N] [--seed N] [--reference-account USD] [--risk-pct P] [--data-source alpaca]` (V192-18); refusals `refused:no-whole-window`, `refused:no-gap-reclaim-sidecar`, `refused:basis-on-validation`, `refused:not-a-basis-pair` (the basis pair is component `MARKET_ENTRY_NEXT_OPEN=true` against an empty baseline). Its JSON carries `census_health`, `n`, `win_rate`, `expectancy_r`, `delta_win_rate_pp`, `delta_expectancy_r`, `outcome_flips`, `strata`, `repriced_dollars`, `ambiguous_sensitivity`, `census`, `splits`, `removed_top2_horizon_share`, `earnings_proximity`, `regime` and, with `--basis`, `basis`.
- `book_autopsy.py --entry-type market` writes `<out-dir>/<date>-book-autopsy-market.json` and `.md`, sets `header["entry_type_filter"]` and adds a header note (V192-19).
- Engine names V192-20's docs cite: `swingbot/core/planning/gap_reclaim.py` (`effective_g`, `next_open_applies`, `waits_for_open`, `stamp_next_open`, `decide_at_open`), `swingbot/core/planning/market_next_open.py` (`next_open_market_exit`, `next_open_fill_bar`, `observing`), `swingbot/core/planning/market_open.py` (`deciding_session`, `market_phase`, `PREMARKET_STOP_CONFIRM_POLLS`), `PlanManager._step_market_open`, `plan_manager.PLACEHOLDER_DISCARD_EVENTS`, `config.enforce_gap_reclaim_coupling`, `knobs.GAP_RECLAIM_NEEDS_NEXT_OPEN`, `Kind.RECLAIM_ORDER`, `instructions.market_on_open_lines`, `strategy_pass._stamp_issued_for_open`, `gap_reclaim_census.py`, `gap_reclaim_clauses.py` (V192-2..V192-17).

**Where commands run.** The controller enters the worktree as the session root (`EnterWorktree`). Every command below still names the worktree by absolute path, through `WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim` set at the top of the same shell call, and uses `git -C "$WT"`: subagent shells reset their working directory between calls, and **`cd` is never used** (it breaks the guard hooks). Never edit the main tree's files from a task.

## Rules for every measurement task (V192-22..V192-25)

- **Invoke the `backtest-gate` skill before every `measure_arms.py` command**, not after.
- **Every producer and judge command carries the three variables on the same line** (index § Global Constraints), plus `--data-source alpaca`:

  ```bash
  MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/measure_arms.py" <args> --data-source alpaca
  ```

  The judges (`validate_component.py`, `permutation_test.py`, `gap_reclaim_report.py`) take the same three variables: their stamp gates call `measure_arms.cached_universe()`, so a judge without `MEASURE_ARMS_UNIVERSE=cache` compares against a different universe and refuses.
- **The knob lists are frozen.** Component: `--knob MARKET_ENTRY_NEXT_OPEN=true --knob GAP_RECLAIM_ATR=<g>`. Baseline: `--baseline-knob MARKET_ENTRY_NEXT_OPEN=true`. The basis pair (V192-23 only): `--knob MARKET_ENTRY_NEXT_OPEN=true` and no `--baseline-knob`. `g` is written `0.1`, `0.25`, `0.5` on the command line and `g010`, `g025`, `g050` in file names.
- **Every producer run passes `--preregistration "$WT/docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md"`**, so every stamp names the committed spec; Stage 3 refuses without it.
- **Dispatch the `backtest-runner` agent for every producer command and every report or permutation run** (each replays bars or bootstraps and can pass 15 minutes). Give it the exact command, the worktree path and the progress file: the newest `"$WT"/logs/measure_arms.*.progress` (the producer writes a percent there; the census that follows the two arms writes no percent, so the runner reports "census running" until the process exits). **One runner at a time**, never two, never overlapping each other or a full-suite run. The judges' reachability, MDE and selection readings are quick and run inline.
- **Frozen code.** From V192-22's first command to V192-25's last stage file, make no edit under `swingbot/` or `scripts/`, and never merge `main` into the worktree: the rows depend on the code. Before each producer run, `git -C "$WT" status --short -- swingbot/ scripts/` prints nothing.
- **A stage that does not advance closes the funnel**: Stage −1 with every cell `refused:zero-diff`; Stage 0 with every cell `REFUSED`; Stage 1 `no-eligible-cell` or `spike`; Stage 2 `FAIL`; Stage 3 `FAIL`. Record it as measured and go straight to V192-25's record steps (part 4b). Never widen a window, add a cell, change a threshold, the MDE ceiling or the reclaim rule, delete a stage file, or re-run Stage 3. Stages −1..2 are deterministic; re-running one is allowed only to recover from a crash, never to move a number.
- **Per-cell rules, honoured as written.** A cell is closed at Stage −1 when its reachability reading is not `REACHABLE`; the funnel continues while any cell is `REACHABLE`. Stage 0 gates each cell on its own paired MDE (`cluster="week"`); a refused cell is passed to Stage 1 as `--mde-refused`, so it can never be selected but stays a plateau neighbour. A cell closed at Stage −1 is still produced at fold-train (fold-train spends no budget) and enters Stage 1 as `--mde-refused` too, so the plateau check always sees the whole frozen grid. Stage 1 picks the highest whole-window standardised ΔWR among eligible cells, ties to the smaller `g`, plateau `backtest_wf.PLATEAU_TOLERANCE_R` = 0.03R on component ExpR; a spike does not proceed.
- **Census health.** Each veto sidecar carries `repriced_in_component` and `repriced_absent_from_component`. Record both beside the strata at every stage. An absent count above 1% of `repriced_in_component + repriced_absent_from_component` means the census and the arm disagree: stop and ask the partner (`AskUserQuestion`, one question, recommended option first: "Stop the funnel and inspect the census against the arm rows (Recommended)" / "Record it and continue"). At or below 1% it is recorded and the funnel continues.
- **Numbers come only from the JSON and text files the commands write**, rendered by the snippets in each task, never retyped. Invoke the `pooled-numbers` skill before quoting any ΔExpR, win rate or N in the results doc, a commit message, the closed table or the ledger.
- **Evidence files are committed** when each is under 50 MB (v139 precedent). A file of 50 MB or more is not committed: append its repo-relative path to the file `git -C "$WT" rev-parse --git-path info/exclude` names (local only, never a committed change) and record its size and `sha256sum` in the results doc.
- **No knob goes live and no default changes**, whatever the verdicts: `MARKET_ENTRY_NEXT_OPEN` stays `"false"` and `GAP_RECLAIM_ATR` `"0"`. Any partner question offers the conservative option first, recommended.

---

# Phase 11 — Docs and the pre-TRAIN disclosure

### Task V192-20: Docs: architecture, known-traps, AGENTS.md

**Model:** haiku — documentation only, with the exact text written below; no code and no judgement beyond placing it.

**Files:**
- Modify: `docs/claude/known-traps.md` (one new section appended at the end of the file, after `## Shared market-data layer: one door, two daily caches (v171)`)
- Modify: `docs/claude/architecture.md` (one bullet in `## Plan engine, registry and scan pipeline`, directly before the bullet that starts `- **Opex-day caution (v44):**`)
- Modify: `AGENTS.md` (one clause in the condensed `known-traps.md` bullet under "Read the `docs/claude/` file before acting")

**Interfaces:**
- Consumes: the names V192-2..V192-17 built (header list above): `swingbot/core/planning/gap_reclaim.py`, `swingbot/core/planning/market_next_open.py`, `swingbot/core/planning/market_open.py`, `PlanManager._step_market_open`, `plan_manager.PLACEHOLDER_DISCARD_EVENTS`, `config.enforce_gap_reclaim_coupling`, `knobs.GAP_RECLAIM_NEEDS_NEXT_OPEN`, `Kind.RECLAIM_ORDER`, `instructions.market_on_open_lines`, `strategy_pass._stamp_issued_for_open`, `gap_reclaim_census.py`, `gap_reclaim_clauses.py`.
- Produces: nothing a later task reads by name. The new known-traps section points at the results doc for the verdict, so V192-25 never edits it.

Before writing, confirm every name exists in the worktree (each was created by an earlier task of this plan):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" grep -n "def effective_g\|def next_open_applies\|def waits_for_open\|def stamp_next_open\|def decide_at_open" -- swingbot/core/planning/gap_reclaim.py
git -C "$WT" grep -n "def next_open_market_exit\|def next_open_fill_bar\|def observing" -- swingbot/core/planning/market_next_open.py
git -C "$WT" grep -n "def deciding_session\|def market_phase\|PREMARKET_STOP_CONFIRM_POLLS = 2" -- swingbot/core/planning/market_open.py
git -C "$WT" grep -n "def _step_market_open\|^PLACEHOLDER_DISCARD_EVENTS" -- swingbot/core/planning/plan_manager.py
git -C "$WT" grep -n "def enforce_gap_reclaim_coupling" -- swingbot/config.py
git -C "$WT" grep -n "GAP_RECLAIM_NEEDS_NEXT_OPEN = " -- swingbot/core/backtesting/arms/knobs.py
git -C "$WT" grep -n "RECLAIM_ORDER" -- swingbot/core/presentation/kinds.py
git -C "$WT" grep -n "def market_on_open_lines" -- swingbot/core/presentation/instructions.py
git -C "$WT" grep -n "def _stamp_issued_for_open" -- swingbot/core/scanning/strategy_pass.py
git -C "$WT" grep -n "def reachability_summary\|SIDECAR_SUFFIX = " -- swingbot/core/backtesting/arms/gap_reclaim_census.py
git -C "$WT" grep -n "def strata_split\|def evaluate_gap_reclaim\|def repriced_permutation" -- swingbot/core/backtesting/arms/gap_reclaim_clauses.py
```

Expected: at least one hit per command. A command with no hit means an earlier task is missing from this worktree: stop and report it.

- [ ] **Step 1: Append the known-traps section**

Append this section at the very end of `"$WT/docs/claude/known-traps.md"` (one blank line before the heading):

```markdown
## Market-on-open and the gap-reclaim veto (v192): two knobs, both off

Two knobs, inert by default: `MARKET_ENTRY_NEXT_OPEN` (`"false"`) and
`GAP_RECLAIM_ATR` (`g`, `"0"`). With both at default, replay `ExitResult`s,
arm rows and plan dicts are byte-identical to before v192, pinned by the
goldens in `tests/fixtures/v192/`. A golden that moves is a behaviour
change, never a fixture to refresh.

- **Coupling.** `GAP_RECLAIM_ATR > 0` is honoured only with
  `MARKET_ENTRY_NEXT_OPEN` on. At import and at every SIGHUP reload
  `config.enforce_gap_reclaim_coupling()` sets it to 0 and logs an ERROR; in
  measurement `arms.knobs.apply_knobs` raises
  `ValueError(GAP_RECLAIM_NEEDS_NEXT_OPEN)` on the merged arm config. A veto
  that "does nothing" live is this guard first. `gap_reclaim.effective_g()`
  is the one reader that applies it.
- **What "waiting" means.** With the first knob on, a market plan (v180
  Turtle Soup excepted) is built PENDING with `entry_price=None` and
  `waits_next_open=True`. `gap_reclaim.waits_for_open(plan)` reads that
  marker, not status and entry type alone: about ten test modules build
  PENDING market plans that must keep the close fill. The marker, `a_t`
  (`reclaim_atr`) and `X` (`reclaim_level`) are stamped once at creation
  and never rewritten by a reload, a knob flip or a restart.
- **`a_t` reads bars through `t` only** (Wilder ATR14,
  `market/indicators.atr`). Under 15 bars, NaN or ≤ 0 gives no
  `reclaim_level`: the plan fills at the open like the baseline, never a
  crash. Live re-derives `E`, `a_t`, `X` from the completed frame, and a
  parity test pins them against the replay.
- **One decision for live and replay.** `gap_reclaim.decide_at_open` runs in
  this order: open at or through the stop → `open_through_stop`; `X` set and
  the open at or beyond it → `reclaim_wait`; past the stop ceiling →
  `risk_cap`; else fill at the open. Replay fills a reclaim at `E ± 1 tick`
  (the stop order's slippage; the v1 arm replay applies no other frictions);
  live fills at `E` on the first RTH poll one tick through it.
- **The fill bar is walked in both arms**
  (`market_next_open.next_open_fill_bar`): stop first, then TP1 (scale-out
  plans bank TP1 and continue the runner from the fill bar), so an ambiguous
  reclaim bar is −1R. An open at or beyond TP1 is v180's 0R `gap_target`.
  `_fill_bar_exit`'s 0R `gap_through_stop` scratch is not reused.
- **Live timing.** `market_open.deciding_session(plan)` is the first NYSE
  session whose 09:30 ET open is at or after `issued_at`
  (`strategy_pass._stamp_issued_for_open` stamps it). Extended-hours polls
  before that open run a two-poll stop-cross debounce
  (`PREMARKET_STOP_CONFIRM_POLLS`), new code: the old
  `EXTENDED_HOURS_EXIT_CHECK` / `EXTENDED_HOURS_DEBOUNCE_TICKS` fields are
  still read by nothing. A first RTH poll on a later session cancels
  `cancelled_expired` / `missed_open`; a plan resting for its reclaim
  cancels `gap_no_reclaim` on the first poll after that session's close.
  `PlanManager._step_market_open` runs ahead of `_step_pending`, whose
  stop-entry fill would otherwise fill a waiting market plan at any price.
- **Feed and followers.** `cancelled_open_through_stop`,
  `cancelled_gap_no_reclaim` and `gap_reclaim_order` are `NOTICE_EVENTS`
  (re-sent until acked), have `instructions` builders and the
  `Kind.RECLAIM_ORDER` copy, and the two cancels are in
  `PLACEHOLDER_DISCARD_EVENTS`, so the alert-time placeholder trade never
  sits open after a cancel. A cancel transition added later must join that
  set and `_CANCEL_LEADS`, or `_cancel_why` raises KeyError.
- **Measurement needs a baseline delta.** Both arms run with
  `MARKET_ENTRY_NEXT_OPEN=true`; the component adds `GAP_RECLAIM_ATR=g`
  (`measure_arms.py --baseline-knob`, stamped `baseline_knob_delta`). The
  veto is not a subset feature: the census sidecar
  `<out stem>.gap_reclaim.json` names the re-priced (reclaimed) keys, and
  `gap_reclaim_clauses.strata_split` scores removed / re-priced / added /
  unchanged, with a SKIPPED clause failing. The verdict is in
  `docs/superpowers/results/2026-10-24-v192-gap-reclaim.md`.
- **A pass licenses neither knob.** `MARKET_ENTRY_NEXT_OPEN` changes every
  market plan's fill and needs its own non-inferiority pre-registration
  (next-open vs close fill) before the partner flips both.
```

- [ ] **Step 2: Architecture**

In `"$WT/docs/claude/architecture.md"`, `## Plan engine, registry and scan pipeline`, directly before the line that starts `- **Opex-day caution (v44):**`, insert:

```markdown
- **Market-on-open path (v192, off by default).** With
  `MARKET_ENTRY_NEXT_OPEN` on, the builders build market plans PENDING
  (`gap_reclaim.stamp_next_open`); `planning/gap_reclaim.py` is the one pure
  rule (tick, `a_t`, `X`, `decide_at_open`) shared by the replay
  (`planning/market_next_open.py`, dispatched from `exit_sim._market_exit`)
  and the live step (`planning/market_open.py` session timing,
  `PlanManager._step_market_open`). `GAP_RECLAIM_ATR` adds the reclaim
  veto. Traps and coupling: `known-traps.md` § Market-on-open and the
  gap-reclaim veto (v192).
```

- [ ] **Step 3: The Codex mirror**

In `"$WT/AGENTS.md"`, the bullet that starts ``- `known-traps.md`: data caching`` today ends with ``production `.env` (never `sed -i`).``. Insert this clause directly before ``production `.env` ``:

```markdown
the v192 market-on-open path
  (`GAP_RECLAIM_ATR` needs `MARKET_ENTRY_NEXT_OPEN`, else zeroed at load),
```

With today's wording the whole bullet then reads:

```markdown
- `known-traps.md`: data caching (v171: every provider call goes through
  `core/marketdata/shared/`, guard test), scan output, embeds, the 2% stop
  cap/clamp, the liquidity floor, the v192 market-on-open path
  (`GAP_RECLAIM_ATR` needs `MARKET_ENTRY_NEXT_OPEN`, else zeroed at load),
  production `.env` (never `sed -i`).
```

If another plan (v191) has already reworded the bullet in this worktree, keep its words and insert the same clause directly before ``production `.env` ``; never drop another plan's clause.

- [ ] **Step 4: Verify**

Run from the worktree as the session root (the controller's `EnterWorktree`), so `changed` selects against the worktree's diff:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python "$WT/scripts/dev/doc_section.py" "$WT/docs/claude/known-traps.md" "Market-on-open and the gap-reclaim veto (v192): two knobs, both off" | head -3
python "$WT/scripts/dev/doc_section.py" "$WT/docs/claude/architecture.md" "Plan engine, registry and scan pipeline" | grep -c "Market-on-open path (v192"
grep -c "v192 market-on-open path" "$WT/AGENTS.md"
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py
python "$WT/scripts/dev/testrun.py" changed
```

Expected: the section heading prints; `1`; `1`; `0 failed` in both runs (`changed` selects whatever tests read these docs).

- [ ] **Step 5: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" add docs/claude/known-traps.md docs/claude/architecture.md AGENTS.md
git -C "$WT" commit -m "docs(v192): known-traps and architecture for the market-on-open path and the gap-reclaim veto; AGENTS.md mirror

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V192-21: Pre-TRAIN disclosure: autopsy cells re-cut to market plans

**Model:** sonnet — runs a finished report script on a read-only export with fixed filters and copies its output through a fixed renderer; the only judgement is the stop-and-report checks spelt out below.

**Files:**
- Create: `docs/superpowers/results/2026-10-24-v192-gap-reclaim.md` (header, the frozen block and the disclosure section; V192-22..V192-25 append to it)
- Create (written by `book_autopsy.py`): `docs/superpowers/results/v192/autopsy-market/full/2026-10-21-book-autopsy-market.json` and `.md`, `docs/superpowers/results/v192/autopsy-market/sep-era/2026-10-21-book-autopsy-market.json` and `.md`, and the same-export controls without the filter `docs/superpowers/results/v192/autopsy-market/control-all-types/full/2026-10-21-book-autopsy.json` and `.md`, `docs/superpowers/results/v192/autopsy-market/control-all-types/sep-era/2026-10-21-book-autopsy.json` and `.md`
- Scratch, never committed (`logs/` is git-ignored): `logs/v192/autopsy/rows.csv`, `rejections.csv`, the four filtered CSVs, `bars/`, `logs/v192/cut_autopsy.py`, `logs/v192/render_autopsy.py`

**Interfaces:**
- Consumes: `book_autopsy.py --entry-type market` (V192-19), which writes `<out-dir>/<date>-book-autopsy-market.json` and `.md`, sets `header["entry_type_filter"]` and adds a header note; the unchanged `book_autopsy.py` without the flag; `scripts/ops/export_book_rows.sh` (`rows` and `rejections` modes, read-only, exists); `autopsy.rows._eastern_date` (`scripts/reports/autopsy/rows.py:120`, exists); the committed `docs/superpowers/results/2026-10-21-book-autopsy.json` and `2026-10-21-book-autopsy-sep-era.json` (cells are dicts with `id`, `cut`, `value`, `n`, `weeks`, `win_rate`, `net_expr`, `gross_expr`, `delta`, `ci`, `p`, `q`, `thin`, `bar_covered_n`; header keys `window`, `n`, `pooled_net_expr`, `pooled_win_rate`, `bar_covered_n`, `cells_tested`).
- Produces: the results doc with its frozen block, committed **before any `measure_arms.py` run** (V192-22 refuses to start without it), and the disclosure section.

**Why:** the motivating `open_gap_bucket=favourable` cell pools stop-entry, limit and market rows, and for live market plans it compares the alert-day open with the alert price (spec § Edge, panel). The spec requires the cells re-cut to market plans only, as disclosure, before TRAIN. The re-cut motivates and never selects: both windows overlap the 2026 holdout, and nothing in it changes the frozen grid, a threshold or the prediction.

- [ ] **Step 1: Pre-flight**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" status --short                       # expected: empty
git -C "$WT" log --oneline main..HEAD | head -40  # expected: the V192-1..V192-19 commits (V192-20 may be there too)
python "$WT/scripts/reports/book_autopsy.py" --help | grep -c "entry-type"
ls "$WT/docs/superpowers/results/2026-10-24-v192-gap-reclaim.md" "$WT/docs/superpowers/results/v192" 2>&1 | head -3
```

Expected: empty status; every V192-1..V192-19 id present; `1`; both `ls` targets absent ("No such file or directory"). An existing results doc or `v192/` directory means a run happened outside this task: stop and report it.

- [ ] **Step 2: Export the live book, read-only**

The export runs on the VM through the wrapper (CLAUDE.md: never a raw `ssh`), opens its psql session READ ONLY and writes nothing there. Raw CSVs stay under the worktree's git-ignored `logs/`:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
mkdir -p "$WT/logs/v192/autopsy"
bash "$WT/scripts/ops/ssh-hetzner.sh" "cd /opt/swing-bot && bash -s -- rows" < "$WT/scripts/ops/export_book_rows.sh" > "$WT/logs/v192/autopsy/rows.csv"
bash "$WT/scripts/ops/ssh-hetzner.sh" "cd /opt/swing-bot && bash -s -- rejections" < "$WT/scripts/ops/export_book_rows.sh" > "$WT/logs/v192/autopsy/rejections.csv"
head -1 "$WT/logs/v192/autopsy/rows.csv" | tr ',' '\n' | grep -c "entry_type"
wc -l "$WT/logs/v192/autopsy/rows.csv" "$WT/logs/v192/autopsy/rejections.csv"
```

Expected: `1` (the `entry_type` column is there) and both files non-empty. `scripts/ops/ssh-hetzner.sh` is uncommitted and lives in the main checkout; if the worktree has no copy, call it as `bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh` with the same arguments.

- [ ] **Step 3: Cut the export to the two 2026-10-21 windows (scratch)**

Create `"$WT/logs/v192/cut_autopsy.py"` with exactly this content. It reproduces the two committed windows: the full book as of 2026-10-21 (every trade closed on or before that Eastern date, every plan created on or before it), and the current exit-model era (the same, restricted to trades opened on or after 2026-09-01 whose plan, when it has one, was created on or after that date, and plans created on or after it). Rejection tallies are cut at 2026-10-21 and carry no entry type:

```python
"""v192 scratch (never committed): cut the live-book export to the two 2026-10-21 autopsy windows."""
import csv
import sys
from pathlib import Path

WT = Path(sys.argv[1])
sys.path[:0] = [str(WT / "scripts" / "reports")]
from autopsy.rows import _eastern_date  # noqa: E402

SRC = WT / "logs" / "v192" / "autopsy"
END, ERA = "2026-10-21", "2026-09-01"


def _on_or_before(raw, day):
    d = _eastern_date(raw)
    return d is not None and d <= day


def _on_or_after(raw, day):
    d = _eastern_date(raw)
    return d is not None and d >= day


def in_full(row):
    if row["row_kind"] == "trade":
        return _on_or_before(row["closed_at"], END)
    return _on_or_before(row["plan_created_at"], END)


def in_era(row):
    if not in_full(row):
        return False
    if row["row_kind"] == "trade":
        plan_ok = not row["plan_created_at"] or _on_or_after(row["plan_created_at"], ERA)
        return _on_or_after(row["opened_at"], ERA) and plan_ok
    return _on_or_after(row["plan_created_at"], ERA)


def write(name, header, rows):
    with open(SRC / name, "w", newline="", encoding="utf-8") as fh:
        out = csv.DictWriter(fh, fieldnames=header)
        out.writeheader()
        out.writerows(rows)
    print(f"{name}: {len(rows)} rows")


with open(SRC / "rows.csv", newline="", encoding="utf-8") as fh:
    reader = csv.DictReader(fh)
    header, rows = reader.fieldnames, list(reader)
write("rows_full.csv", header, [r for r in rows if in_full(r)])
write("rows_era.csv", header, [r for r in rows if in_era(r)])
with open(SRC / "rejections.csv", newline="", encoding="utf-8") as fh:
    reader = csv.DictReader(fh)
    rheader, rejections = reader.fieldnames, list(reader)
write("rejections_cut.csv", rheader, [r for r in rejections if r["date"].strip() <= END])
tickers = sorted({r["ticker"] for r in rows if in_full(r) and r["ticker"]})
first = min(_eastern_date(r["plan_created_at"]) or END for r in rows if in_full(r))
(SRC / "tickers.txt").write_text(",".join(tickers), encoding="utf-8")
print(f"tickers {len(tickers)}; first plan date {first}")
```

Run it:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python "$WT/logs/v192/cut_autopsy.py" "$WT"
```

Expected: four `<name>: <n> rows` lines with non-zero counts, then the ticker count and the first plan date (2026-07-20 or earlier).

- [ ] **Step 4: Fetch bars into a scratch cache (never `data/backtest_cache/`)**

The fetcher needs 260 daily bars, so start at least 550 calendar days before the first plan date Step 3 printed (for 2026-07-20 that is 2025-01-16 or earlier; `2025-01-01` covers it):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
BACKTEST_CACHE_DIR="$WT/logs/v192/autopsy/bars" python "$WT/scripts/data/fetch_backtest_data.py" --tickers "$(cat "$WT/logs/v192/autopsy/tickers.txt")" --start 2025-01-01 --end today
ls "$WT/logs/v192/autopsy/bars" | wc -l
```

Expected: about one CSV per ticker. If Step 3 printed a first plan date before 2026-07-01, move `--start` back to 550 days before it. A ticker the provider cannot serve is left uncovered; the autopsy counts it under `bar_covered_n`.

- [ ] **Step 5: Run the autopsy four times — market only and the same-export control, per window**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
A="$WT/logs/v192/autopsy"; O="$WT/docs/superpowers/results/v192/autopsy-market"
python "$WT/scripts/reports/book_autopsy.py" "$A/rows_full.csv" "$A/rejections_cut.csv" --bars-dir "$A/bars" --out-dir "$O/full" --date 2026-10-21 --entry-type market
python "$WT/scripts/reports/book_autopsy.py" "$A/rows_era.csv" "$A/rejections_cut.csv" --bars-dir "$A/bars" --out-dir "$O/sep-era" --date 2026-10-21 --entry-type market
python "$WT/scripts/reports/book_autopsy.py" "$A/rows_full.csv" "$A/rejections_cut.csv" --bars-dir "$A/bars" --out-dir "$O/control-all-types/full" --date 2026-10-21
python "$WT/scripts/reports/book_autopsy.py" "$A/rows_era.csv" "$A/rejections_cut.csv" --bars-dir "$A/bars" --out-dir "$O/control-all-types/sep-era" --date 2026-10-21
```

Expected: each prints two `wrote ...` lines and `N <n>, bar-covered <b>, cells tested <c>`. The market runs write `2026-10-21-book-autopsy-market.json`/`.md`; the controls write `2026-10-21-book-autopsy.json`/`.md` in their own directories (they never overwrite the committed 2026-10-21 files, which live one level up).

The controls exist because the book has moved since 2026-10-21 (late closes, re-journaled rows): the market-only cut is compared against the same export unfiltered, never against the committed file alone.

- [ ] **Step 6: Write the renderer (scratch) and print the disclosure tables**

Create `"$WT/logs/v192/render_autopsy.py"` with exactly this content:

```python
"""v192 scratch (never committed): the open-gap cells of the committed, control and market-only autopsies."""
import json
import sys
from pathlib import Path

WT = Path(sys.argv[1])
R = WT / "docs" / "superpowers" / "results"
O = R / "v192" / "autopsy-market"
SOURCES = {
    "full": (R / "2026-10-21-book-autopsy.json", O / "control-all-types/full/2026-10-21-book-autopsy.json",
             O / "full/2026-10-21-book-autopsy-market.json"),
    "sep-era": (R / "2026-10-21-book-autopsy-sep-era.json",
                O / "control-all-types/sep-era/2026-10-21-book-autopsy.json",
                O / "sep-era/2026-10-21-book-autopsy-market.json"),
}
LABELS = ("committed 2026-10-21, all types", "same export, all types", "same export, market only")


def fmt(value, spec):
    return "—" if value is None else format(value, spec)


def cells(report, cut):
    return {c["value"]: c for c in report["cells"] if c["cut"] == cut}


for window, paths in SOURCES.items():
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    print(f"### {window}\n")
    print("| source | window | N | bar-covered | pooled WR | pooled net ExpR | cells tested |")
    print("|---|---|---|---|---|---|---|")
    for label, rep in zip(LABELS, reports):
        h = rep["header"]
        print(f"| {label} | {h['window'][0]}..{h['window'][1]} | {h['n']} | {h['bar_covered_n']} | "
              f"{fmt(h['pooled_win_rate'], '.1%')} | {fmt(h['pooled_net_expr'], '+.3f')} | {h['cells_tested']} |")
    print()
    print("| open_gap_bucket | source | N | weeks | WR | net ExpR | Δ net ExpR [95% CI] | q | thin |")
    print("|---|---|---|---|---|---|---|---|---|")
    values = sorted(set().union(*(cells(rep, "open_gap_bucket") for rep in reports)))
    for value in values:
        for label, rep in zip(LABELS, reports):
            c = cells(rep, "open_gap_bucket").get(value)
            if c is None:
                print(f"| {value} | {label} | 0 | — | — | — | — | — | — |")
                continue
            ci = c["ci"] or [None, None]
            print(f"| {value} | {label} | {c['n']} | {c['weeks']} | {fmt(c['win_rate'], '.1%')} | "
                  f"{fmt(c['net_expr'], '+.3f')} | {fmt(c['delta'], '+.3f')} [{fmt(ci[0], '+.3f')}, "
                  f"{fmt(ci[1], '+.3f')}] | {fmt(c['q'], '.3f')} | {c['thin']} |")
    print()
    market = reports[2]["header"]
    print(f"market-only filter recorded: {market.get('entry_type_filter')}\n")
```

Run it:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python "$WT/logs/v192/render_autopsy.py" "$WT"
```

Expected: two `### full` / `### sep-era` blocks, each a header table with three rows and an `open_gap_bucket` table, and `market-only filter recorded: market` twice. Sanity checks, in this order:
- The market-only N is at or below the same-export N in both windows, and both header windows end on or before 2026-10-21. Otherwise the cut or the filter is wrong: stop and report.
- The same-export N differs from the committed N (776 full, 221 era) by more than 5%: disclose it in Step 7 as book drift since 2026-10-21; it does not stop the task.
- No market-only `favourable` row (N 0) is a reading, not a failure: it says the motivating cell carried no market rows, and Step 7 says so in words.

- [ ] **Step 7: Write the results doc (header, frozen block, disclosure) and commit it before any run**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" log -1 --format=%h -- docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md
```

Create `"$WT/docs/superpowers/results/2026-10-24-v192-gap-reclaim.md"` with this content, filling `<spec hash>` from the command above (a value read from git, not a choice) and pasting Step 6's output where shown:

```markdown
# v192 — Wait for a reclaim when a market plan's next open gaps toward its stop: results

**Spec (the pre-registration):** `docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md`, last changed in `<spec hash>`. Every producer run passes it as `--preregistration`; Stage 3 refuses without it.
**Plan:** `docs/superpowers/plans/2026-10-24-v192-gap-toward-stop-reclaim_0-index.md` (§ Global Constraints carries the frozen block below).
**Producer:** `scripts/backtest/measure_arms.py` with `--baseline-knob`; judges `validate_component.py --gap-reclaim`, `permutation_test.py --gap-reclaim`; report `scripts/reports/gap_reclaim_report.py`. Stage files under `docs/superpowers/results/v192/`.

## Frozen before any run

- Claim: on market-entry plans, replacing the unconditional entry with "wait for a same-session reclaim of the planned entry when the next open gaps toward the stop by at least `g × ATR14`" raises win rate without breaking the v72 funnel's expectancy, geometry, volume and mechanism clauses.
- Prediction (falsifiable, selected cell): decided win rate +1.5pp or more; ΔExpR > 0; the removed population has a lower win rate than the unchanged one and ExpR ≤ 0. A contradiction is recorded as a missed prediction. The +1.5pp is a judgement, not derived from the autopsy cell.
- Definitions: `E = trigger_price`; `a_t` = Wilder ATR14 of bars through the creating bar `t`, `None` under 15 bars, NaN or ≤ 0 (then no veto: the plan fills at the open as in the baseline); `X = E − g·a_t` (bull, floored to the tick) / `E + g·a_t` (bear, ceiled); tick 0.01 at `E ≥ 1`, else 0.0001. Reclaim: bull `High ≥ E + tick`, bear `Low ≤ E − tick`, same session; replay fills at `E ± tick`. Ambiguous reclaim bar (reclaim and stop both touched) = −1R (stop-first).
- Grid `g ∈ {0.10, 0.25, 0.50}`; three cells, no other.
- Both arms on the next-open market fill (`MARKET_ENTRY_NEXT_OPEN=true`), the fill bar walked stop-first in both; the component adds `GAP_RECLAIM_ATR=g`. Open at or through the stop and the 2% stop ceiling at the open cancel in both arms (`not_triggered`).
- Strata: removed (baseline keys absent from the component), re-priced (the census's reclaimed keys present in both arms), added (component keys absent from the baseline), unchanged (every other paired key). Clause 6: removed WR < unchanged WR and removed ExpR ≤ 0; re-priced reported, never deciding. Volume cut = removed ÷ baseline N ≤ 25%. Geometry on every kept trade, re-priced included. A SKIPPED clause fails.
- Stage −1: per `g`, the census over market plans; a cell is closed `refused:zero-diff` when nothing changes. Stage 0: paired MDE on fold-train, statistic standardised ΔWR, week-clustered; a refused cell can never be selected but stays a plateau neighbour. Stage 1: the `g` with the highest whole-window fold-train standardised ΔWR among cells with point ΔExpR ≥ −0.01R and Stage 0 resolvable; ties to the smaller `g`; plateau `plateau_report` 0.03R on component ExpR; a spike does not proceed. Stage 2: walk-forward folds 2021 / 2022 / 2023, `gate_win_rate`. Stage 3: one VALIDATION shot, all six v72 clauses (ΔWR > 0 at p < 0.05, ΔExpR lower bound > −0.01R, geometry lock ≤ 2%, volume cut ≤ 25%, permutation p < 0.05 with re-priced trades held fixed, mechanism).
- Windows: pilot 2018-06-01..2020-12-31 (10 tickers); fold-train 2018-06-01..2022-12-31; walk-forward 2021 / 2022 / 2023; VALIDATION 2024-01-01..2025-12-31.
- Instrument v1; `data_source` alpaca (the v162 store); universe `measure_arms.cached_universe()` with `MEASURE_ARMS_UNIVERSE=cache`; intervals `week_cluster_bootstrap`.
- Frictions: none in either arm (the v1 arm replay applies none); one adverse tick on the reclaim fill instead.
- Census health: a veto run whose `repriced_absent_from_component` exceeds 1% of `repriced_in_component + repriced_absent_from_component` stops the funnel for the partner.
- Disclosure only, never deciding: the next-open baseline against today's v1 close fill, on fold-train only (never on VALIDATION, so the later non-inferiority check keeps an unspent window); splits by source, direction and horizon with the top-two-horizon share; the `regime2` cut; ambiguous-bar sensitivity; re-priced trades in dollars on a 100,000 USD reference account at 1% risk. No earnings-proximity cut: the v1 row carries no earnings date and no as-of earnings archive exists.
- Multiple comparisons: three `g` cells searched; splits are descriptive and cannot rescue a pooled fail; the ledger row cites `ledger_qvalues`.
- A pass licenses neither knob: both stay off until the partner decides, and `MARKET_ENTRY_NEXT_OPEN` needs its own non-inferiority pre-registration.

## Pre-TRAIN disclosure: the 2026-10-21 autopsy cells re-cut to market plans

Exploratory and outside the funnel: both windows overlap the 2026 holdout, so this motivates and never selects, and nothing below changes the grid, a threshold or the prediction above. The export was read on <export date> (read-only, `scripts/ops/export_book_rows.sh`) and cut to the two committed windows (trades closed on or before 2026-10-21; the era adds trades opened, and plans created, on or after 2026-09-01). Each window shows the committed pooled autopsy, the same export unfiltered (the control: the book has moved since 2026-10-21), and the same export restricted to `entry_type = market` (`book_autopsy.py --entry-type market`). Rejection tallies carry no entry type and are unfiltered. For live market plans the bucket compares the alert-day open with the alert price, not the next open the veto reads.

<Step 6's output, pasted as printed>

<One paragraph, from the tables only: the market-only `favourable` row's N, WR and net ExpR in each window beside the pooled rows; whether the market-only rows look like the pooled cell or not, stated plainly; any book drift over 5% named. No adjective that the figures do not carry.>
```

`<export date>` is today's date (the day Step 2 ran). Then commit the doc and the eight autopsy outputs alone:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" add docs/superpowers/results/2026-10-24-v192-gap-reclaim.md docs/superpowers/results/v192/autopsy-market
git -C "$WT" status --short
git -C "$WT" commit -m "docs(v192): results record -- frozen block and the pre-TRAIN market-only autopsy disclosure, written before any run

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected `status` before the commit: only the results doc and files under `docs/superpowers/results/v192/autopsy-market/` staged; no CSV (the raw exports stay under `logs/`). Invoke the `pooled-numbers` skill before the paragraph in Step 7: every figure in it is read off the rendered tables.

# Phase 12 — The measurement runs

Order: V192-22 (Stage −1, three pilot runs), then V192-23 (fold-train: three veto runs and the basis run, Stage 0, Stage 1, the per-cell reports), then part 4b's V192-24 (Stage 2) and V192-25 (Stage 3 and the record). One `backtest-runner` at a time throughout. A stage that closes the funnel goes straight to V192-25's record steps.

### Task V192-22: Stage −1 reachability for g in 0.10, 0.25, 0.50

**Model:** sonnet — runs a finished producer and judge three times and copies their output through a fixed renderer; the judgement is limited to the stop-and-report checks spelt out below.

**Files:**
- Create (written by `measure_arms.py`): `docs/superpowers/results/v192/2026-10-24-v192-g010-pilot.json`, `2026-10-24-v192-g025-pilot.json`, `2026-10-24-v192-g050-pilot.json`, each with its `<file>.provenance.json` and its census `2026-10-24-v192-g0XX-pilot.gap_reclaim.json`
- Modify: `docs/superpowers/results/2026-10-24-v192-gap-reclaim.md` (the `## Stage −1 reachability` section)
- Scratch, never committed: `logs/v192/render_census.py`, `logs/v192/g0XX-reachability.txt`

**Interfaces:**
- Consumes: `measure_arms.py --knob ... --baseline-knob ... --stage pilot --out F --preregistration F --data-source alpaca` (V192-14), which writes `F`, `F.provenance.json` and (component delta with `GAP_RECLAIM_ATR > 0`) the census `<F stem>.gap_reclaim.json` (V192-15), and on the pilot stage exits 1 with `refused:zero-diff` when no outcome changed, after writing those files; `validate_component.py --gap-reclaim --stage reachability` (V192-18), which prints the `knobs:` / `baseline knobs:` / `split` lines, the census summary as JSON, then `REACHABLE -- the veto arms on market plans; Stage 0 may proceed.` (exit 0) or a `refused:zero-diff -- ...` line (exit 1); the census keys `knob_delta`, `baseline_knob_delta`, `signal_window`, `universe_count`, `summary` (`cells`, `total`, `gap_atr`, `verdict`), `repriced_in_component`, `repriced_absent_from_component`, `rows`; the results doc and its frozen block (V192-21).
- Produces: one reachability verdict per cell, which V192-23 reads from the results doc: a cell is **REACHABLE** only when its producer exited 0 (outcomes changed) **and** its judge printed `REACHABLE`; otherwise it is closed `refused:zero-diff` at Stage −1.

- [ ] **Step 1: Pre-flight — frozen block committed, code frozen, nothing closed covers this**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" status --short                                   # expected: empty
git -C "$WT" status --short -- swingbot/ scripts/             # expected: empty (frozen code from here)
git -C "$WT" log --oneline -3 -- docs/superpowers/results/2026-10-24-v192-gap-reclaim.md
grep -c "^## Frozen before any run\|^## Pre-TRAIN disclosure" "$WT/docs/superpowers/results/2026-10-24-v192-gap-reclaim.md"
ls "$WT/docs/superpowers/results/v192/"                      # expected: autopsy-market only
git -C "$WT" grep -n "PLATEAU_TOLERANCE_R = 0.03" -- swingbot/core/backtesting/backtest_wf.py
python "$WT/scripts/backtest/measure_arms.py" --help | grep -c "baseline-knob"
python "$WT/scripts/backtest/validate_component.py" --help | grep -c "gap-reclaim"
```

Expected: both statuses empty; the V192-21 commit listed; `2`; only `autopsy-market`; one grep hit; `1`; `1`. A missing frozen block means V192-21 has not run: stop, the disclosure must precede TRAIN. A pilot file that already exists means a run happened outside this task: stop and report it.

Invoke the `backtest-gate` skill. Then check the closed table:

```bash
python "$WT/scripts/dev/doc_section.py" "$WT/docs/claude/backtest-methodology.md" "Closed pre-registrations — do not re-run these" | grep -n -i "reclaim\|next open\|next-open\|gap toward\|gap-toward\|open gap"
```

Expected: no row closes "a same-session reclaim of the planned entry after a next-open gap toward the stop on market plans". v180's Turtle Soup row (a next-open fill on one strategy, no veto) and the `gap_volume` screen (buying after a gap *up*, which the spec says is not evidence here) are different mechanisms. If another row does close this mechanism, stop and ask the partner (`AskUserQuestion`, one question, recommended option first: "Stop: v192 re-runs <row> (Recommended)" / "Proceed: the mechanism differs because <reason>").

- [ ] **Step 2: Write the census renderer (scratch)**

Create `"$WT/logs/v192/render_census.py"` with exactly this content. It prints one cell's census and stamp from the files the producer wrote, so no number is retyped:

```python
"""v192 scratch (never committed): one cell's census sidecar and stamp as markdown."""
import json
import sys
from pathlib import Path

COUNTS = ("market_plans", "filled_at_open", "armed", "reclaimed", "ambiguous", "gap_no_reclaim",
          "open_through_stop", "risk_cap", "no_bar")


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


def health(side):
    inside, absent = side["repriced_in_component"], side["repriced_absent_from_component"]
    total = inside + absent
    share = absent / total if total else 0.0
    flag = "STOP (over 1%)" if share > 0.01 else "ok"
    print(f"census health: re-priced in component {inside}, absent from component {absent}, "
          f"absent share {share:.4%} -> {flag}\n")


def main(arms_path):
    arms = Path(arms_path)
    blob = json.loads(arms.read_text(encoding="utf-8"))
    stamp = blob["provenance"]
    prov = json.loads(Path(str(arms) + ".provenance.json").read_text(encoding="utf-8"))
    side = json.loads(arms.with_name(f"{arms.stem}.gap_reclaim.json").read_text(encoding="utf-8"))
    summary = side["summary"]
    print(f"**{arms.name}** -- stage {stamp['stage']}, window {stamp['signal_window']}, "
          f"data {prov['data_source']}, universe {side['universe_count']}, "
          f"changed outcomes {stamp['changed_outcomes']}\n")
    print(f"knobs {stamp['knob_delta']}; baseline knobs {stamp.get('baseline_knob_delta')}; "
          f"preregistration {stamp.get('preregistration')}\n")
    print(f"baseline N {len(blob.get('baseline', []))}, component N {len(blob.get('component', []))}\n")
    table(("horizon", "direction", *COUNTS, "reclaim rate", "ambiguous share"),
          [(c["horizon_key"], c["direction"], *(c[k] for k in COUNTS), c["reclaim_rate"],
            c["ambiguous_share"]) for c in summary["cells"]])
    t = summary["total"]
    table(("total", *COUNTS, "reclaim rate", "ambiguous share"),
          [("all", *(t[k] for k in COUNTS), t["reclaim_rate"], t["ambiguous_share"])])
    g = summary["gap_atr"]
    table(("gap/ATR n", *[k for k in g if k.startswith("q")], *[f">= {k}" for k in g["share_at_or_above"]]),
          [(g["n"], *[g[k] for k in g if k.startswith("q")], *g["share_at_or_above"].values())])
    health(side)
    print(f"census verdict: {summary['verdict']}")


if __name__ == "__main__":
    main(sys.argv[1])
```

- [ ] **Step 3: Pilot for g = 0.10**

Confirm `git -C "$WT" status --short -- swingbot/ scripts/` prints nothing. Invoke `backtest-gate`. Dispatch `backtest-runner` with the worktree path, the progress file (the newest `"$WT"/logs/measure_arms.*.progress`; after the two arms the census writes no percent, so the runner reports "census running" until the process exits), and:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/measure_arms.py" --knob MARKET_ENTRY_NEXT_OPEN=true --knob GAP_RECLAIM_ATR=0.1 --baseline-knob MARKET_ENTRY_NEXT_OPEN=true --stage pilot --out "$WT/docs/superpowers/results/v192/2026-10-24-v192-g010-pilot.json" --preregistration "$WT/docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md" --data-source alpaca; echo "exit $?"
```

Expected: `exit 0`, or `refused:zero-diff -- the component changed no trade on the pilot slice. Budget intact.` and `exit 1`. Either way the three files exist: `ls "$WT"/docs/superpowers/results/v192/2026-10-24-v192-g010-pilot*`. Ask the runner to report the wall time; Step 7 uses it.

- [ ] **Step 4: Pilot for g = 0.25**

After the first runner has returned, confirm the frozen-code status again, invoke `backtest-gate`, and dispatch `backtest-runner` the same way with:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/measure_arms.py" --knob MARKET_ENTRY_NEXT_OPEN=true --knob GAP_RECLAIM_ATR=0.25 --baseline-knob MARKET_ENTRY_NEXT_OPEN=true --stage pilot --out "$WT/docs/superpowers/results/v192/2026-10-24-v192-g025-pilot.json" --preregistration "$WT/docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md" --data-source alpaca; echo "exit $?"
```

Expected: as in Step 3, for `g025`.

- [ ] **Step 5: Pilot for g = 0.50**

After the second runner has returned, the same checks, then:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/measure_arms.py" --knob MARKET_ENTRY_NEXT_OPEN=true --knob GAP_RECLAIM_ATR=0.5 --baseline-knob MARKET_ENTRY_NEXT_OPEN=true --stage pilot --out "$WT/docs/superpowers/results/v192/2026-10-24-v192-g050-pilot.json" --preregistration "$WT/docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md" --data-source alpaca; echo "exit $?"
```

Expected: as in Step 3, for `g050`.

- [ ] **Step 6: The judge's reachability reading, per cell (inline, quick)**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
V="$WT/docs/superpowers/results/v192"
for cell in g010:0.1 g025:0.25 g050:0.5; do
  tag=${cell%%:*}; g=${cell##*:}
  MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/validate_component.py" --data-source alpaca --gap-reclaim --stage reachability --arms "$V/2026-10-24-v192-$tag-pilot.json" --title "v192 gap reclaim g=$g -- stage -1 reachability" --window 2018-06-01..2020-12-31 > "$WT/logs/v192/$tag-reachability.txt" 2>&1
  echo "$tag exit $?"; tail -1 "$WT/logs/v192/$tag-reachability.txt"
done
```

Expected per cell: `exit 0` with `REACHABLE -- the veto arms on market plans; Stage 0 may proceed.`, or `exit 1` with a `refused:...` line. A `refused:no-gap-reclaim-sidecar` or a stamp-gate token (`refused:...stamp...`) is a code or environment fault, not a reading: stop and report it with the file.

- [ ] **Step 7: Sanity checks before anything is read as a result**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python - "$WT" <<'PYEOF'
import json, sys
from pathlib import Path
v = Path(sys.argv[1]) / "docs/superpowers/results/v192"
problems, bases = [], {}
for tag, g in (("g010", 0.1), ("g025", 0.25), ("g050", 0.5)):
    arms = v / f"2026-10-24-v192-{tag}-pilot.json"
    blob = json.loads(arms.read_text(encoding="utf-8"))
    stamp = blob["provenance"]
    side = json.loads((v / f"2026-10-24-v192-{tag}-pilot.gap_reclaim.json").read_text(encoding="utf-8"))
    prov = json.loads(Path(str(arms) + ".provenance.json").read_text(encoding="utf-8"))
    if prov["data_source"] != "alpaca":
        problems.append(f"{tag}: data_source {prov['data_source']}")
    if stamp["knob_delta"] != {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": g}:
        problems.append(f"{tag}: knob_delta {stamp['knob_delta']}")
    if stamp.get("baseline_knob_delta") != {"MARKET_ENTRY_NEXT_OPEN": True}:
        problems.append(f"{tag}: baseline_knob_delta {stamp.get('baseline_knob_delta')}")
    if "2026-10-24-v192-gap-toward-stop-reclaim-design.md" not in str(stamp.get("preregistration")):
        problems.append(f"{tag}: preregistration {stamp.get('preregistration')}")
    if side["knob_delta"] != stamp["knob_delta"]:
        problems.append(f"{tag}: census knob_delta differs from the stamp")
    t = side["summary"]["total"]
    if t["market_plans"] <= 0:
        problems.append(f"{tag}: no market plan in the census -- the next-open path never ran")
    if t["reclaimed"] + t["gap_no_reclaim"] > t["armed"] or t["ambiguous"] > t["reclaimed"]:
        problems.append(f"{tag}: census counts inconsistent {t}")
    bases[tag] = (len(blob["baseline"]), t["market_plans"], t["open_through_stop"], t["risk_cap"])
if len(set(bases.values())) != 1:
    problems.append(f"baseline-side counts differ across cells {bases}: the baseline arm is g-independent")
print("\n".join(problems) or "pilot sane")
PYEOF
```

Expected: `pilot sane`. Any other line is a code bug, not a result: stop, report the lines, and run nothing further. The baseline arm and every count decided before the veto (market plans, open through the stop, risk cap) do not depend on `g`, so they match across the three files. The armed count falls as `g` rises, or stays equal.

Then, per cell, the census-health rule (part rule): an absent share above 1% stops the funnel for the partner's answer before anything else.

Wall-time estimate for V192-23, written into its runner briefs: `veto run ≈ pilot wall time × (cached universe size ÷ 10) × 1.8` (fold-train spans 4.6 years against the pilot's 2.6), and `basis run ≈ 0.6 × veto run` (two arms, no census). The cached universe size:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python -c "import sys; w=sys.argv[1]; sys.path[:0] = [w, w + '/scripts/backtest', w + '/scripts/data']; import measure_arms; print(len(measure_arms.cached_universe()))" "$WT"
```

- [ ] **Step 8: Write the Stage −1 section**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
for tag in g010 g025 g050; do
  python "$WT/logs/v192/render_census.py" "$WT/docs/superpowers/results/v192/2026-10-24-v192-$tag-pilot.json"
  grep -E "^(knobs|baseline knobs|split|REACHABLE|refused)" "$WT/logs/v192/$tag-reachability.txt"
done
ls -l "$WT/docs/superpowers/results/v192/"
```

Append to the results doc:

```markdown
## Stage −1 reachability (pilot 2018-06-01..2020-12-31, 10 tickers)

<For each of g = 0.10, 0.25, 0.50, a `### g = <g>` subsection: the renderer's output pasted as printed, then the judge's `knobs` / `baseline knobs` / `split` lines and its last line, then one sentence: "Producer exit <0|1> (changed outcomes <n>); judge <REACHABLE|refused:...>; cell <REACHABLE | closed refused:zero-diff at Stage −1>.">

**Stage −1 verdict:** REACHABLE cells <list>; closed cells <list or "none">. <If every cell is closed: "The funnel closes at Stage −1, budget intact (UNMEASURABLE)." Otherwise: "The funnel continues to fold-train; closed cells are still produced there and enter Stage 1 as --mde-refused.">
```

Note any evidence file of 50 MB or more (part rule: excluded locally, size and `sha256sum` recorded here).

- [ ] **Step 9: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" add docs/superpowers/results/v192/2026-10-24-v192-g010-pilot.json docs/superpowers/results/v192/2026-10-24-v192-g010-pilot.json.provenance.json docs/superpowers/results/v192/2026-10-24-v192-g010-pilot.gap_reclaim.json docs/superpowers/results/v192/2026-10-24-v192-g025-pilot.json docs/superpowers/results/v192/2026-10-24-v192-g025-pilot.json.provenance.json docs/superpowers/results/v192/2026-10-24-v192-g025-pilot.gap_reclaim.json docs/superpowers/results/v192/2026-10-24-v192-g050-pilot.json docs/superpowers/results/v192/2026-10-24-v192-g050-pilot.json.provenance.json docs/superpowers/results/v192/2026-10-24-v192-g050-pilot.gap_reclaim.json docs/superpowers/results/2026-10-24-v192-gap-reclaim.md
git -C "$WT" commit -m "docs(v192): Stage -1 reachability -- REACHABLE <cells>, closed <cells>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

`<cells>` are copied from the Stage −1 verdict line. Leave out of `git add` any file over 50 MB (part rule). If every cell is closed, skip V192-23 and V192-24 and go to V192-25's record steps (part 4b), verdict `UNMEASURABLE`.


### Task V192-23: Stages 0 and 1, plus the next-open vs close-fill basis on fold-train

**Model:** sonnet — runs finished producers, judges and the report on frozen inputs and copies their output through fixed renderers; the judgement is limited to the stop-and-report checks and the per-cell bookkeeping spelt out below.

**Files:**
- Create (written by `measure_arms.py`): `docs/superpowers/results/v192/2026-10-24-v192-g010-selection.json`, `2026-10-24-v192-g025-selection.json`, `2026-10-24-v192-g050-selection.json`, each with its `<file>.provenance.json` and its census `2026-10-24-v192-g0XX-selection.gap_reclaim.json`; `2026-10-24-v192-basis-selection.json` with its `.provenance.json` (no census: the basis delta sets no `GAP_RECLAIM_ATR`)
- Create (written by the judges and the report): `docs/superpowers/results/v192/2026-10-24-v192-stage0.json` (collected by the scratch script below from the judge output), `2026-10-24-v192-stage1.json` (`validate_component.py --out-json`), `2026-10-24-v192-g0XX-selection-report.json` and `.md` per cell (`gap_reclaim_report.py`)
- Modify: `docs/superpowers/results/2026-10-24-v192-gap-reclaim.md` (sections `## Stages 0 and 1 (fold-train 2018-06-01..2022-12-31)` and `## Next-open vs close fill (fold-train, disclosure only)`)
- Scratch, never committed: `logs/v192/collect_stage0.py`, `logs/v192/g0XX-mde.txt`, `logs/v192/stage1.txt`, `logs/v192/report-runs.txt`

**Interfaces:**
- Consumes: the Stage −1 verdict per cell from the results doc and `logs/v192/g0XX-reachability.txt` (V192-22); `logs/v192/render_census.py` (V192-22, scratch, reused unchanged); the wall-time estimate written in V192-22 Step 7; `measure_arms.py ... --stage selection` (V192-14, V192-15), whose blob carries the whole-window `baseline` / `component` rows and `train_folds` (`train_end` 2020 / 2021 / 2022, expanding); `validate_component.py --gap-reclaim --stage mde --train-effect-from-arms` and `--stage selection --grid-arms g=F --mde-refused g --out-json F` (V192-18: one `g=<v> eligible=... dWR=... ExpR=... failed=... disclosure=...` line per cell, then `verdict=<selected|no-eligible-cell|spike> selected=<g|None>`; the JSON carries `selected`); `gap_reclaim_report.py --arms F --basis F --out-json F --out-md F` (V192-18; JSON keys listed in this part's header).
- Produces: `2026-10-24-v192-stage1.json` with `selected` (a float `g` or `null`) and `verdict`, which V192-24 reads; the Stage 0 and Stage 1 sections and the basis disclosure in the results doc.

- [ ] **Step 1: Pre-flight — Stage −1 recorded, code frozen, no fold-train file yet**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" status --short                                   # expected: empty
git -C "$WT" status --short -- swingbot/ scripts/             # expected: empty
git -C "$WT" log --oneline -1 -- docs/superpowers/results/2026-10-24-v192-gap-reclaim.md   # expected: the Stage -1 commit
grep -n "^\*\*Stage −1 verdict:\*\*" "$WT/docs/superpowers/results/2026-10-24-v192-gap-reclaim.md"
for tag in g010 g025 g050; do echo "$tag: $(tail -1 "$WT/logs/v192/$tag-reachability.txt")"; done
ls "$WT"/docs/superpowers/results/v192/ | grep -c "selection\|stage0\|stage1"   # expected: 0
```

Expected: both statuses empty; the Stage −1 commit is the latest on the results doc; one verdict line; each cell's last judge line (`REACHABLE -- ...` or `refused:...`); `0`. If the scratch reachability files are gone (a fresh shell cleared `logs/`), read each cell's verdict from its `### g = <g>` subsection of the results doc instead. Write the closed cells down as `CLOSED_M1` (e.g. `CLOSED_M1="0.5"`, empty when none): Step 7 uses it. If every cell was closed at Stage −1, this task does not run: go to V192-25's record steps (part 4b), verdict `UNMEASURABLE`.

- [ ] **Step 2: Fold-train veto run for g = 0.10**

All three cells are produced here, whatever their Stage −1 reading: fold-train spends no budget and Stage 1's plateau check needs the whole frozen grid (part rules). Confirm `git -C "$WT" status --short -- swingbot/ scripts/` prints nothing. Invoke `backtest-gate`. Dispatch `backtest-runner` with the worktree path, the progress file (the newest `"$WT"/logs/measure_arms.*.progress`; "census running" after the two arms until the process exits), the wall-time estimate from V192-22 Step 7 (`veto run`), and:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/measure_arms.py" --knob MARKET_ENTRY_NEXT_OPEN=true --knob GAP_RECLAIM_ATR=0.1 --baseline-knob MARKET_ENTRY_NEXT_OPEN=true --stage selection --out "$WT/docs/superpowers/results/v192/2026-10-24-v192-g010-selection.json" --preregistration "$WT/docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md" --data-source alpaca; echo "exit $?"
```

Expected: `exit 0` and three files: `ls "$WT"/docs/superpowers/results/v192/2026-10-24-v192-g010-selection*`. The selection stage has no zero-diff exit; any non-zero exit is a fault: stop and report the runner's last 20 lines.

- [ ] **Step 3: Fold-train veto run for g = 0.25**

After the first runner has returned, confirm the frozen-code status, invoke `backtest-gate`, and dispatch `backtest-runner` the same way with:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/measure_arms.py" --knob MARKET_ENTRY_NEXT_OPEN=true --knob GAP_RECLAIM_ATR=0.25 --baseline-knob MARKET_ENTRY_NEXT_OPEN=true --stage selection --out "$WT/docs/superpowers/results/v192/2026-10-24-v192-g025-selection.json" --preregistration "$WT/docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md" --data-source alpaca; echo "exit $?"
```

Expected: as in Step 2, for `g025`.

- [ ] **Step 4: Fold-train veto run for g = 0.50**

After the second runner has returned, the same checks, then:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/measure_arms.py" --knob MARKET_ENTRY_NEXT_OPEN=true --knob GAP_RECLAIM_ATR=0.5 --baseline-knob MARKET_ENTRY_NEXT_OPEN=true --stage selection --out "$WT/docs/superpowers/results/v192/2026-10-24-v192-g050-selection.json" --preregistration "$WT/docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md" --data-source alpaca; echo "exit $?"
```

Expected: as in Step 2, for `g050`.

- [ ] **Step 5: The basis run — next open against today's close fill, fold-train only**

The spec reads the next-open baseline against today's v1 close fill as disclosure, on fold-train only, never on VALIDATION (the later non-inferiority check for `MARKET_ENTRY_NEXT_OPEN` keeps that window unspent). The pair is component `MARKET_ENTRY_NEXT_OPEN=true` against an **empty** baseline delta, so no `--baseline-knob`. After the third runner has returned, the same checks, then dispatch `backtest-runner` with the `basis run` wall-time estimate and:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/measure_arms.py" --knob MARKET_ENTRY_NEXT_OPEN=true --stage selection --out "$WT/docs/superpowers/results/v192/2026-10-24-v192-basis-selection.json" --preregistration "$WT/docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md" --data-source alpaca; echo "exit $?"
```

Expected: `exit 0`; the JSON and its `.provenance.json`, and **no** `2026-10-24-v192-basis-selection.gap_reclaim.json` (a census here means the sidecar fired on the wrong delta: stop and report it).

- [ ] **Step 6: Sanity checks before anything is read as a result**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python - "$WT" <<'PYEOF'
import json, sys
from pathlib import Path
v = Path(sys.argv[1]) / "docs/superpowers/results/v192"
spec = "2026-10-24-v192-gap-toward-stop-reclaim-design.md"
problems, baselines = [], {}
def canon(rows):
    return sorted(json.dumps(r, sort_keys=True) for r in rows)
def stamp_ok(tag, blob, path, knobs, base):
    stamp = blob["provenance"]
    prov = json.loads(Path(str(path) + ".provenance.json").read_text(encoding="utf-8"))
    if prov["data_source"] != "alpaca": problems.append(f"{tag}: data_source {prov['data_source']}")
    if stamp["stage"] != "selection": problems.append(f"{tag}: stage {stamp['stage']}")
    if stamp["knob_delta"] != knobs: problems.append(f"{tag}: knob_delta {stamp['knob_delta']}")
    if stamp.get("baseline_knob_delta") != base: problems.append(f"{tag}: baseline_knob_delta {stamp.get('baseline_knob_delta')}")
    if spec not in str(stamp.get("preregistration")): problems.append(f"{tag}: preregistration {stamp.get('preregistration')}")
    if [f["train_end"] for f in blob["train_folds"]] != ["2020", "2021", "2022"]: problems.append(f"{tag}: folds")
for tag, g in (("g010", 0.1), ("g025", 0.25), ("g050", 0.5)):
    path = v / f"2026-10-24-v192-{tag}-selection.json"
    blob = json.loads(path.read_text(encoding="utf-8"))
    stamp_ok(tag, blob, path, {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": g}, {"MARKET_ENTRY_NEXT_OPEN": True})
    side = json.loads((v / f"2026-10-24-v192-{tag}-selection.gap_reclaim.json").read_text(encoding="utf-8"))
    if side["knob_delta"] != blob["provenance"]["knob_delta"]: problems.append(f"{tag}: census knob_delta differs")
    t = side["summary"]["total"]
    if t["reclaimed"] + t["gap_no_reclaim"] > t["armed"] or t["ambiguous"] > t["reclaimed"]:
        problems.append(f"{tag}: census counts inconsistent {t}")
    baselines[tag] = canon(blob["baseline"])
basis_path = v / "2026-10-24-v192-basis-selection.json"
basis = json.loads(basis_path.read_text(encoding="utf-8"))
stamp_ok("basis", basis, basis_path, {"MARKET_ENTRY_NEXT_OPEN": True}, None)
if len({tuple(rows) for rows in baselines.values()}) != 1:
    problems.append("veto baselines differ across cells: the next-open baseline is g-independent")
if canon(basis["component"]) != baselines["g010"]:
    problems.append("basis component differs from the veto runs' baseline: both are MARKET_ENTRY_NEXT_OPEN=true alone")
print("\n".join(problems) or "fold-train sane")
PYEOF
```

Expected: `fold-train sane`. The last check is the strongest one this run has: the basis pair's component and every veto pair's baseline are the same arm with the same delta, so their rows are identical. Any other line is a code bug, not a result: stop, report the lines, and run nothing further.

Then render each veto cell's census (the same renderer as Stage −1) and apply the census-health rule (part rules: an absent share above 1% stops the funnel for the partner's answer before anything else):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
for tag in g010 g025 g050; do python "$WT/logs/v192/render_census.py" "$WT/docs/superpowers/results/v192/2026-10-24-v192-$tag-selection.json"; done
```

- [ ] **Step 7: Stage 0 — the paired MDE per cell (inline, quick)**

Run the judge on every cell that Stage −1 left REACHABLE; a cell in `CLOSED_M1` is not judged here (it is already closed) and is recorded as `closed at Stage -1`:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
V="$WT/docs/superpowers/results/v192"
CLOSED_M1="<from Step 1, e.g. 0.5, or empty>"
for cell in g010:0.1 g025:0.25 g050:0.5; do
  tag=${cell%%:*}; g=${cell##*:}
  case " $CLOSED_M1 " in *" $g "*) echo "closed at Stage -1" > "$WT/logs/v192/$tag-mde.txt"; echo "$tag closed at Stage -1"; continue;; esac
  MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/validate_component.py" --data-source alpaca --gap-reclaim --stage mde --train-effect-from-arms --arms "$V/2026-10-24-v192-$tag-selection.json" --title "v192 gap reclaim g=$g -- stage 0 MDE" --window 2018-06-01..2022-12-31 > "$WT/logs/v192/$tag-mde.txt" 2>&1
  echo "exit $?" >> "$WT/logs/v192/$tag-mde.txt"
  echo "$tag: $(tail -2 "$WT/logs/v192/$tag-mde.txt" | tr '\n' ' ')"
done
```

Expected per judged cell: `RESOLVABLE -- the shot may proceed.` with `exit 0`, or `REFUSED -- the TRAIN effect is below the minimum this sample can detect. Budget intact.` with `exit 1`. Each file must also show `gating on: paired`. Any `refused:...` token (`no-gap-reclaim-sidecar`, a stamp gate) is a code or environment fault: stop and report it.

Collect the readings into the stage file with a scratch script, so no number is retyped. Create `"$WT/logs/v192/collect_stage0.py"` with exactly this content:

```python
"""v192 scratch (never committed): Stage 0 readings per cell, collected from the judge's output."""
import json
import sys
from pathlib import Path

PREFIXES = ("train effect", "observed N", "projected target N", "paired MDE", "unpaired MDE", "gating on")


def cell(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines == ["closed at Stage -1"]:
        return {"verdict": "closed at Stage -1", "exit": None, "lines": []}
    exit_code = int(lines[-1].split()[-1])
    verdict = next((line.split(" -- ")[0] for line in lines if line.startswith(("RESOLVABLE", "REFUSED"))), None)
    return {"verdict": verdict, "exit": exit_code,
            "lines": [line for line in lines if line.startswith(PREFIXES)]}


def main(logs, out):
    cells = {g: cell((Path(logs) / f"{tag}-mde.txt").read_text(encoding="utf-8"))
             for tag, g in (("g010", "0.1"), ("g025", "0.25"), ("g050", "0.5"))}
    refused = [g for g, c in cells.items() if c["verdict"] != "RESOLVABLE"]
    blob = {"stage": "mde", "window": "2018-06-01..2022-12-31", "statistic": "standardised dWR",
            "cluster": "week", "cells": cells, "mde_refused": refused,
            "verdict": "closed" if len(refused) == len(cells) else "continue"}
    Path(out).write_text(json.dumps(blob, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(blob, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python "$WT/logs/v192/collect_stage0.py" "$WT/logs/v192" "$WT/docs/superpowers/results/v192/2026-10-24-v192-stage0.json"
```

Expected: every cell carries a verdict (`RESOLVABLE`, `REFUSED` or `closed at Stage -1`); a `null` verdict means the judge printed neither line: stop and report the file. `mde_refused` lists every cell that cannot be selected. `"verdict": "closed"` means every cell is refused or closed: the funnel closes at Stage 0 (part rules). Then skip Step 8, still run Step 9 (fold-train reports spend no budget and the record needs them), write Step 10 with the Stage 1 line "not run: every cell refused at Stage 0 or closed at Stage −1", commit (Step 11), and go to V192-25's record steps (part 4b), verdict `NO-LIFT` at Stage 0.

- [ ] **Step 8: Stage 1 — select g on the whole fold-train window (inline, quick)**

Every cell in the stage file's `mde_refused` list is passed as `--mde-refused`, so it can never be selected but stays a plateau neighbour:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
V="$WT/docs/superpowers/results/v192"
REFUSED_ARGS=$(python -c "import json, sys; print(' '.join(f'--mde-refused {g}' for g in json.load(open(sys.argv[1]))['mde_refused']))" "$V/2026-10-24-v192-stage0.json")
echo "refused args: $REFUSED_ARGS"
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/validate_component.py" --data-source alpaca --gap-reclaim --stage selection --grid-arms "0.1=$V/2026-10-24-v192-g010-selection.json" --grid-arms "0.25=$V/2026-10-24-v192-g025-selection.json" --grid-arms "0.5=$V/2026-10-24-v192-g050-selection.json" $REFUSED_ARGS --title "v192 gap reclaim -- stage 1 selection" --window 2018-06-01..2022-12-31 --out-json "$V/2026-10-24-v192-stage1.json" > "$WT/logs/v192/stage1.txt" 2>&1
echo "exit $?"; cat "$WT/logs/v192/stage1.txt"
```

Expected: three `g=<v> eligible=... dWR=... ExpR=... failed=... disclosure=...` lines and `verdict=selected selected=<g>` with `exit 0`, or `verdict=no-eligible-cell selected=None` / `verdict=spike selected=None` with `exit 1`. A `refused:...` line is a fault: stop and report it. Check the rule against the printed lines before believing the verdict: the selected `g` is eligible, it carries the highest `dWR` among eligible cells (ties to the smaller `g`), and every cell in `mde_refused` shows `eligible=False`. A mismatch is a code bug: stop and report the lines.

`no-eligible-cell` or `spike` closes the funnel at Stage 1 (part rules): still run Step 9 and Step 10, commit, then go to V192-25's record steps (part 4b), verdict `NO-LIFT` at Stage 1.

- [ ] **Step 9: Per-cell fold-train reports, with the basis (one runner)**

Every cell gets its fold-train report, selected or not (the spec reports every stage; the splits and the ambiguous sensitivity are descriptive and never decide). `--basis` is legal here because the basis pair is fold-train; it is never given on VALIDATION. Invoke `backtest-gate`. Dispatch one `backtest-runner` for the whole loop (three bootstraps in series; it reports the loop line per cell):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
V="$WT/docs/superpowers/results/v192"
for tag in g010 g025 g050; do
  MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/reports/gap_reclaim_report.py" --arms "$V/2026-10-24-v192-$tag-selection.json" --basis "$V/2026-10-24-v192-basis-selection.json" --out-json "$V/2026-10-24-v192-$tag-selection-report.json" --out-md "$V/2026-10-24-v192-$tag-selection-report.md" --data-source alpaca
  echo "$tag report exit $?" | tee -a "$WT/logs/v192/report-runs.txt"
done
```

Expected: `exit 0` for each cell, six files. `refused:not-a-basis-pair` means the basis file's stamp is not component `MARKET_ENTRY_NEXT_OPEN=true` against an empty baseline (Step 6 should have caught it): stop and report it. Any other `refused:...` is a fault: stop and report it.

Cross-check the census health the report carries against the sidecar, so the doc's two places cannot disagree:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python - "$WT" <<'PYEOF'
import json, sys
from pathlib import Path
v = Path(sys.argv[1]) / "docs/superpowers/results/v192"
for tag in ("g010", "g025", "g050"):
    rep = json.loads((v / f"2026-10-24-v192-{tag}-selection-report.json").read_text(encoding="utf-8"))
    side = json.loads((v / f"2026-10-24-v192-{tag}-selection.gap_reclaim.json").read_text(encoding="utf-8"))
    pair = {k: side[k] for k in ("repriced_in_component", "repriced_absent_from_component")}
    same = all(rep["census_health"].get(k) == val for k, val in pair.items())
    print(tag, pair, "match" if same else f"MISMATCH report={rep['census_health']}")
PYEOF
```

Expected: `match` on all three lines. A mismatch is a code bug: stop and report it.

- [ ] **Step 10: Write the Stage 0, Stage 1 and basis sections**

Print what the sections are built from:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
V="$WT/docs/superpowers/results/v192"
for tag in g010 g025 g050; do python "$WT/logs/v192/render_census.py" "$V/2026-10-24-v192-$tag-selection.json"; done
python -c "import json, sys; b = json.load(open(sys.argv[1])); [print(g, c['verdict'], *c['lines'], sep='\n  ') for g, c in b['cells'].items()]; print('mde_refused', b['mde_refused'], 'verdict', b['verdict'])" "$V/2026-10-24-v192-stage0.json"
cat "$WT/logs/v192/stage1.txt" 2>/dev/null
for tag in g010 g025 g050; do echo "===== $tag"; cat "$V/2026-10-24-v192-$tag-selection-report.md"; done
ls -l "$V"
```

Invoke the `pooled-numbers` skill, then append to the results doc:

```markdown
## Stages 0 and 1 (fold-train 2018-06-01..2022-12-31)

Both arms on the next-open market fill; the component adds `GAP_RECLAIM_ATR = g`. Whole-window rows (`blob["baseline"]` / `blob["component"]`), never the expanding folds pooled. Intervals `week_cluster_bootstrap`.

### Census per cell

<For each g: the renderer's output, as printed (it ends with the census-health line).>

### Stage 0 — paired MDE (standardised ΔWR, week-clustered)

<For each g: its verdict and the collected lines from `2026-10-24-v192-stage0.json`, as printed.>

**Stage 0:** resolvable <list>; refused <list or "none">; closed at Stage −1 <list or "none">.

### Stage 1 — selection

<`logs/v192/stage1.txt` as printed, in a fenced block; or "not run: every cell refused at Stage 0 or closed at Stage −1".>

**Stage 1 verdict:** <selected g = <g> | no-eligible-cell | spike>. <One sentence: "Stage 2 runs on g = <g>." or "The funnel closes at Stage 1; VALIDATION not spent.">

### Fold-train reports per cell (descriptive)

<For each g, a `#### g = <g>` subsection: its `-selection-report.md` pasted as rendered, minus its basis section (shown once below).>

## Next-open vs close fill (fold-train, disclosure only)

Read on fold-train only and never on VALIDATION, so the non-inferiority pre-registration `MARKET_ENTRY_NEXT_OPEN` needs before it can go live keeps an unspent window. It decides nothing here.

<The basis section of the g010 report, pasted as rendered (identical in all three reports: the basis pair does not depend on g).>
```

Note any evidence file of 50 MB or more (part rule: excluded locally, size and `sha256sum` recorded here).

- [ ] **Step 11: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
R=docs/superpowers/results/v192/2026-10-24-v192
git -C "$WT" add "$R-g010-selection.json" "$R-g010-selection.json.provenance.json" "$R-g010-selection.gap_reclaim.json" "$R-g025-selection.json" "$R-g025-selection.json.provenance.json" "$R-g025-selection.gap_reclaim.json" "$R-g050-selection.json" "$R-g050-selection.json.provenance.json" "$R-g050-selection.gap_reclaim.json" "$R-basis-selection.json" "$R-basis-selection.json.provenance.json" "$R-stage0.json" "$R-g010-selection-report.json" "$R-g010-selection-report.md" "$R-g025-selection-report.json" "$R-g025-selection-report.md" "$R-g050-selection-report.json" "$R-g050-selection-report.md" docs/superpowers/results/2026-10-24-v192-gap-reclaim.md
if [ -f "$WT/$R-stage1.json" ]; then git -C "$WT" add "$R-stage1.json"; else echo "no stage1.json (Stage 1 not run)"; fi
git -C "$WT" status --short
git -C "$WT" commit -m "docs(v192): fold-train -- Stage 0 resolvable <cells>, Stage 1 <verdict, selected g>; next-open vs close-fill basis disclosed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

`<cells>` and `<verdict, selected g>` are copied from the Stage 0 and Stage 1 verdict lines. Expected `status` before the commit: only the files above staged, nothing under `swingbot/` or `scripts/`. Leave out of `git add` any file over 50 MB (part rule). If the funnel closed at Stage 0 or Stage 1, skip V192-24 and go to V192-25's record steps (part 4b).
