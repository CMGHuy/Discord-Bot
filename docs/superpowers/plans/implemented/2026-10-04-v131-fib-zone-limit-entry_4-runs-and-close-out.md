# v131 Fibonacci Limit — Part 4: pre-registration, runs, close-out

Index, Global Constraints, Review Focus and `## Parallelisation`: `2026-10-04-v131-fib-zone-limit-entry_0-index.md`. Spec: `docs/superpowers/specs/implemented/2026-10-04-v131-fib-zone-limit-entry-design.md`.

Everything in Part 4 runs on `main` in the main tree (`E:/Documents/Private/Projects/Discord-Bot`), after V131-08's merge. `$D` is the UTC date the task starts (`date -u +%F`), fixed once per task and reused in every filename that task writes. `$P` is the committed pre-registration, `docs/superpowers/results/<V131-09's $D>-v131-preregistration.md`.

**Stop-on-fail is the rule of this part.** Each stage's verdict is read from the JSON the script wrote, never re-derived. A closing verdict writes its results document and its closed-pre-registrations row (`docs/claude/backtest-methodology.md`, table "Closed pre-registrations — do not re-run these") in the same task, commits, and jumps to V131-12. No stage is ever re-run with a changed constant, a changed universe or a changed window.

# Phase 4 — Pre-registration (sequential)

### Task V131-09: Pre-registration — its own commit, before any v131 number exists

**Files:**
- Create: `docs/superpowers/results/$D-v131-preregistration.md`

**Interfaces:**
- Consumes: the merged `scripts/backtest/measure_fib_limit.py`, `funnel.py`, the spec's measurement section, `swingbot/config.py` values as they ship.
- Produces: `$P`, which every `measure_fib_limit.py` command requires committed (`require_preregistration`).

- [ ] **Step 1: Confirm nothing has been measured.** `git ls-files docs/superpowers/results | grep v131` prints nothing; `ls data/v131_*.json` finds nothing. If any v131 TRAIN number exists anywhere (including a smoke run's printed ExpR/WR), stop: the pre-registration can no longer be written blind — report it to the partner.

- [ ] **Step 2: Collect the frozen values from the committed code, not from this plan.**

```bash
grep -n "^[A-Z_0-9]* = \|^[A-Z_0-9]*: " scripts/backtest/measure_fib_limit.py scripts/backtest/funnel.py
git log -1 --format="%h %cs" -- scripts/backtest/measure_fib_limit.py
python -c "from swingbot import config as c; print({k: getattr(c, k, None) for k in ('MIN_RISK_REWARD_RATIO','MAX_RISK_REWARD_RATIO','LEVEL_LIFECYCLE_STOPS_ENABLED','STRUCTURAL_STOP_SCOPE','FIB_LEVEL_STOP_ATR','FIB_LEVEL_STOP_DIRECTIONS','FIB_SR_CONFLUENCE_ATR','FIB_TARGET_1_0_EXTENSION','DATA_DRIVEN_STOPS_ENABLED','REGIME_GATES_ENABLED')})"
python -c "from swingbot.core.planning.params import PLAN_SHAPES, EXIT_V2_PARAMS, STRUCTURE_BUFFER_ATR; print(PLAN_SHAPES['Fibonacci Limit'], EXIT_V2_PARAMS['Fibonacci Limit'], EXIT_V2_PARAMS['Fibonacci'], STRUCTURE_BUFFER_ATR)"
python -c "from swingbot.core.market.entry_filters import DEFAULT_PARAMS, FIB_LIMIT_MIN_RETRACE, FIB_LIMIT_MIN_AGE, ATR_FLOOR_PCT, ATR_CALM_MULT; print(DEFAULT_PARAMS['Fibonacci Limit'], DEFAULT_PARAMS['Fibonacci'], FIB_LIMIT_MIN_RETRACE, FIB_LIMIT_MIN_AGE, ATR_FLOOR_PCT, ATR_CALM_MULT)"
python -c "from swingbot.core.market.strategy_types import LEGACY_HORIZONS, HORIZONS; print(LEGACY_HORIZONS); print({k: HORIZONS[k]['fib_lookback'] for k in LEGACY_HORIZONS})"
BACKTEST_CACHE_DIR=data/backtest_cache_ext python -c "import sys; sys.path[:0]=['scripts/backtest','.']; from measure_fib_confluence import _load_frames; f=_load_frames(None, None); print(len(f)); print(','.join(sorted(f))); print(max(str(x.index[-1].date()) for x in f.values()))"
```

The last command needs the local Postgres the watchlist table lives in (the same source v113 used). Required: it prints `74`. If it does not, stop and ask the partner — the spec fixes universe 74.

- [ ] **Step 3: Write the pre-registration.** Create `docs/superpowers/results/$D-v131-preregistration.md` with, in order:

1. **Header:** `# v131 pre-registration — Fibonacci Limit (resting buy limit inside the retracement zone)`; links to the spec and the plan index; "Committed before any v131 number existed. No v131 result JSON, `data/v131_*.json` or registry row exists at this commit. This document contains no performance figure." The script commit from Step 2 (`measure_fib_limit.py` last changed in `<hash>`).
2. **`## The measurement (verbatim from the spec)`** — the spec's section copied byte for byte between two marker lines. Generate it, do not retype it:

