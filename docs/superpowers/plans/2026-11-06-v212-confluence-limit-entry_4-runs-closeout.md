# v212 — Confluence limit entry, part 4: runs and close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier. **Never read a part whole**: `grep -n "^### Task V212-16:" -A 330 <this file>`.

**Spec:** [v212 — Confluence limit entry partway to the support](../specs/2026-11-06-v212-confluence-limit-entry.md) (§ The rule (frozen here) and § Pass rule are the pre-registration; rule 6 as corrected in e5dd654f)
**Index:** [`2026-11-06-v212-confluence-limit-entry_0-index.md`](2026-11-06-v212-confluence-limit-entry_0-index.md) — Goal, Architecture, **Global Constraints**, Review Focus, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.
**Previous:** [part 3, V212-11..V212-14](2026-11-06-v212-confluence-limit-entry_3-measurement.md) — the replay module, the portfolio pass, the measure script `scripts/backtest/measure_confluence_limit.py` and the disclosures module this part runs.
**Brief:** `.superpowers/briefs/2026-11-06-v212-confluence-limit-entry.md`

Tasks V212-15 .. V212-17: the pre-registration record committed before any
compute, the Stage −1 census and `observed_n`, Stages 0 → 3 through the
`backtest-runner` agent, the results doc and one ledger row per look, the
verdict record (a closed row, or a pass report to the partner), `/panel` and
`/close-out`.

**Where these run.** On `main` in the main tree
(`E:/Documents/Private/Projects/Discord-Bot`), **after** V212-1..V212-14 are
merged and the CI run on that push is green. Never in the v212 worktree:
the rows must come from the merged code. Never `cd` in Bash; every command
below runs from the repo root with repo-relative paths, and
`backtest-runner` gets absolute paths. No task here reads the database, so
none needs `/replicate-prod-db`; no task runs the full suite.

**Names consumed from part 3** (index ledger, V212-11..V212-14):
`scripts/backtest/measure_confluence_limit.py` with subcommands `census`
and `rows` (V212-13: `--window train` only, `rows --touch`, `--cells`,
`--preregistration` (required), `--out` = a **directory**, default
`docs/superpowers/results/v212`, `--checkpoint-dir`, `--tickers`, `--workers`;
output `<out>/v212-<command>-<window>[-touch]-rows.json`), and `stage --stage
{-1,0,1,2,3}` and `ledger` (V212-13c; `stage --stage 3` builds the VALIDATION
rows itself, for the selected cell only; stage files `stage-1.json`,
`v212-stage0.json` .. `v212-stage3.json` under `docs/superpowers/results/v212/`); its constants `REQUIRES`, `FILLS_SHARE = 0.5`,
`WR_SLACK_PP = 2.0`, `THIN_PER_DIRECTION = 30`; `require_preregistration(path)`;
`confluence_limit_replay.F_GRID`, `cell_key`, `CELLS`, `census_row` (keys
`scope`, `d`, drops, `filled` per cell); `confluence_limit_disclosures.render_disclosures(d)`.
V212-15 Step 1 prints every subcommand's `--help`; a flag this part passes
that the help does not list, or a required flag this part does not pass, is a
stop (report it, never improvise a flag).

## Rules for every measurement task (V212-15, V212-16)

- **Invoke the `backtest-gate` skill before every `measure_confluence_limit.py` command**, not after.
- **Every driver command carries the same environment on one line:**

  ```bash
  MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python -u scripts/backtest/measure_confluence_limit.py <subcommand> <args>
  ```

  `BACKTEST_CACHE_DIR` names the flat CSV cache backtests read (v131
  precedent); live root `market_data/` is never read here except the earnings
  CSVs for one disclosure.
- **Dispatch the `backtest-runner` agent for `census`, `rows` and every
  `stage` command** (each replays ten horizons over the cache universe or
  bootstraps three cells and can pass 15 minutes). Give it the exact command,
  the repo root, the checkpoint directory `logs/v212/ckpt-<unit>/` and the
  log `logs/v212/<unit>.log`. **One runner at a time**, never two.
- **Checkpointed.** `census` and `rows` write one file per finished ticker
  under `--checkpoint-dir` and skip finished tickers on a restart; a crash is
  recovered by re-running the same command, never by deleting the directory.
  Runs past 15 minutes print a flushed percent (`python -u`).
- **Frozen code.** From the pre-registration commit to the last stage file,
  make no edit under `swingbot/` or `scripts/`. Before each run,
  `git status --short -- swingbot/ scripts/` is empty. Another session's
  commit to those paths on `main` during the runs is a stop: report it.
- **A stage that does not advance ends the chain**: refused at Stage −1,
  `UNDERPOWERED` at Stage 0, no plateau at Stage 1, `FAIL` at Stage 2,
  `FAIL` or `THIN` at Stage 3. Record it as measured and go to the record
  steps. Never widen a window, add a cell, change a threshold or the MDE
  ceiling, delete a stage file, or re-run Stage 3. Stages −1..2 are
  deterministic; re-running one is allowed only to recover from a crash.
- **The driver enforces stage order** (`REQUIRES`). When it prints
  `refused: ...`, read the message and stop; never work around it.
- **Numbers come only from the stage JSON files**, through the renderer.
  Invoke the `pooled-numbers` skill before quoting any ExpR, win rate or N in
  the results doc, a commit message, the closed table or the ledger.
- **Rows files are evidence and are committed** (v139 precedent) when each is
  under 50 MB. One of 50 MB or more is not committed: add its path to
  `.git/info/exclude` (local only) and record its size and `sha256sum` in
  the results doc.
- `CONFLUENCE_LIMIT_ENTRY_F` stays `"0"` in `swingbot/config.py`,
  `.env.example` and production, whatever the verdict. A pass goes to the
  partner, who decides via `mirror-prod`.

**Windows (v139 precedent, the part 3 header).** TRAIN 2020-01-01..2023-12-31
(Stages −1, 0, 1, 2); Stage 2 folds 2021 / 2022 / 2023; VALIDATION
2024-01-01..2025-12-31 (Stage 3, one shot, the selected cell only).

# Phase E — runs and close-out

### Task V212-15: Pre-registration record, committed before any compute

**Model:** sonnet — fills a fixed document from command output and runs a scratch check; the only judgement is the stop-and-report pre-flight written out below.

**Files:**
- Create: `docs/superpowers/results/<D>-v212-preregistration.md` (`<D>` = the UTC date printed in Step 2; V212-16 and V212-17 find the file with `ls docs/superpowers/results/*-v212-preregistration.md`)
- Scratch, never committed (`logs/` is git-ignored): `logs/v212/cli-help.txt`, `logs/v212/universe.txt`, `logs/v212/spec_quote.py`, `logs/v212/check_prereg.py`

**Interfaces:**
- Consumes: `scripts/backtest/measure_confluence_limit.py` (`--help` of `census`, `rows`, `stage`, `ledger`; `require_preregistration`, `REQUIRES`, `FILLS_SHARE`, `WR_SLACK_PP`, `THIN_PER_DIRECTION`; V212-13), `confluence_limit_replay.F_GRID` / `cell_key` / `census_row` (V212-11), `builders.LIMIT_STOP_BUFFER` / `LIMIT_EXPIRY_BARS` / `LIMIT_DROP_REASONS` (V212-2), `reachability.REGISTRY["CONFLUENCE_LIMIT_ENTRY_F"]` (V212-1), `measure_arms.cached_universe` / `load_frame` (existing).
- Produces: the committed pre-registration `docs/superpowers/results/<D>-v212-preregistration.md` (`$P`) that every later command passes as `--preregistration`, ending in the line `Not yet computed.` under `## observed_n`, which V212-15b replaces; `logs/v212/cli-help.txt`, `logs/v212/universe.txt` (`<N>` on line 1), read by V212-15b.

