# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Discord swing-trade alert bot ("swingbot"): it scans a watchlist of stock/ETF
tickers through the trading session, looks for multi-method-confirmed
support/resistance setups across 10 swing horizons (`2w`…`9m`, defined in
`swingbot/core/strategy_types.py:HORIZONS` — code is authoritative when the
README's tables lag), and posts trade-plan alerts with charts. It tracks
everything as **paper trades only** — it never places orders. Python 3.11+,
discord.py, pandas/numpy, yfinance, mplfinance, pytest. JSON persistence under
`data/`; no database.

Two entry points: `python bot.py` (the bot) and `python admin_ui.py` (Flask
admin UI). Deployed as two Docker containers off one image (`DOCKER.md`,
`DEPLOY_HETZNER.md`); `.env` is the single config source, hot-reloaded via
SIGHUP (schema lives in `swingbot/config.py` — every setting is one `Field`
entry that feeds both the env parser and the admin UI's Settings page).

## Token discipline (read first — this repo has context landmines)

- **NEVER read a plan file whole** — `cockpit-v3.md` is 662 KB, `edge-engine-v4.md`
  358 KB. Pull one task instead: `/task-brief E53` or
  `grep -n "^### Task E53" -A 120 <plan>`. `gatekeeper-v7` exists only as
  `_0-index.md` + `_1..._11` parts (the 822 KB monolith was deleted; recover it
  from git history if needed). `grep -c "^### Task"` / `grep -n "^# Phase"` to orient.
- **Grep respects the root `.ignore` file (hides `.claude/worktrees/`,
  `market_data/`, `data/`, `logs/`); Glob does not.** Always scope Glob by hand
  (`Glob("swingbot/**/*.py")`, never `**/*.py`) or it returns hundreds of
  worktree-copy matches. For symbol lookups prefer `git grep -n "def foo"`
  (tracked files only, can't see worktrees). Never edit files under
  `.claude/worktrees/` from a main-tree session.
- **README.md is 645 lines** — grep its `^## ` headers and read the one section
  you need. Same for `.superpowers/sdd/progress.md`: `tail` it, never `cat` it.
- **Don't re-run the full suite to check a local change** (~3 min) — run the
  touched file (`pytest tests/test_edge_gates.py -q`) and save the full suite
  for the pre-commit gate.
- Hand wide/exploratory searches to the `Explore` agent so raw grep output
  never lands in this context.

**Current status is not tracked here** (it drifts stale). The `SessionStart`
hook (`.claude/hooks/session-cursor.ps1`) prints it every session: active plan
+ task count, last/next task, git HEAD and dirty files, live worktrees, and any
in-progress multi-hour backtest. Completed plans: unified-plan-engine-v2,
strategy-winrate-redesign, admin-ui-tradingview-redesign-v6 (task IDs
`U1`-`U36`; manual browser QA left for a future pass). On disk but not
current focus: cockpit-v3, gatekeeper-v7, llm-advisor-v5.

**Don't trust the hook's "NEXT" task ID blind** — it can name IDs (e.g. `E89`)
that don't exist in the plan file it labels as active (which may use a
different prefix, e.g. `U34`). Verify with `grep -n "^### Task" <plan>` before
chasing a task the hook mentioned.

**Repo tooling (`.claude/`):** `/task-brief <id>` extracts one plan task and
preflights this repo's documented traps. `/gate` is the pre-commit verification
gate (knows the one permitted pre-existing failure). Subagents:
`backtest-runner` (multi-hour jobs in an isolated context, returns only
verdicts), `symbol-verifier` (`git grep` existence checks for symbols a plan
names). `.mcp.json` provides context7 for yfinance/pandas-ta/discord.py docs.

## Commands

```bash
python -m pytest tests/ -q                 # full suite, ~3min — pre-commit gate (see known failure below)
python -m pytest tests/test_foo.py::test_bar -v   # single test — use this while iterating
make check                                 # py_compile syntax pass (no make on Windows: run python -m py_compile over bot.py admin_ui.py swingbot/**/*.py)
python scripts/fetch_backtest_data.py      # populate the CSV cache (once, network) — required by every backtest/grid script
python scripts/run_backtest_range.py --train|--validation [--exit-model v2 --scale-out] [--strategy "RSI"] [--json out.json]
python scripts/tune_strategy.py --strategy "RSI" --grid key=v1,v2 --exit-model v2 --scale-out   # TRAIN-only grid
python scripts/shadow_parity_report.py     # v2-vs-legacy comparison from data/shadow_plans.jsonl
make up / make logs / make restart         # docker compose lifecycle
```

**Known-good baseline** (commit `a7d23ab`): `841 passed, 54 skipped, 1 failed`
in ~3m13s. The one failure,
`tests/test_trade_monitor_wiring.py::test_flag_on_polls_open_plans`
(`cancelled_expired` != `filled`), is pre-existing and expiry/wall-clock
dependent — don't treat it as your regression or "fix" it as a side quest.
"Green" means your diff adds no *new* failure; a different count or a second
failure is yours to fix.

Long backtest/grid runs: a full 75-ticker × 10-horizon sweep takes tens of
minutes (`replay_scenarios` is ~30s per ticker-horizon — hours for a full
grid; never run it casually). Chunk long grids per-strategy.

**Any script meant to run in the background for more than a couple of
minutes must print incremental progress** (one flushed line per unit of
work — fold/ticker/chunk — not just a final summary once everything is
done). `scripts/wf_run.py --full` is the counterexample that cost a whole
monitoring session: it only prints the fold table after `run_folds()`
fully returns, so a multi-hour run gives zero signal beyond OS-level CPU
time until the very end. When writing or invoking a new long-running
script, either confirm it already logs per-unit progress, or add a
`print(..., flush=True)` (or `log.info`) per completed unit before
kicking it off — don't discover this gap hours into an unmonitorable run.

## Reference docs

Not auto-loaded — read the relevant one before starting work in that area.

- `docs/claude/architecture.md` — core/commands/admin split, edge-engine
  module map, entry-signal single source, NO-LOOKAHEAD rule, Plan Engine v2,
  badges/registry, scan pipeline. Read before touching `swingbot/core`,
  `plan_engine`, or the scan pipeline.
- `docs/claude/known-traps.md` — the two parallel OHLCV caches, legacy shims,
  silent sizing/wiring no-ops, scan-loop ordering, symbol names plans get
  wrong. Read before touching data caching, `scan_engine`/`scan_embeds`, or
  `embeds.py`.
- `docs/claude/backtest-methodology.md` — TRAIN/VALIDATION windows, acceptance
  gates, frozen constants. Read before running or interpreting any
  backtest/grid/validation.
- `docs/claude/working-conventions.md` — commit style, concurrent-session git
  hygiene, worktrees.
- `docs/claude/skills-tools.md` — which Superpowers skill or subagent to reach
  for on a given kind of task in this repo.