```bash
awk '/^## The measurement \(`scripts\/backtest\/measure_fib_limit.py`\)/{f=1} /^## Testing$/{f=0} f' docs/superpowers/specs/implemented/2026-10-04-v131-fib-zone-limit-entry-design.md > /tmp/v131_quote.md
```

   Paste `/tmp/v131_quote.md` between `<!-- spec-quote-begin -->` and `<!-- spec-quote-end -->`.
3. **`## The mechanism as implemented`** — the spec's arming rule, plan, fill and cancel, quoted from the spec's "The mechanism" section in summary, plus Step 2's frozen values: `DEFAULT_PARAMS['Fibonacci Limit']` (defaults only; every cell sets L and N), `FIB_LIMIT_MIN_RETRACE`, `FIB_LIMIT_MIN_AGE`, `ATR_FLOOR_PCT`, `ATR_CALM_MULT`, `STRUCTURE_BUFFER_ATR`, the `PLAN_SHAPES` and `EXIT_V2_PARAMS` rows, the R:R band, `fib_lookback` per horizon.
4. **`## Decisions the spec left open`** — the index's ten "Decisions this plan makes where the spec is silent", each verbatim, and the config values from Step 2 as they ship (level lifecycle on; structural stop scope empty; Fibonacci level stop and confluence filter as shipped — they shape the reference arm only).
5. **`## Populations`:** v2 exits, scale-out on, TP2 levels mode (Fibonacci and Fibonacci Limit have `tp2 False`, so no TP2), frictions flag on (the v2 path is frictionless; the flag only matters to v1), `one_at_a_time` on, bullish only, the ten `LEGACY_HORIZONS`.
6. **`## Universe and data`:** the 74 tickers from Step 2 (count and the sorted comma list), the extended cache, its latest bar date at this commit (informational: the holdout end is read again at the shot), survivorship bias biases longs up.
7. **`## Commands`:** exactly the commands V131-10 and V131-11 will run (copy them from those tasks with `$P` filled in).
8. **`## Multiple testing`:** six cells, no correction; the plateau rule, the profit clauses and the 13-fold check are the guard; the reference arm is reported and never selected.
9. **`## Not re-run`:** v84, v101, v102, v103 A/C, v104, v113 B — this is entry mechanics, a new mechanism (spec "Non-goals"); v124 is untouched.

- [ ] **Step 4: Verify the quote is verbatim.**