- [ ] **Step 1: Pre-flight — merged, green, frozen, nothing closed covers this**

```bash
git fetch origin
git status --short -- swingbot/ scripts/                      # expected: empty
git rev-parse HEAD origin/main                                 # expected: equal
git log --oneline -1 --merges --grep="v212"                    # expected: the merge of the v212 branch
gh run list --branch main --limit 3                            # expected: the run on that push is completed / success
ls docs/superpowers/results/v212 docs/superpowers/results/*-v212-* 2>/dev/null   # expected: nothing
git grep -n "FILLS_SHARE = 0.5\|WR_SLACK_PP = 2.0\|THIN_PER_DIRECTION = 30\|def require_preregistration\|^REQUIRES = " -- scripts/backtest/measure_confluence_limit.py
git grep -n "^F_GRID = \|def cell_key\|def census_row\|def paired_alerts" -- swingbot/core/backtesting/confluence_limit_replay.py
git grep -n "def render_disclosures" -- swingbot/core/backtesting/confluence_limit_disclosures.py
git grep -n "LIMIT_STOP_BUFFER = 0.0025\|LIMIT_EXPIRY_BARS = 3\|LIMIT_DROP_REASONS = " -- swingbot/core/planning/builders.py
git grep -n '"CONFLUENCE_LIMIT_ENTRY_F"' -- swingbot/core/backtesting/arms/reachability.py
mkdir -p logs/v212
for s in census rows stage ledger; do echo "== $s"; python scripts/backtest/measure_confluence_limit.py $s --help; done > logs/v212/cli-help.txt 2>&1
grep -n -- "^== \|--checkpoint-dir\|--out\|--preregistration\|--window\|--touch\|--stage\|required" logs/v212/cli-help.txt
```

Expected: every grep hits; `cli-help.txt` names `--checkpoint-dir`, `--out`, `--preregistration` and `--window` on `census` and `rows`, `--touch` on `rows`, `--stage` and `--preregistration` on `stage`, and a `ledger` usage. A required flag on `stage` or `ledger` other than `--stage`, `--preregistration` and `--out` is passed as the help prints it, in every command below and in the record. A missing subcommand or flag, a red CI run, an unmerged task or an existing v212 results file is a stop: report it, run nothing.

Invoke `backtest-gate`. Then check the closed table:

```bash
grep -n "v212\|resting buy limit\|limit partway\|Fibonacci Limit" docs/claude/backtest-methodology.md
```

