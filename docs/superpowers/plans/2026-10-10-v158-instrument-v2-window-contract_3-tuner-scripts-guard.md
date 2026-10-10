# v158 Instrument v2, phase 3: window contract and folds. Implementation Plan, part 3 (fold-selected tuner, the flag on every live script, date-literal guard, full suite)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `/task-brief WC9` or `grep -n "^### Task WC9" -A 500 docs/superpowers/plans/2026-10-10-v158-instrument-v2-window-contract_3-tuner-scripts-guard.md`.

**Spec:** [`docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md`](../specs/2026-10-06-v136-backtest-instrument-v2-design.md) (cross-cutting rules 1 and 2; section 1 "Folds" and "Universe"; "Testing": date-literal guard)
**Index:** [`2026-10-10-v158-instrument-v2-window-contract_0-index.md`](2026-10-10-v158-instrument-v2-window-contract_0-index.md): header block, `## Where to work`, `## Global Constraints`, `## Parallelisation` and the task ledger. Every task below implicitly includes that index's Global Constraints; the ledger's names, signatures and paths are the contract with parts 1 and 2.

**Tasks in this part:** WC9, WC10, WC11, WC12. WC9 needs WC4 (folds), WC5 (universe gate), WC6 (CLI helper) and WC7 (aliases); WC10 needs WC6 and WC7. WC9 and WC10 may run in parallel with each other and with WC8 (disjoint files), at most 2 implementers at once. WC11 needs WC7–WC10 (it asserts the end state of every script). WC12 is the plan's single full-suite run and its final task.

Conventions used in every task (from the index's `## Where to work`):

- `$R` = `/home/user/Discord-Bot` (main tree, never edited by a task). `$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v158-instrument-v2-window-contract` (branch `2026-10-10-v158-instrument-v2-window-contract`).
- Never `cd`. Use `git -C $WT ...` and `python $WT/scripts/dev/testrun.py file tests/...` (test paths resolve against `$WT`).
- After every commit: `git -C $R status --short` must print nothing new (the main tree is unchanged).
- Every new or changed function stays < complexity 15: `python -m radon cc -s -n C <files>`. Legacy functions never get worse (measured on `main` at `085f7ce6`: `tune_strategy.main` D 29, `tune_strategy.run_config` C 17, `tune_exit_v2.main` C 15, `tune_confluence_gates.main` C 16, `wf_run.main` C 19, `measure_arms.main` C 14).
- Names used here from earlier parts (verify with `git -C $WT grep -n` before starting a task):
  - WC1: `InstrumentSpec.universe`, `.research_span`, `.purge`, `.embargo_days`, `.liquidity_floor`, `.fold_test_years`; `contract.resolve`, `contract.VERSIONS`.
  - WC4 (`instrument/folds.py`): `anchored_folds(spec) -> tuple[Fold, ...]`; `out_of_fold(trades_by_config, folds, select, *, embargo_days, purge=True) -> OutOfFold(choices, trades)`; `select` receives `{config: train trades}` and returns a config key.
  - WC5 (`instrument/universe_gate.py`): `eligible_trades(trades, spans, df, floor) -> list`; `watchlist_slice_verdict(n, expectancy_r) -> SliceVerdict(status, n, expectancy_r)`; `WATCHLIST_SLICE_MIN_N`.
  - WC6 (`instrument/cli.py`): `add_instrument_arg(parser)`; `spec_from_args(args)`; `window_for(spec, stage)`; `require_v1(spec, script, owner)` (SystemExit naming `script`, `--instrument v2` and `owner`).
  - WC7: `tune_strategy.TRAIN`, `tune_exit_v2.TRAIN`, `tune_confluence_gates.TRAIN` are `resolve_instrument("v1").train_window`, imported as `from swingbot.core.backtesting.instrument.contract import resolve as resolve_instrument`.
  - Pre-existing `run_backtest_range` helpers WC9 calls (signatures unchanged by WC8): `window_trades(summary, date_from, date_to)`, `_tickers_for_run(universe)`, `_membership_for_run(universe, tickers)`, `_spans_for(membership, ticker)`, `_exclusion_reason(df, ticker, pit)`.

# Phase C (continued): tuner folds, the flag on every live script, the guard