```bash
awk '/<!-- spec-quote-begin -->/{f=1;next} /<!-- spec-quote-end -->/{f=0} f' docs/superpowers/results/$D-v131-preregistration.md | diff - /tmp/v131_quote.md && echo VERBATIM
```

Expected: `VERBATIM`. Also confirm the document contains no number that could only come from a run (no WR, ExpR, N other than the spec's v103 reference figures).

- [ ] **Step 5: Commit it alone.**

```bash
git add docs/superpowers/results/$D-v131-preregistration.md
git commit -m "docs(v131): pre-register the Fibonacci Limit measurement -- six L x N cells, TRAIN 2010-2025, 13 folds, one 2026 holdout shot

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short docs/superpowers/results/
```

Expected: the status line is empty for the file (committed, clean) — `require_committed` checks exactly that.

# Phase 5 — Runs (a chain, each gated on the previous verdict)

### Task V131-10: Stages 0–2 on TRAIN (dispatch to `backtest-runner`), with stop-on-fail branches

**Files:**
- Create (local, ignored): `data/v131_collect_{2w,4w,2m,3m,4m,5m,6m,7m,8m,9m}.json`, `logs/v131_collect_<hz>.log`
- Create (committed): `docs/superpowers/results/$D-v131-stage0.json`, `$D-v131-reproduction.json`, `$D-v131-reproduction.md` (only if the reference does not reproduce), `$D-v131-train-fills.json.gz`, `$D-v131-evaluate.json` (only if Stage 0 passes), `$D-v131-train.md`
- Modify (on a closing verdict): `docs/claude/backtest-methodology.md` (one row appended to the closed table)

**Interfaces:**
- Consumes: `$P`; the script's `collect`, `stage0`, `reproduce`, `features`, `evaluate` commands.
- Produces: the evaluate JSON V131-11 reads (`proceed_to_holdout`, `winner`, `tier`), or a closing row.

- [ ] **Step 1: Load the `backtest-gate` skill** and answer its questions before the first command. The answers are already fixed by `$P`: window TRAIN 2010-01-01..2025-12-31, extended cache, universe 74, no closed knob is being re-run (this is a new mechanism), the acceptance rule is the spec's Stages 0–2, nothing is tuned after reading.

- [ ] **Step 2: Universe check.** Re-run Step 2's last command from V131-09. The sorted ticker list must equal the one in `$P` exactly. A difference stops the task: report it to the partner; do not run on a different universe.

- [ ] **Step 3: Dispatch the TRAIN collects to `backtest-runner`, chunked per horizon.** Hand it this brief verbatim (fill `$P`):

> Run from `E:/Documents/Private/Projects/Discord-Bot` on `main`, one horizon at a time, in this order: `9m 8m 7m 6m 5m 4m 3m 2m 4w 2w` (long horizons are fastest; `2w` takes ~50 min). For each `<hz>`:
> `BACKTEST_CACHE_DIR=data/backtest_cache_ext python -u scripts/backtest/measure_fib_limit.py collect --horizon <hz> --preregistration $P --out data/v131_collect_<hz>.json > logs/v131_collect_<hz>.log 2>&1`
> The script prints flushed `[k/N] P% <hz> <cell> <ticker>` lines; past 15 minutes report the percent from the log's last line. Do not open the output JSONs and do not compute or report any WR, ExpR or N — report only, per horizon: exit code, elapsed seconds (`elapsed_s` is the last key; read it with `python -c "import json; print(json.load(open('data/v131_collect_<hz>.json'))['elapsed_s'], json.load(open('data/v131_collect_<hz>.json'))['universe_n'])"`), and `universe_n`. Stop at the first non-zero exit and report the log tail. Delete each log on success.

Required from the report: ten exit codes `0`, ten `universe_n` equal to `74`. Anything else: stop and report; do not re-run with changes.

- [ ] **Step 4: Stage 0 (free).**

```bash
python scripts/backtest/measure_fib_limit.py stage0 --preregistration $P --rows data/v131_collect_*.json --out docs/superpowers/results/$D-v131-stage0.json
python -c "import json; print(json.load(open('docs/superpowers/results/$D-v131-stage0.json')))"
```

**Branch — Stage 0 fails (`passes: false`):** the mechanism closes as volume-dead, budget intact.
  - Run Step 6 (features) anyway, so B has whatever fills exist.
  - Write `docs/superpowers/results/$D-v131-train.md`: header (spec, `$P`, window, universe 74), the Stage 0 count against 30, the statement "closed at Stage 0, volume-dead; no cell, reference or fold was read; holdout budget intact".
  - Append the closing row (template below, outcome "**NO-LIFT — volume-dead at Stage 0.** Loosest cell `L=0.5, N=10` filled <fills> times on TRAIN, under the 30-fill floor. No cell or reference read; holdout budget not spent, remains available.").
  - Commit (Step 10's command, with the files that exist) and jump to V131-12.

- [ ] **Step 5: The reference reproduction (before any cell is read).**

```bash
python scripts/backtest/measure_fib_limit.py reproduce --preregistration $P --rows data/v131_collect_*.json --out docs/superpowers/results/$D-v131-reproduction.json
python -c "import json; d=json.load(open('docs/superpowers/results/$D-v131-reproduction.json')); print(d['matches'], d['expected'], d['got'])"
```

If `matches` is `false` (expected: v103's reference was universe 73 and today's is 74, and Fibonacci's path has changed since), write `docs/superpowers/results/$D-v131-reproduction.md` **before** Step 7, explaining the gap from evidence, without reading any cell:
  - the universe difference: if `data/v103_collect_A.json` exists locally, list the tickers in today's `by_ticker` that v103's `rows_by_cell["0"]` never traded and vice versa, with per-ticker trade counts; otherwise state that v103's per-ticker rows are not on disk and give the universe sizes;
  - code changes on the reference arm's path since v103's pre-registration commit `56f2f6ba`: `git log --oneline 56f2f6ba..HEAD -- swingbot/core/market/entry_filters.py swingbot/core/planning swingbot/core/backtesting/backtest.py swingbot/core/market/levels.py`, each commit with one line on whether it can move Fibonacci trades;
  - the conclusion: which of these accounts for the N / WR / ExpR difference, and that the reference arm used by Stage 1 is today's code on today's universe (the spec's "same window and universe").
  Commit the note and both JSONs before Step 7:

```bash
git add docs/superpowers/results/$D-v131-stage0.json docs/superpowers/results/$D-v131-reproduction.json docs/superpowers/results/$D-v131-reproduction.md
git commit -m "docs(v131): Stage 0 count and the reference reproduction against v103, explained before any cell is read

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Without the `.md` when `matches` is `true`.)

- [ ] **Step 6: The features record for B.**

```bash
python scripts/backtest/measure_fib_limit.py features --preregistration $P --rows data/v131_collect_*.json --out docs/superpowers/results/$D-v131-train-fills.json.gz
ls -la docs/superpowers/results/$D-v131-train-fills.json.gz
```

If the file exceeds 10 MB, ask the partner (`AskUserQuestion`, recommended option first: "commit it — B needs every fill") before committing it. Never open it to look at a feature split.

- [ ] **Step 7: Stages 1–2.**

```bash
python scripts/backtest/measure_fib_limit.py evaluate --preregistration $P --rows data/v131_collect_*.json --stage0 docs/superpowers/results/$D-v131-stage0.json --reproduction docs/superpowers/results/$D-v131-reproduction.json --reproduction-note docs/superpowers/results/$D-v131-reproduction.md --out docs/superpowers/results/$D-v131-evaluate.json
python -c "import json; d=json.load(open('docs/superpowers/results/$D-v131-evaluate.json')); print(d['closed_at'], d['proceed_to_holdout'], d['winner'], d['tier'], d['stage1']['profit_clauses'])"
```

(Drop `--reproduction-note ...` when the reproduction matched.)

- [ ] **Step 8: Write `docs/superpowers/results/$D-v131-train.md`** from the evaluate JSON only (load `pooled-numbers`; every figure is read from the JSON, none recomputed or remembered):
  - header: spec, `$P`, the JSON files, window, `universe_n`, the Stage 0 line, the reproduction line (and the note's one-line conclusion);
  - **reference arm:** N (decided), trades, WR, ExpR, scratch+timeout share, total R;
  - **cells table:** one row per cell — decided N, fills, WR, ExpR, scratch share, bootstrap lower bound, Tier 1 clauses, Tier 2 clauses, tier, total R;
  - plateau Tier 1 / Tier 2 lists, the winner and its tier, and the three profit clauses with both sides of each comparison;
  - **Stage 2** (if it ran): the 13 folds — test year, selected cell, test N, test ExpR — and the verdict line (qualifying, positive, unselected);
  - **disclosures table** (cells and reference): fill rate, placed / filled / expired / cancelled, stopped-out-within-3-bars share, cap-bind share (cells priced from the limit, reference from its close), same-bar new-high-and-fill count, top-2 horizon share against the 80% line, total R;
  - the sentence "Features recorded for B are in `$D-v131-train-fills.json.gz`; this document reports no split on any of them";
  - the limitation "No friction model; the strict trade-through fill is the only conservatism".

- [ ] **Step 9: Branch on the verdict.**
  - **`closed_at: "stage1"`** — no winner, or the winner failed a profit clause. Append the closing row: "**NO-LIFT at Stage 1 on TRAIN; holdout budget not spent, remains available.**" + the reference (N, WR, ExpR), each cell's N / WR / ExpR / tier, the plateau lists, and which clause failed with both sides.
  - **`closed_at: "stage2"`** — append: "**NO-LIFT at Stage 2 on TRAIN; holdout budget not spent, remains available.**" + the Stage 1 winner, its tier and clauses, and the fold verdict (qualifying, positive, of 13).
  - **`proceed_to_holdout: true`** — no row yet; V131-11 runs next.

  **Closed-row template** (append one line at the end of the table in `docs/claude/backtest-methodology.md`, in the house style of the v103/v104/v113 rows):

  `| Fibonacci Limit — resting buy limit at swing_high − L × leg, armed ahead of the zone, strict trade-through, cancelled above the swing high, L ∈ {0.5, 0.618} × N ∈ {3, 5, 10} (v131) | <outcome in bold>. TRAIN 2010-01-01..2025-12-31, extended cache, universe 74, bullish, ten horizons. Reference today's Fibonacci: <N, WR, ExpR>. <cell figures, plateau, clauses, folds as the branch says>. | results/$D-v131-train.md, pre-registration <$P's commit hash> |`

  Never put a backticked all-caps token in the row other than ones already listed in `.claude/hooks/guardrails.py`'s `CLOSED_PREREGISTRATION_KNOBS` (the drift test rejects it). Then `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py` — green.

- [ ] **Step 10: Commit.**

```bash
git add docs/superpowers/results/$D-v131-train.md docs/superpowers/results/$D-v131-evaluate.json docs/superpowers/results/$D-v131-train-fills.json.gz docs/claude/backtest-methodology.md
git commit -m "docs(v131): Stages 0-2 on TRAIN -- <one-line verdict: closed at Stage N / proceeds to the holdout with <winner> at Tier <t>>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Leave `backtest-methodology.md` out when the mechanism proceeds.) `require_committed` will read the evaluate JSON in V131-11, so it must be committed and clean.

### Task V131-11: Stage 3 — the one holdout shot (only if V131-10 proceeded)

**Files:**
- Create: `docs/superpowers/results/$D-v131-holdout.json`, `docs/superpowers/results/$D-v131-holdout.md`
- Modify: `docs/claude/backtest-methodology.md` (one row)
- Modify (pass only): `swingbot/core/backtesting/validation_registry.json` (via `emit-registry`)

**Interfaces:**
- Consumes: V131-10's committed evaluate JSON (`proceed_to_holdout: true`, `winner`, `tier`); `$P`.
- Produces: the holdout verdict; on a pass, one `Fibonacci Limit` registry row.

- [ ] **Step 0: Gate.** `python -c "import json; print(json.load(open('docs/superpowers/results/<V131-10 $D>-v131-evaluate.json'))['proceed_to_holdout'])"` must print `True`. Otherwise record "V131-11 skipped — closed at <stage> in V131-10" in the index's Progress line and go to V131-12.

- [ ] **Step 1: Load `backtest-gate`.** This is the one shot: the window is 2026-01-01 to the cache end at this moment; nothing about the cell, the reference or the clauses may change.

- [ ] **Step 2: Dispatch the shot to `backtest-runner`** (~10–20 min; two arms × ten horizons × 74 tickers):

> From `E:/Documents/Private/Projects/Discord-Bot` on `main`:
> `BACKTEST_CACHE_DIR=data/backtest_cache_ext python -u scripts/backtest/measure_fib_limit.py holdout --preregistration $P --evaluate docs/superpowers/results/<V131-10 $D>-v131-evaluate.json --out docs/superpowers/results/$D-v131-holdout.json > logs/v131_holdout.log 2>&1`
> Report the exit code, the log's last percent line past 15 minutes, and then only `python -c "import json; d=json.load(open('docs/superpowers/results/$D-v131-holdout.json')); print(d['status'], d.get('passes'), d.get('badge'), d['window'], d['fills'])"`. Do not re-run on any error; report it.

The script refuses a second shot, an `--out` outside `docs/superpowers/results/`, and a sealed-thin retry before the cache reaches 2026-12-31 — never work around a refusal.

- [ ] **Step 3: Branch on the verdict and write `$D-v131-holdout.md`** (figures from the holdout JSON only, `pooled-numbers`):
  - **`status: "sealed-thin"`** (fills < 15): the shot is unspent. The document states the fill count, the window, and "one retry once the extended cache reaches 2026-12-31 (the v104/v113 precedent); the retry needs a Claude session". Closing row outcome: "**Proceeded to the 2026 holdout: sealed-thin (<fills> fills < 15), shot unspent, one retry available once the cache reaches 2026-12-31.**" + the TRAIN winner, tier and figures.
  - **`passes: false`**: the shot is spent and final. Document: the clauses with both sides (including clause (a) against the reference on the same holdout), the stats, the lower bound, disclosures. Closing row outcome: "**NO-LIFT — FAILED its one holdout shot; the shot is spent and final.**" + TRAIN and holdout figures and the failing clause.
  - **`passes: true`**: the mechanism ships to the live-wiring follow-on spec. Emit the registry row:

```bash
python scripts/backtest/measure_fib_limit.py emit-registry --holdout-json docs/superpowers/results/$D-v131-holdout.json --registry swingbot/core/backtesting/validation_registry.json --run-date $D
python scripts/dev/testrun.py file tests/backtesting/test_registry.py
```

    (`emit-registry` requires the holdout JSON committed — commit it first, alone, then emit, then commit the registry.) Document: the badge (`VALIDATED` only for a Tier 1 winner that passed; `WEAK` for Tier 2), every clause, the disclosures, and "What follows" from the spec (live-wiring spec: `PlanManager` limit fills and cancels, the resting-order alert line, v93 shadow soak; `STRATEGY_GATES` stays masked until then). Closing row outcome: "**PASS on the 2026 holdout (Tier <t>, badge <VALIDATED|WEAK>); live wiring is a follow-on spec, the strategy stays masked.**" + figures.

  Row format and the guardrails check exactly as V131-10 Step 9; `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py` green.

- [ ] **Step 4: Commit.**

```bash
git add docs/superpowers/results/$D-v131-holdout.json docs/superpowers/results/$D-v131-holdout.md docs/claude/backtest-methodology.md
git commit -m "docs(v131): the 2026 holdout shot -- <sealed-thin / FAIL / PASS Tier t>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

On a pass, commit `swingbot/core/backtesting/validation_registry.json` in its own commit right after (`docs(v131): Fibonacci Limit registry row from the holdout pass`).

### Task V131-12: Close out the results

**Files:**
- Modify: `docs/strategy-types/fibonacci.md` (one line), `docs/superpowers/plans/implemented/2026-10-04-v131-fib-zone-limit-entry_0-index.md` (a `**Progress:**` line under the header)

**Interfaces:**
- Consumes: V131-10's and (if run) V131-11's committed documents and row.
- Produces: the closed record a later session reads first.

- [ ] **Step 1: Verify the record is complete.** Exactly one v131 row exists in the closed table (`grep -c "(v131)" docs/claude/backtest-methodology.md` prints `1`); it names the results document(s) and the pre-registration commit; every figure in it appears in a committed v131 JSON. If V131-10 proceeded and V131-11 ran, the row is V131-11's (V131-10 wrote none).

- [ ] **Step 2: Strategy page.** In `docs/strategy-types/fibonacci.md`, add one row at the end of the `### Research history` table (after the `| v104 | ...` row), in its style: `| v131 | "Fibonacci Limit": a resting buy limit at swing_high − L × leg, armed ahead of the zone, strict trade-through, cancelled above the swing high (L ∈ 0.5/0.618, N ∈ 3/5/10) | <outcome, one clause, with the closing stage or the holdout verdict; "ships masked"> |`. Below the table's "Main open problem" paragraph nothing changes: today's Fibonacci entry, plan, exits and badge row are untouched by v131.

- [ ] **Step 3: Progress line.** Under the index's `**Edge:**` line add `**Progress:** Closed <date>. V131-01 … V131-10 done; V131-11 <ran: verdict | skipped: closed at Stage N>; V131-12 done; V131-13 <pending | result>.` If the spec's `Edge:` prediction proved wrong (e.g. adverse selection ate the price improvement), amend the spec's `**Edge:**` line with one clause saying so, per `document-conventions.md`.

- [ ] **Step 4: Commit.**

```bash
git add docs/strategy-types/fibonacci.md docs/superpowers/plans/implemented/2026-10-04-v131-fib-zone-limit-entry_0-index.md
git commit -m "docs(v131): close out the results -- strategy page and plan progress

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Hand-off.** Moving the spec and plan to `implemented/` or `no-lift/` is `/close-out`'s job (`document-lifecycle.md`); the Skill tool refuses to run it, so ask the partner to type `/close-out` after V131-13. On a sealed-thin result, the follow-up is a session after the cache reaches 2026-12-31 — record that in the holdout document, do not schedule a laptop job.

# Phase 6 — Verification

### Task V131-13: Full-suite verification

**Files:** none (fixes only, in whatever file a failure names).

- [ ] **Step 1: Run the suite once.** Dispatch the `test-runner` subagent with `python scripts/dev/testrun.py full` on `main`, over everything Phases 0–5 merged. Expect `0 failed`, `0 xfailed`. No frontend file was touched, so no `npm test`.

- [ ] **Step 2: If not green, fix forward.** The failures are this plan's regressions until shown otherwise. A failure in a file v131 never touched that also fails on the pre-merge commit (`git worktree add <tmp> <V131-08 merge>^1` and run that one test file there) is pre-existing: report it to the partner with the evidence; do not mark the plan green and do not add an `xfail`.

- [ ] **Step 3: Record.** Fill V131-13's result into the index's `**Progress:**` line (pass count, `0 failed`, `0 xfailed`) and commit (`docs(v131): full suite green -- <n> passed`). No release: `Bump: none`; `VERSION.json` is not touched.