Expected: only the v131 Fibonacci Limit row (a strategy-source limit inside the Fibonacci zone; the spec's § Why separates it). A row that closes "a resting limit partway from market to the confluence level, stop under that level" is a stop: ask the partner (`AskUserQuestion`, one question, recommended option first: "Stop: v212 re-runs <row>").

- [ ] **Step 2: Read the frozen facts**

```bash
date -u +%F                                                     # <D>
git log -1 --format=%h -- docs/superpowers/specs/2026-11-06-v212-confluence-limit-entry.md   # <SPEC>
git log -1 --format=%h --merges --grep="v212"                   # <MERGE>
python -c "from swingbot import config; print(getattr(config, 'TRAINING_DATA_SOURCE', 'yfinance'))"   # <SOURCE>
MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python -c "import sys; sys.path[:0]=['scripts/backtest','.']; from measure_arms import cached_universe, load_frame; u=cached_universe(); f={t: load_frame(t) for t in u}; k=sorted(t for t, x in f.items() if x is not None and len(x)); print(len(k)); print(','.join(k)); print(max(str(f[t].index[-1].date()) for t in k))" > logs/v212/universe.txt
sed -n 1p logs/v212/universe.txt; sed -n 3p logs/v212/universe.txt
```

Expected: `<N>` (line 1) between 60 and 80 tickers; `<LATEST>` (line 3) on or after 2025-12-31, so VALIDATION is complete. A latest bar before 2025-12-31 is a stop: the cache needs `python scripts/data/fetch_backtest_data.py` (network) first, and the partner is asked before fetching.

- [ ] **Step 3: Extract the spec's frozen text verbatim (scratch)**

Create `logs/v212/spec_quote.py`:

```python
"""v212 (scratch): the spec's frozen sections, byte for byte, for the pre-registration."""
from pathlib import Path

SPEC = Path("docs/superpowers/specs/2026-11-06-v212-confluence-limit-entry.md")
START, END = "## The rule (frozen here)", "## Goals"


def quote() -> str:
    text = SPEC.read_text(encoding="utf-8")
    start, end = text.index(START), text.index(END)
    return text[start:end].rstrip().replace("\n## ", "\n### ") + "\n"


if __name__ == "__main__":
    body = quote()
    body = "### " + body[len("## "):]           # demote the first heading too
    Path("logs/v212/spec_quote.md").write_text(body, encoding="utf-8")
    print(len(body.splitlines()), "lines")
```

Run `python logs/v212/spec_quote.py`. Expected: about 190 lines (§ The rule, the grid, § Pass rule with its disclosures).

- [ ] **Step 4: Write the pre-registration record**

Create `docs/superpowers/results/<D>-v212-preregistration.md`. Replace each `<...>` token with the value Step 2 printed or the line named (values read, never chosen; `<ENV>` stays as written) and paste `logs/v212/spec_quote.md` between the two markers unchanged:

````markdown
# v212 pre-registration — Confluence limit entry partway to the support

**Spec:** `docs/superpowers/specs/2026-11-06-v212-confluence-limit-entry.md`, last changed in `<SPEC>`.
**Plan:** `docs/superpowers/plans/2026-11-06-v212-confluence-limit-entry_0-index.md`.
**Code:** `main` at `<MERGE>` (V212-1..V212-14 merged, CI green). No edit under `swingbot/` or `scripts/` until the last stage file is committed.
**Driver:** `scripts/backtest/measure_confluence_limit.py`; stage files under `docs/superpowers/results/v212/`.
**Committed before any compute.** `observed_n` is appended after the outcome-blind Stage −1 census, in its own commit, before Stage 0 (plan index § OPEN).

## The measurement (verbatim from the spec)

<!-- spec-quote-begin -->
(paste logs/v212/spec_quote.md here, unchanged)
<!-- spec-quote-end -->

## The mechanism as implemented

| Item | Value | Where |
|---|---|---|
| Knob | `CONFLUENCE_LIMIT_ENTRY_F`, default `"0"` (inert); the driver sets `f` per cell | `swingbot/config.py`, `ScanParams.confluence_limit_entry_f` |
| Scope | confluence plan, `entry_type` today `market` (not breakout), `builders.clamped_distance(M, level, is_bull) is not None` (level more than 2% from M); never `stop_moved_by` | `builders.apply_confluence_limit` |
| Limit | `L = M − f·(M − S)`, rounded to the tick toward M | `builders.confluence_limit_geometry` |
| Stop | `S·(1 − 0.0025)` long, `S·(1 + 0.0025)` short, rounded to the tick away from L | `builders.LIMIT_STOP_BUFFER = 0.0025` |
| Drops | `limit_stop_beyond_cap` when `(L − stop)/L > 2%`; `limit_rr_fail` when TP1 fails `MIN_RISK_REWARD_RATIO` from L; `limit_scope` when the rounded geometry is degenerate | `builders.LIMIT_DROP_REASONS` |
| Expiry | bars t+1..t+3 in replay | `builders.LIMIT_EXPIRY_BARS = 3` |
| Fill | trade-through (low ≤ L − tick) primary, touch as the disclosed sensitivity (`rows --touch`); open ≤ L fills at the open; a fill at or through the stop fills and stops at the open (`filled_stopped_gap`, outcome `loss`, about 0R less frictions); TP1 cancel inclusive; a bar reaching both L and TP1 cancels | `planning/limit_entry_rule.bar_outcome` |
| Frictions | `swingbot/core/edge/frictions.py`, both arms, every trade, at scoring | `confluence_limit_replay.net_r` |
| Portfolio pass | heat, sector, cluster, `MAX_OPEN_POSITIONS`, `MAX_POSITION_SIZE_PCT`, `MAX_POSITION_VALUE_ABSOLUTE`; arm signals dated at the fill date; both arms scored on the pass's kept trades | `backtest_wf.portfolio_replay`, `measure_confluence_limit.portfolio_pass` |
| Grid | `F_GRID = (1/3, 1/2, 2/3)`, cells `f0.333`, `f0.5`, `f0.667`; looks: 3 | `confluence_limit_replay.F_GRID` |
| Clauses | (1) arm ExpR > reference ExpR; (2) arm fills ≥ `FILLS_SHARE` = 0.5 × reference trades, pooled directions; (3) arm win rate ≥ reference − `WR_SLACK_PP` = 2.0 pp; point estimates | `measure_confluence_limit.clauses` |
| Gate family | harvest; Stage 2 `backtest_wf.gate_expectancy_harvest`; clause 2 replaces `VOLUME_MAX_CUT_PCT` | `measure_confluence_limit.py` |
| Stage chain | `REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}` | `measure_confluence_limit.REQUIRES` |
| Plateau | best cell clearing clauses 1–3 whose every grid neighbour clears them too (⅓ and ⅔ have one neighbour); tie rule as `plateau()`'s docstring states: `<paste the docstring's tie sentence>` | `measure_confluence_limit.plateau` |
| Thin seal | fewer than `THIN_PER_DIRECTION` = 30 filled trades per direction at Stage 3 is THIN, never a pass | `measure_confluence_limit.thin` |

## Decisions the spec left open (plan index § OPEN, author's calls)

- `limit_scope` is the drop for an in-scope plan whose rounded geometry is degenerate (L not strictly between the stop and M, or a non-finite level). Out-of-scope plans are untouched and never counted as drops.
- `filled_stopped_gap` is never a placeholder discard: the fill is persisted and closed by the stop, so the realised loss stays in the book.
- `observed_n` per cell is the number of in-scope TRAIN alerts whose arm limit filled (the paired keys of Stage 0), appended below after the census.
- Windows follow v139: TRAIN 2020-01-01..2023-12-31; folds 2021 / 2022 / 2023; VALIDATION 2024-01-01..2025-12-31.
- Ledger verdict mapping (the ledger enum has no UNDERPOWERED or THIN): refused at Stage −1 → `UNMEASURABLE`; UNDERPOWERED, no plateau or Stage 2 FAIL → `NO-LIFT` (v191 precedent); the selected cell's Stage 3 FAIL / THIN / PASS → `FAIL` / `INCONCLUSIVE` / `PASS`, the other two looks `NO-LIFT`.

## Populations

- Confluence plans only, both directions, pooled for the verdict; per-direction disclosed. Strategy-source and breakout plans are outside the population.
- Reference arm: today's market entry and clamped stop on each cell's own in-scope plans (`paired_alerts`, derived from one knob-0 replay, so both arms share the plan stream and the cooldown).
- Horizons and replay gates: the driver's defaults, as `logs/v212/cli-help.txt` prints them: `<paste the default-horizons help line>`.

## Universe and data

- Universe `measure_arms.cached_universe()` with `MEASURE_ARMS_UNIVERSE=cache`: `<N>` tickers, latest bar `<LATEST>`.
- Cache `data/backtest_cache_ext` (`BACKTEST_CACHE_DIR`); `data_source` `<SOURCE>` (v162: named here before TRAIN is read). Survivorship bias favours longs; it applies to both arms alike.
- Tickers: `<paste line 2 of logs/v212/universe.txt>`

## Commands

`$P` = this file. Every command runs from `E:/Documents/Private/Projects/Discord-Bot` on `main`, with the environment `MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext`, written `<ENV>` below:

```bash
<ENV> python -u scripts/backtest/measure_confluence_limit.py census --window train --preregistration $P --checkpoint-dir logs/v212/ckpt-census-train --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py stage --stage -1 --preregistration $P --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py rows --window train --preregistration $P --checkpoint-dir logs/v212/ckpt-rows-train --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py rows --window train --touch --preregistration $P --checkpoint-dir logs/v212/ckpt-rows-train-touch --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py stage --stage 0 --preregistration $P --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py stage --stage 1 --preregistration $P --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py stage --stage 2 --preregistration $P --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py stage --stage 3 --preregistration $P --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py ledger --preregistration $P
```

Outputs: `docs/superpowers/results/v212/v212-census-train-rows.json`, `v212-rows-train-rows.json`, `v212-rows-train-touch-rows.json`, `stage-1.json`, `v212-stage0.json` .. `v212-stage3.json`. Stage 3 (which builds the VALIDATION rows for the selected cell) runs once, only after Stage 2 PASS.

## Multiple testing

Three looks (`f0.333`, `f0.5`, `f0.667`), pooled over both directions. They enter the ledger's `ledger_qvalues` BH family as three rows; the q-values are reported, never gating. The guards are the plateau rule, the three clauses, the Stage 2 folds and the one Stage 3 shot.

## Not re-run

v131 (Fibonacci Limit, strategy source), v139 arms S and D, v191 arms K and R and the v115 clamp are untouched: this moves the **entry** on clamped **confluence** plans, a mechanism no closed row covers (spec § Why). A fail closes this rule; another f, buffer, expiry or a limit at the support is not a new mechanism (spec § Anti-goals).

## observed_n (appended after the Stage −1 census, before Stage 0)

Not yet computed.
````

- [ ] **Step 5: Check the record (scratch test), then commit it alone**

Create `logs/v212/check_prereg.py`:

```python
"""v212 (scratch): the pre-registration carries every frozen item and the verbatim spec text."""
import glob
import re
import sys
from pathlib import Path

sys.path[:0] = ["logs/v212"]
from spec_quote import quote  # noqa: E402

REQUIRED = ("f0.333", "f0.5", "f0.667", "0.0025", "FILLS_SHARE", "WR_SLACK_PP", "THIN_PER_DIRECTION",
            "2020-01-01..2023-12-31", "2024-01-01..2025-12-31", "gate_expectancy_harvest",
            "ledger_qvalues", "MEASURE_ARMS_UNIVERSE=cache", "backtest_cache_ext", "## observed_n")


def main() -> int:
    paths = glob.glob("docs/superpowers/results/*-v212-preregistration.md")
    assert len(paths) == 1, paths
    text = Path(paths[0]).read_text(encoding="utf-8")
    body = text.split("<!-- spec-quote-begin -->\n")[1].split("<!-- spec-quote-end -->")[0]
    expected = "### " + quote()[len("## "):]
    assert body == expected, "spec quote is not verbatim"
    missing = [item for item in REQUIRED if item not in text]
    assert not missing, missing
    left = [t for t in re.findall(r"<[A-Z]+>|<paste [^>]+>", text) if t != "<ENV>"]
    assert not left, f"unfilled tokens: {left}"
    print("prereg ok:", paths[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run `python logs/v212/check_prereg.py`. Expected: `prereg ok: docs/superpowers/results/<D>-v212-preregistration.md`. A failed assertion names what to fix in the record; fix it and re-run.

```bash
git add docs/superpowers/results/<D>-v212-preregistration.md
git commit -m "docs(v212): pre-registration record -- frozen before any compute" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
P=$(ls docs/superpowers/results/*-v212-preregistration.md)
python -c "import sys; sys.path[:0]=['scripts/backtest','.']; from measure_confluence_limit import require_preregistration; require_preregistration(sys.argv[1]); print('accepted')" "$P"
```

Expected: `accepted`.

Stop here. V212-15b runs the census only after this commit is on `main`.

### Task V212-15b: Stage −1 census and `observed_n`, before Stage 0

**Model:** sonnet — runs a finished driver through `backtest-runner` and copies its output through a fixed renderer; the only judgement is the stop-and-report sanity checks written out below.

**Files:**
- Create (driver output): `docs/superpowers/results/v212/v212-census-train-rows.json`, `docs/superpowers/results/v212/stage-1.json`
- Modify: `docs/superpowers/results/<D>-v212-preregistration.md` (the `## observed_n` section only: `Not yet computed.` becomes one line per cell)
- Scratch, never committed (`logs/` is git-ignored): `logs/v212/render_stage.py` (V212-16 reuses it), `logs/v212/observed_n.py`, `logs/v212/ckpt-census-train/`, `logs/v212/census-train.log`, `logs/v212/stage-1.log`, `logs/v212/stage-1.md`

**Interfaces:**
- Consumes: the committed pre-registration `$P` (V212-15); `measure_confluence_limit.py census` and `stage --stage -1` (V212-13); `confluence_limit_replay.census_row` keys `scope`, `d`, drops, `filled` (dict cell key → bool; V212-11); `logs/v212/universe.txt` (`<N>`, V212-15 Step 2).
- Produces: `stage-1.json`, whose `verdict` V212-16's Stage 0 requires through `REQUIRES[0] = (-1, "REACHABLE")`; the `## observed_n` section, committed before Stage 0; `logs/v212/render_stage.py`.

- [ ] **Step 0: Pre-flight**

```bash
git status --short -- swingbot/ scripts/              # expected: empty
P=$(ls docs/superpowers/results/*-v212-preregistration.md); echo "$P"
git log --oneline -1 -- "$P"                           # expected: the V212-15 commit
tail -n 1 "$P"                                         # expected: Not yet computed.
ls docs/superpowers/results/v212 2>/dev/null           # expected: nothing
python -c "import sys; sys.path[:0]=['scripts/backtest','.']; from measure_confluence_limit import require_preregistration; require_preregistration(sys.argv[1]); print('accepted')" "$P"
```

Expected: as commented; a stage file that already exists means a run happened outside this task: stop and report it.

- [ ] **Step 1: Stage −1 census through `backtest-runner`**

Invoke `backtest-gate`. Dispatch `backtest-runner` (one runner) with the repo root `E:/Documents/Private/Projects/Discord-Bot`, `$P` written out in full, the checkpoint directory `logs/v212/ckpt-census-train/`, and these two commands in order (the second only after the first exits 0):

```bash
MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python -u scripts/backtest/measure_confluence_limit.py census --window train --preregistration "$P" --checkpoint-dir logs/v212/ckpt-census-train --out docs/superpowers/results/v212 > logs/v212/census-train.log 2>&1
MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python -u scripts/backtest/measure_confluence_limit.py stage --stage -1 --preregistration "$P" --out docs/superpowers/results/v212 > logs/v212/stage-1.log 2>&1
```

Ask it to return only the exit codes, the wall time, the last percent line and the `verdict` field of `stage-1.json`.

- [ ] **Step 2: Render Stage −1 and run the sanity checks**

Create `logs/v212/render_stage.py` (generic, so no number is ever retyped, whatever keys the stage file carries):

```python
"""v212 stage renderer (scratch, never committed): markdown tables from one stage JSON."""
import json
import sys


def fmt(v):
    if v is None:
        return "—"
    return f"{v:.4f}" if isinstance(v, float) else str(v)


def table(head, rows):
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for row in rows:
        print("| " + " | ".join(fmt(x) for x in row) + " |")
    print()


def flat(d):
    return [(k, v) for k, v in d.items() if not isinstance(v, (dict, list))]


def block(name, value):
    if isinstance(value, dict) and value and all(isinstance(v, dict) for v in value.values()):
        cols = sorted({k for v in value.values() for k, x in v.items() if not isinstance(x, (dict, list))})
        print(f"**{name}**\n")
        table((name, *cols), [(key, *(v.get(c) for c in cols)) for key, v in value.items()])
        for key, v in value.items():
            for sub, x in v.items():
                if isinstance(x, (dict, list)):
                    block(f"{name}.{key}.{sub}", x)
    elif isinstance(value, dict):
        print(f"**{name}**\n")
        table(("key", "value"), flat(value))
        for sub, x in value.items():
            if isinstance(x, (dict, list)):
                block(f"{name}.{sub}", x)
    elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        cols = sorted({k for v in value for k, x in v.items() if not isinstance(x, (dict, list))})
        print(f"**{name}**\n")
        table(cols, [tuple(v.get(c) for c in cols) for v in value])
    elif isinstance(value, list):
        print(f"**{name}**: {', '.join(fmt(x) for x in value)}\n")


def main(path):
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    print(f"**Stage {d.get('stage')}: {d.get('verdict')}**\n")
    table(("key", "value"), flat(d))
    for key, value in d.items():
        if isinstance(value, (dict, list)) and key != "disclosures":
            block(key, value)


if __name__ == "__main__":
    main(sys.argv[1])
```

```bash
python logs/v212/render_stage.py docs/superpowers/results/v212/stage-1.json > logs/v212/stage-1.md
head -40 logs/v212/stage-1.md
```

Sanity checks; each failure is a stop-and-report (a geometry or wiring bug, never a result):
- the census row count is above 0 and every row has `scope` true (`paired_alerts` returns in-scope alerts only);
- each cell's smallest `d` is above 2.0% (scope) and its largest kept `d` is at most `1.75 / (1 − f) + 0.25` % (the drop rule: about 2.6 / 3.5 / 5.25%);
- the drop counts per reason are printed for every cell (`limit_scope` near 0 by construction);
- the universe count in the stage file, if it carries one, equals `<N>` (line 1 of `logs/v212/universe.txt`).

- [ ] **Step 3: Append `observed_n` and commit in two scoped commits**

Create `logs/v212/observed_n.py`:

```python
"""v212 (scratch): observed_n per cell = in-scope TRAIN alerts whose arm limit filled."""
import glob
import json
from pathlib import Path

CELLS = ("f0.333", "f0.5", "f0.667")
MARK = "Not yet computed."


def counts(rows):
    assert rows and all(isinstance(r.get("filled"), dict) for r in rows), "census_row shape changed"
    return {c: sum(1 for r in rows if r["filled"].get(c)) for c in CELLS}


def main():
    rows = json.loads(Path("docs/superpowers/results/v212/v212-census-train-rows.json").read_text("utf-8"))
    rows = rows["rows"] if isinstance(rows, dict) else rows
    obs = counts(rows)
    stage = json.loads(Path("docs/superpowers/results/v212/stage-1.json").read_text("utf-8"))
    if "observed_n" in stage:
        assert stage["observed_n"] == obs, (stage["observed_n"], obs)
    lines = [f"- `{c}`: observed_n = {obs[c]} filled keys of {len(rows)} in-scope TRAIN alerts" for c in CELLS]
    path = Path(glob.glob("docs/superpowers/results/*-v212-preregistration.md")[0])
    text = path.read_text("utf-8").rstrip()
    assert text.endswith(MARK), "observed_n already appended"
    path.write_text(text[: -len(MARK)] + "\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
```

```bash
python logs/v212/observed_n.py
ls -l docs/superpowers/results/v212/
git add docs/superpowers/results/v212/v212-census-train-rows.json docs/superpowers/results/v212/stage-1.json
git commit -m "docs(v212): Stage -1 census -- <verdict field of stage-1.json>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add "$P"
git commit -m "docs(v212): pre-registration -- observed_n per cell, appended before Stage 0" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

A census rows file of 50 MB or more is excluded and hashed instead (§ Rules). If `stage-1.json` is refused, still append `observed_n` and make both commits: the chain ends here and V212-16 runs only its record steps (Steps 6–9).

### Task V212-16: Stages 0 → 3 through `backtest-runner`; results doc; one ledger row per look

**Model:** sonnet — runs a finished driver stage by stage and records its output through a fixed renderer and the existing ledger script; the stop rules are written out, nothing is chosen.

**Files:**
- Create (driver output): `docs/superpowers/results/v212/v212-rows-train-rows.json`, `docs/superpowers/results/v212/v212-rows-train-touch-rows.json`, `docs/superpowers/results/v212/v212-stage0.json`, `docs/superpowers/results/v212/v212-stage1.json`, `docs/superpowers/results/v212/v212-stage2.json`, `docs/superpowers/results/v212/v212-stage3.json` and whatever VALIDATION rows file Stage 3 writes under `docs/superpowers/results/v212/` (each only if its stage runs)
- Create: `docs/superpowers/results/<D>-v212-confluence-limit-entry.md` (`<D>` = the date in the pre-registration's filename, so the two sort together)
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (three rows, appended by `measure_confluence_limit.py ledger`, V212-13c, which writes through `stats` the way `scripts/reports/preregistration_ledger.py` does)
- Scratch, never committed: `logs/v212/check_rows.py`, `logs/v212/check_ledger.py`, `logs/v212/stage{0,1,2,3}.md`, `logs/v212/disclosures.md`, `logs/v212/ckpt-rows-*/`, `logs/v212/*.log`

**Interfaces:**
- Consumes: `$P` with its `## observed_n` lines (V212-15, V212-15b); `stage-1.json` (V212-15b); `logs/v212/render_stage.py` (V212-15b Step 2); `measure_confluence_limit.py rows` / `stage` (V212-13); entry-row keys `key`, `arm`, `direction`, `outcome`, `r_net`, `exit_reason`, `gap_stopped`, `stop_pct`, `d_pct` (V212-11); `confluence_limit_disclosures.render_disclosures` (V212-14); `measure_confluence_limit.py ledger` (V212-13c; flags as `logs/v212/cli-help.txt` prints them).
- Produces for V212-17: the results doc with a `**Verdict:**` line (`PASS` / `FAIL` / `THIN` / `NO-LIFT (UNDERPOWERED at Stage 0)` / `NO-LIFT (no plateau at Stage 1)` / `NO-LIFT (Stage 2 FAIL)` / `UNMEASURABLE (refused at Stage −1)`) and the selected cell or `none`; ledger rows `v212-f0.333`, `v212-f0.5`, `v212-f0.667`.

- [ ] **Step 0: Pre-flight**

```bash
git status --short -- swingbot/ scripts/              # expected: empty
P=$(ls docs/superpowers/results/*-v212-preregistration.md); echo "$P"
grep -c "observed_n = " "$P"                           # expected: 3
python -c "import json; print(json.load(open('docs/superpowers/results/v212/stage-1.json'))['verdict'])"
ls logs/v212/render_stage.py
```

If `render_stage.py` is missing (a fresh machine), restore it from V212-15b's step in this plan file:

```bash
awk '/^Create .logs\/v212\/render_stage.py/{f=1;next} f&&/^.{3}python$/{p=1;next} p&&/^.{3}$/{exit} p' docs/superpowers/plans/2026-11-06-v212-confluence-limit-entry_4-runs-closeout.md > logs/v212/render_stage.py
python -c "import ast; ast.parse(open('logs/v212/render_stage.py').read()); print('ok')"
```

If the Stage −1 verdict is not `REACHABLE`, go straight to Step 6: the chain has ended.

- [ ] **Step 1: TRAIN entry rows, primary and touch, through `backtest-runner`**

Invoke `backtest-gate`. Dispatch `backtest-runner` (one runner) from `E:/Documents/Private/Projects/Discord-Bot` with `$P` written out in full and these two commands in order:

```bash
MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python -u scripts/backtest/measure_confluence_limit.py rows --window train --preregistration "$P" --checkpoint-dir logs/v212/ckpt-rows-train --out docs/superpowers/results/v212 > logs/v212/rows-train.log 2>&1
MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python -u scripts/backtest/measure_confluence_limit.py rows --window train --touch --preregistration "$P" --checkpoint-dir logs/v212/ckpt-rows-train-touch --out docs/superpowers/results/v212 > logs/v212/rows-train-touch.log 2>&1
```

Ask for exit codes, wall time and the last percent line only. Then create `logs/v212/check_rows.py` and run it on both files; a failed assertion is a wiring bug: stop and report, never patch the rows:

```python
"""v212 (scratch): structural checks on an entry-rows file; outcome-neutral."""
import json
import sys
from collections import Counter

CELLS = {"f0.333", "f0.5", "f0.667"}


def load(path):
    data = json.load(open(path, encoding="utf-8"))
    return data["rows"] if isinstance(data, dict) else data


def check(rows):
    arms = Counter(r["arm"] for r in rows)
    assert set(arms) <= CELLS | {"ref"} and arms["ref"] > 0, arms
    ref_keys = {r["key"] for r in rows if r["arm"] == "ref"}
    orphans = [r["key"] for r in rows if r["arm"] != "ref" and r["key"] not in ref_keys]
    assert not orphans, f"arm rows without a reference row: {orphans[:5]}"
    arm = [r for r in rows if r["arm"] != "ref" and r.get("filled") and not r.get("dropped")]
    wide = [r["key"] for r in arm if r["stop_pct"] > 2.0 + 1e-9]
    assert not wide, f"|L - stop| / L above 2%: {wide[:5]}"
    gaps = [r["key"] for r in arm if r["gap_stopped"] and (r["outcome"] != "loss" or r["exit_reason"] != "filled_stopped_gap")]
    assert not gaps, f"gap-through-stop not booked as a realised loss: {gaps[:5]}"
    print(dict(arms))


if __name__ == "__main__":
    for path in sys.argv[1:]:
        check(load(path))
```

```bash
python logs/v212/check_rows.py docs/superpowers/results/v212/v212-rows-train-rows.json docs/superpowers/results/v212/v212-rows-train-touch-rows.json
```

- [ ] **Step 2: Stage 0 (paired MDE)**

Invoke `backtest-gate`; dispatch `backtest-runner`:

```bash
MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python -u scripts/backtest/measure_confluence_limit.py stage --stage 0 --preregistration "$P" --out docs/superpowers/results/v212 > logs/v212/stage0.log 2>&1
python logs/v212/render_stage.py docs/superpowers/results/v212/v212-stage0.json > logs/v212/stage0.md; head -30 logs/v212/stage0.md
```

The per-cell paired N in `v212-stage0.json` equals that cell's `observed_n` in `$P`; a mismatch is a stop. `UNDERPOWERED` ends the chain (budget intact, v191): go to Step 6.

- [ ] **Step 3: Stage 1 (clauses and plateau on TRAIN)**

Invoke `backtest-gate`; dispatch `backtest-runner`:

```bash
MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python -u scripts/backtest/measure_confluence_limit.py stage --stage 1 --preregistration "$P" --out docs/superpowers/results/v212 > logs/v212/stage1.log 2>&1
python logs/v212/render_stage.py docs/superpowers/results/v212/v212-stage1.json > logs/v212/stage1.md; head -40 logs/v212/stage1.md
```

The verdict is `SELECTED` with one cell, or no plateau (the rule is closed: Step 6). Never pick a cell by hand.

- [ ] **Step 4: Stage 2 (folds 2021 / 2022 / 2023, `gate_expectancy_harvest`)**

Invoke `backtest-gate`; dispatch `backtest-runner`:

```bash
MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python -u scripts/backtest/measure_confluence_limit.py stage --stage 2 --preregistration "$P" --out docs/superpowers/results/v212 > logs/v212/stage2.log 2>&1
python logs/v212/render_stage.py docs/superpowers/results/v212/v212-stage2.json > logs/v212/stage2.md; head -30 logs/v212/stage2.md
```

`FAIL` ends the chain (Step 6). Only `PASS` spends the VALIDATION shot.

- [ ] **Step 5: Stage 3 — the one VALIDATION shot**

Commit Steps 1–4's files first (Step 8 commit (a)), so the TRAIN evidence is on `main` before VALIDATION is read. Invoke `backtest-gate`; dispatch `backtest-runner` with this command (Stage 3 builds the VALIDATION rows itself, for the selected cell only; `rows` refuses `--window validation`):

```bash
MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python -u scripts/backtest/measure_confluence_limit.py stage --stage 3 --preregistration "$P" --out docs/superpowers/results/v212 > logs/v212/stage3.log 2>&1
ls -t docs/superpowers/results/v212/ | head -3                    # the VALIDATION rows file Stage 3 wrote, if any
python logs/v212/check_rows.py docs/superpowers/results/v212/<that VALIDATION rows file>
python logs/v212/render_stage.py docs/superpowers/results/v212/v212-stage3.json > logs/v212/stage3.md; head -40 logs/v212/stage3.md
```

The verdict is `PASS`, `FAIL` or `THIN` (fewer than 30 filled trades in a direction). Stage 3 never runs twice, whatever happens next; a crash is resumed with the same command (its per-ticker checkpoint), never restarted with another window or cell.

- [ ] **Step 6: The results doc**

Render the disclosures from the last stage file that carries them (Stage 1 or 3; on an earlier end, from whichever stage file has a `disclosures` key, else write "Not computed: the chain ended at Stage <k>."):

```bash
python -c "import json, sys; from swingbot.core.backtesting.confluence_limit_disclosures import render_disclosures; d=json.load(open(sys.argv[1], encoding='utf-8')); print(render_disclosures(d['disclosures']))" docs/superpowers/results/v212/v212-stage1.json > logs/v212/disclosures.md
grep -c "D range\|direction" logs/v212/disclosures.md       # expected: at least 2 (the spec requires both)
```

Invoke `pooled-numbers`. Create `docs/superpowers/results/<D>-v212-confluence-limit-entry.md`, pasting each `logs/v212/*.md` render unchanged and filling `<...>` from the stage files and `git log`:

```markdown
# v212 — Confluence limit entry partway to the support: results

**Spec (the pre-registration):** `docs/superpowers/specs/2026-11-06-v212-confluence-limit-entry.md`.
**Pre-registration record:** `<$P>` (committed `<hash of the V212-15 commit>`; `observed_n` appended in `<hash of the V212-15b commit>`, before Stage 0).
**Plan:** `docs/superpowers/plans/2026-11-06-v212-confluence-limit-entry_0-index.md`.
**Driver:** `scripts/backtest/measure_confluence_limit.py` at `main` `<merge hash from $P>`; stage files under `docs/superpowers/results/v212/`.
**Verdict:** <one of the Produces verdicts>; selected cell `<cell or none>`. `CONFLUENCE_LIMIT_ENTRY_F` stays `0`.

## Frozen before any run

Everything frozen is in the pre-registration record above: the rule, the grid `f ∈ {⅓, ½, ⅔}` (3 looks, pooled directions), the three clauses (arm ExpR > reference; fills ≥ 50% of reference trades; win rate ≥ reference − 2 pp), the harvest gate family, the plateau and thin rules, TRAIN 2020-01-01..2023-12-31, folds 2021 / 2022 / 2023, VALIDATION 2024-01-01..2025-12-31, the universe and the data source.

## Stage −1 (census, no outcome read)

<logs/v212/stage-1.md>

## Stage 0 (paired MDE)

<logs/v212/stage0.md, or "Did not run: the chain ended at Stage <k> (<verdict>).">

## Stage 1 (clauses and plateau, TRAIN)

<logs/v212/stage1.md, or "Did not run: ...">

## Stage 2 (folds)

<logs/v212/stage2.md, or "Did not run: ...">

## Stage 3 (VALIDATION, one shot)

<logs/v212/stage3.md, or "Did not run: ...">

## Disclosures (printed, never gating)

<logs/v212/disclosures.md>

## Prediction

The `Edge:` line predicted, on filled trades: ExpR up, fewer trades, fewer noise stop-outs (stopped within 3 bars). Per cell, from Stage 1 (or the last stage that scored it): arm ExpR <x> vs reference <y>; trades <a> vs <b>; stopped within 3 bars <c> vs <d> → <hit / miss, one clause each>. A miss is recorded, never explained away.

## Evidence files

<`ls -l docs/superpowers/results/v212/` output; for any rows file of 50 MB or more, its size and `sha256sum`, and the note that it is excluded locally.>

## What follows

<PASS: "The partner decides whether to set `CONFLUENCE_LIMIT_ENTRY_F` live (via `mirror-prod`); nothing is switched on here." Otherwise: "Closed: a row in `backtest-methodology.md` § Closed pre-registrations (V212-17). Another f, buffer, expiry or a limit at the support is not a new mechanism.">
```

- [ ] **Step 7: One ledger row per look**

The results doc exists (Step 6), so every row's `record` resolves. Run the driver's `ledger` subcommand once, adding any required flag its help prints (the results doc path, if it asks for one):

```bash
python -u scripts/backtest/measure_confluence_limit.py ledger --preregistration "$P" > logs/v212/ledger.log 2>&1; cat logs/v212/ledger.log
```

It appends `v212-f0.333`, `v212-f0.5` and `v212-f0.667` and prints each BH q-value: copy the three into the results doc under `## Multiple testing (reported, never gating)`. Then check the rows against `$P` § Decisions with `logs/v212/check_ledger.py`; a mismatch is a stop (report it; never hand-edit the ledger):

```python
"""v212 (scratch): the three ledger rows match the pre-registered verdict mapping."""
import glob
import json
import re
import sys
from pathlib import Path

CELLS = ("f0.333", "f0.5", "f0.667")
LEDGER = Path("docs/superpowers/results/preregistration-ledger.jsonl")


def expected(verdict: str, selected: str, cell: str) -> str:
    if verdict.startswith("UNMEASURABLE"):
        return "UNMEASURABLE"
    staged = {"PASS": "PASS", "FAIL": "FAIL", "THIN": "INCONCLUSIVE"}
    if verdict in staged and cell == selected:
        return staged[verdict]
    return "NO-LIFT"


def main() -> int:
    record = glob.glob("docs/superpowers/results/*-v212-confluence-limit-entry.md")[0].replace("\\", "/")
    text = Path(record).read_text(encoding="utf-8")
    verdict = re.search(r"^\*\*Verdict:\*\* (\S+)", text, re.M).group(1).rstrip(";")
    selected = re.search(r"selected cell `([^`]+)`", text).group(1)
    rows = {r["id"]: r for r in map(json.loads, LEDGER.read_text("utf-8").splitlines()) if r["id"].startswith("v212-")}
    assert sorted(rows) == sorted(f"v212-{c}" for c in CELLS), sorted(rows)
    for cell in CELLS:
        row = rows[f"v212-{cell}"]
        assert row["record"] == record, (row["record"], record)
        assert row["verdict"] == expected(verdict, selected, cell), (cell, row["verdict"])
        assert row["instrument"] == "v1", row["instrument"]
    print("ledger ok:", {c: rows[f"v212-{c}"]["verdict"] for c in CELLS})
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

```bash
python logs/v212/check_ledger.py
```

```bash
python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py
python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py
```

Expected: `0 failed`, `0 xfailed`.

- [ ] **Step 8: Commit in scoped commits**

```bash
# (a) TRAIN evidence -- before Stage 3 if it runs (Step 5), otherwise here
git add docs/superpowers/results/v212/v212-rows-train-rows.json docs/superpowers/results/v212/v212-rows-train-touch-rows.json docs/superpowers/results/v212/v212-stage0.json docs/superpowers/results/v212/v212-stage1.json docs/superpowers/results/v212/v212-stage2.json
git commit -m "docs(v212): TRAIN rows and Stages 0-2 -- <last TRAIN verdict>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
# (b) VALIDATION evidence, only if Stage 3 ran
git add docs/superpowers/results/v212/v212-stage3.json docs/superpowers/results/v212/<the VALIDATION rows file Stage 3 wrote>
git commit -m "docs(v212): VALIDATION rows and Stage 3 -- <verdict>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
# (c) results doc
git add docs/superpowers/results/<D>-v212-confluence-limit-entry.md
git commit -m "docs(v212): results -- <verdict>, selected cell <cell or none>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
# (d) ledger
git add docs/superpowers/results/preregistration-ledger.jsonl
git commit -m "docs(v212): ledger rows for the three looks" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Add only the files that exist (a stage that did not run has none); a rows file of 50 MB or more is excluded and hashed (§ Rules).

- [ ] **Step 9: Hand the verdict to V212-17**

Report the `**Verdict:**` line and the selected cell to the controller. A `PASS` is reported to the partner as a result, with no recommendation to switch the knob on in the same message.

### Task V212-17: Record the verdict (closed row or pass report), `/panel`, `/close-out`

**Model:** sonnet — writes one table row from a committed results doc and runs two existing skills step by step; every judgement call is routed to the partner or the panel.

**Files:**
- Modify (no pass only): `docs/claude/backtest-methodology.md` (one row at the top of `### Closed pre-registrations — do not re-run these`)
- `AGENTS.md`: unchanged — it does not mirror the closed table (Step 1 confirms with a grep; a hit means it now does, and the row goes there too, condensed)
- Modify (via `/close-out`): `VERSION.json` (bot line, patch), `swingbot/admin/version_history.json` (regenerated); `docs/superpowers/plans/2026-11-06-v212-confluence-limit-entry_0-index.md` (`**Edge:**` line, no pass only)
- Move (via `/close-out`): the six plan files `docs/superpowers/plans/2026-11-06-v212-confluence-limit-entry_{0-index,1-rule-and-replay,3-measurement,3b-measurement-stages,3c-disclosures-wiring,4-runs-closeout}.md` (the live path is v216's plan: on a pass it stays in `plans/` for implementation; on any other verdict move v216's spec and plan to `no-lift/` in this same close-out) and the spec `docs/superpowers/specs/2026-11-06-v212-confluence-limit-entry.md` into `implemented/` (the code reached `main`, inert, as v191 did)
- Modify: the v212 results doc and pre-registration record (their spec/plan links, to the `implemented/` paths)
- Modify only if Step 5b finds a stale citation: files under `.claude/skills/` or `.claude/agents/`, and their Codex mirrors via `python scripts/dev/sync_codex.py`

**Interfaces:**
- Consumes: the results doc `docs/superpowers/results/<D>-v212-confluence-limit-entry.md` and its `**Verdict:**` line, the three ledger rows `v212-f0.333` / `v212-f0.5` / `v212-f0.667` (V212-16); `$P` (V212-15).
- Produces: nothing later tasks read; the plan is closed.

- [ ] **Step 0: Pre-flight**

```bash
git fetch origin; git rev-parse HEAD origin/main                 # expected: equal (pull first if behind)
R=$(ls docs/superpowers/results/*-v212-confluence-limit-entry.md); P=$(ls docs/superpowers/results/*-v212-preregistration.md); echo "$R $P"
grep -n "^\*\*Verdict:\*\*" "$R"
grep -c '"id": "v212-' docs/superpowers/results/preregistration-ledger.jsonl   # expected: 3
grep -n "Closed pre-registrations\|v191" AGENTS.md                              # expected: no hit
```

- [ ] **Step 1a (no pass: FAIL, THIN, NO-LIFT or UNMEASURABLE): the closed row**

Invoke `pooled-numbers`. Every number below is copied from `$R`, never recomputed. Build the row in this shape (the `(v212)` tag is what `test_every_closed_table_version_has_a_ledger_row` matches):

```markdown
| Confluence limit entry partway to the support — on clamped confluence market plans (level more than 2% from market) a resting limit at L = M − f·(M − S), stop 0.25% beyond the level, TP1/TP2 kept, 3 sessions, inclusive TP1 cancel, trade-through fill, f ∈ {⅓, ½, ⅔} (v212) | **<VERDICT in words, e.g. "NO-LIFT: no plateau at Stage 1, budget intact" / "UNDERPOWERED at Stage 0, budget intact" / "FAIL at Stage 3; VALIDATION spent" / "THIN at Stage 3; VALIDATION spent">.** TRAIN 2020-01-01..2023-12-31, <N>-ticker cache universe, <SOURCE> bars, instrument v1; observed N (filled keys) <a> / <b> / <c> (cells f0.333 / f0.5 / f0.667); <the deciding numbers of the stage where the chain ended: MDE per cell, or arm vs reference ExpR, fills share and ΔWR per cell, or fold results, or the Stage 3 clauses>; Stages <k+1>–3 did not run. 3 looks, BH q reported in the record. Reopening needs "an entry rule other than a resting limit at a fraction f of the way from market to the confluence level with the stop just beyond that level". Another f, stop buffer, expiry, or a limit at the level itself is not a new mechanism. | `results/<D>-v212-confluence-limit-entry.md`, `results/<D>-v212-preregistration.md` |
```

Insert it as the first row under the table's header, with this script (scratch, run once):

```python
"""v212 (scratch): insert the closed row at the top of the closed pre-registrations table."""
import sys
from pathlib import Path

DOC = Path("docs/claude/backtest-methodology.md")
HEADING = "### Closed pre-registrations — do not re-run these"


def insert(row: str) -> None:
    lines = DOC.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.rstrip("\n") == HEADING)
    sep = next(i for i in range(start, len(lines)) if lines[i].startswith("|---"))
    assert "(v212)" not in "".join(lines), "v212 row already present"
    lines.insert(sep + 1, row.rstrip("\n") + "\n")
    DOC.write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    insert(Path(sys.argv[1]).read_text(encoding="utf-8"))
```

Save the row to `logs/v212/closed_row.md` and the script to `logs/v212/insert_row.py`, then:

```bash
python logs/v212/insert_row.py logs/v212/closed_row.md
grep -n "(v212)" docs/claude/backtest-methodology.md            # expected: one hit, the first table row
python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py
python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py
git add docs/claude/backtest-methodology.md
git commit -m "docs(v212): closed pre-registration row -- <verdict>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: `0 failed`, `0 xfailed` in both runs.

- [ ] **Step 1b (PASS only): the pass report**

No closed row, no knob change. Ask the partner with `AskUserQuestion`, one question, recommended option first: "v212 passed at cell `<cell>` (results: `<R>`). What next?" — options: "Keep `CONFLUENCE_LIMIT_ENTRY_F` at 0 for now; switching it on is a separate `mirror-prod` task (recommended)"; "Write that switch-on task now (production `.env`, `mirror-prod`)". Record the answer as one line under `## What follows` in `$R` and commit it: `docs(v212): partner decision on the pass`. Nothing in this plan edits production.

- [ ] **Step 2: `/panel` before close-out**

Invoke the `panel` skill with the spec's `**Panel:**` roles, serially: `quant-researcher,veteran-trader,risk-manager`. Target: the plan's merged diff and its recorded results:

```bash
M=$(git log -1 --format=%h --merges --grep="v212"); echo "$M^1...$M^2"
```

Pass `"$M^1...$M^2"`, `$R`, `$P` and `docs/superpowers/results/v212/` as the target. Every `BLOCKING` finding is either fixed (code: on a new branch from `main`, its own task and tests; docs: on `main`) or recorded in `.superpowers/sdd/progress.md` as `v212 panel: <finding> -- rejected: <why>`. A finding that questions the measurement's validity goes to the partner (`AskUserQuestion`, one question); it is never answered by re-running a stage or editing a stage file.

- [ ] **Step 3: `/close-out`**

Invoke the `close-out` skill and follow it step by step. What each step comes to for v212:

- **Step 3–4 (bump):** read `VERSION.json`; `Bump:` is bot patch, so only the bot line moves. Commit `VERSION.json` alone as `release(bot): <version> -- v212 confluence limit entry (knob inert at 0), measurement <verdict>`, then `python scripts/dev/build_version_matrix.py` and commit `swingbot/admin/version_history.json` alone as `chore(bot): <version> -- v212 confluence limit entry (knob inert at 0), measurement <verdict>`.
- **Step 5 (no pass only):** in the index, replace the `**Edge:**` line with `**Edge:** expectancy, measured none — <one clause naming where the chain ended, e.g. "no cell cleared clauses 1–3 with a plateau on TRAIN">`. Fold it into the Step 6 move commit.
- **Step 5b (skills):** check every skill and agent for citations the v212 diff made stale:

  ```bash
  git grep -n "PENDING_CANCEL_EVENTS\|NOTICE_EVENTS\|PLAN_EVENT_KINDS\|cancelled_limit\|cancelled_gap_through_stop\|_step_limit\|_fill_pending\|ticket_for\|entry_line\|portfolio_replay\|simulate_exit_v2\|_limit_entry_v2\|build_confluence_plan\|clamped_distance\|plan rejected (\|limit_strict_fill\|levels-block\|BUY AT MARKET\|measure_confluence_stop" -- .claude/skills .claude/agents
  ```

  A hit is stale when it lists cancel/notice events without `cancelled_heat_at_fill` / `filled_stopped_gap`, lists plan drop reasons without `limit_scope` / `limit_stop_beyond_cap` / `limit_rr_fail`, says a limit plan prints "BUY AT MARKET", or names the gap-through-stop cancel as the only gap path for limit plans. Fix each in a `docs(skills): align <skill> with v212` commit, then `python scripts/dev/sync_codex.py` and `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py` (`0 failed`), the mirror in the same commit. No stale hit: write `skills: none affected` in the move commit's body.
- **Step 6 (move):** `git mv` the five plan files into `docs/superpowers/plans/implemented/` and the spec into `docs/superpowers/specs/implemented/`. Then repoint the links:

  ```bash
  git grep -ln "plans/2026-11-06-v212-\|specs/2026-11-06-v212-" -- docs/ | grep -v "/implemented/"
  ```

  In each listed file (at least `$R` and `$P`), change `plans/2026-11-06-v212-` to `plans/implemented/2026-11-06-v212-` and `specs/2026-11-06-v212-` to `specs/implemented/2026-11-06-v212-`; the relative links inside the moved plan files (`../specs/...`) become `../../specs/implemented/...`. Re-run the grep: no hit outside `implemented/`. Commit: `docs(v212): close out -- plan and spec to implemented/; <Edge outcome>` with the Step 5b line in the body.
- **Step 7 (worktree):** the plan closed to `implemented/`, so remove the worktree and its branch, never forcing:

  ```bash
  git worktree list | grep v212
  git rev-list --count main..2026-11-06-v212-confluence-limit-entry    # must print 0; non-zero: stop and ask the partner
  git worktree remove .claude/worktrees/2026-11-06-v212-confluence-limit-entry
  git branch -d 2026-11-06-v212-confluence-limit-entry
  ```

- [ ] **Step 4: Push and watch CI**

```bash
git push origin main
gh run watch "$(gh run list --branch main --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
```

Expected: the run is green. A failing test is fixed and re-run alone (`python scripts/dev/testrun.py file <test>`), committed, pushed, and watched again until green (`working-conventions.md` § Pipeline watch).
