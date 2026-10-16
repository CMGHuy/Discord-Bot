# v161 Trade scout: generator roles over a live-book autopsy. Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `/task-brief TS5` or `grep -n "^### Task TS5" -A 300 docs/superpowers/plans/2026-10-15-v161-trade-scout_*.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v161-trade-scout-design.md`](../specs/2026-10-15-v161-trade-scout-design.md) (all sections; the "Data availability" block overrides the column list; every applied `## Panel review` finding is a requirement)
**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)

**Goal:** A read-only VM export plus a local, deterministic autopsy of the live book (`scripts/reports/book_autopsy.py`), three generator role skills (`exit-harvester`, `setup-scout`, `regime-desk`) run through a read-only `scout` agent by a `/trade-scout` skill, and a deterministic merge (`scripts/dev/scout_merge.py`) that drops closed, duplicate and unsupported rows and writes a ranked slate of hypotheses for `/screen` or `/prereg`.

**Architecture:** The VM runs exactly two read-only commands from `scripts/ops/export_book_rows.sh` (a `READ ONLY` psql `\copy` and a host log grep); everything else is local. The autopsy is a thin CLI over a small package `scripts/reports/autopsy/` (rows → cells → cuts → report), so each file has one job and the statistical core is tested alone. The merge is one script in `scripts/dev/`. Skills and the agent are text, shape-tested in `tests/scout/` and `tests/hooks/`, and mirrored to Codex with `sync_codex.py` in the same commit.

**Tech Stack:** Python 3.11, pandas/numpy, pytest (via `scripts/dev/testrun.py`), radon, bash + psql (VM side only). Statistics reuse `swingbot/core/backtesting/instrument/stats.py` (`week_cluster_bootstrap`, `bh_qvalues`, `iso_week_key`) and `swingbot/core/analytics/gate_counterfactual_report.py:42 two_sided_bootstrap_p`.

## Progress

TS1–TS12 implemented on `2026-10-15-v161-trade-scout`; TS13 first live run is in progress on 2026-10-16. TS14 is pending.

## Handoff

- TS13: the partner approved the read-only export, including a retry after the local command sandbox denied WSL startup. The retry used the same `scripts/ops/ssh-hetzner.sh` path and completed; the aggregated autopsy was committed on `main` as `1653056f`. Raw CSVs remain in scratch until TS13 finishes.
- TS13 correction: `fetch_backtest_data.py` rejects frames shorter than 260 daily bars. Starting at the first plan date (2026-07-24) produced zero cached tickers; starting at 2025-01-01 in scratch produced 72 of 75. The TS13 instruction now leads the first plan date by 550 calendar days. Three unavailable symbols count as uncovered rather than being patched by hand.
- TS13 correction: `cells_tested` counts cells with a p-value, not every listed cell. This run has one thin cell without a p-value; the validation instruction now checks the tested subset.

## Where to work

- **Branch and worktree:** `2026-10-15-v161-trade-scout`, at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout` (written `$WT` below). The main tree is `$R` = `E:/Documents/Private/Projects/Discord-Bot`. TS1 Step 0 creates the worktree with the `worktree-lifecycle` skill; name `$WT` in every subagent dispatch.
- **Never `cd`** (it breaks the guardrail hooks). Use absolute paths and `git -C $WT`. `python $WT/scripts/dev/testrun.py file tests/scout/test_x.py` resolves test paths against `$WT`.
- **This plan file is committed on `main`.** Only the implementation is branched. Each task commits on the branch. After every task, `git -C $R status --short` must show the main tree unchanged.
- **Scratch:** raw production rows and fetched bars live in the session scratchpad (written `$SCRATCH`), never in the repo.
- **TS13 runs in the main session, not in a subagent:** it asks the partner (`AskUserQuestion`) before the one production command and dispatches the `scout` agents.

## Global Constraints

- **Bump: none.** No task edits `VERSION.json` or `version_history.json`; nothing under `swingbot/` changes (imports from it are fine). Repo tooling only: `.claude/`, `scripts/`, `tests/`, `docs/`, `AGENTS.md`, generated `.agents/` and `.codex/`.
- **Free only.** No `claude plugin eval`, no API keys, no billed or cloud runs anywhere in this plan. Skills get no `evals/` directories (the generator roles are not in `test_role_skills.py`'s `ROLES`). The `scout` dispatches in TS13 run as subagents on the subscription.
- **Production is read-only and partner-gated.** The only production footprint is `scripts/ops/export_book_rows.sh` run through `bash scripts/ops/ssh-hetzner.sh` (never raw `ssh`/`scp`). TS13 asks the partner before running it, preferably outside the US session and premarket. The export opens its psql session with `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`; the script contains no `INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP|CREATE` (word-bounded, case-sensitive). psql runs as `docker compose exec -T db psql -U swingbot -d swingbot` (the host has no psql). Logs are grepped on the **host** at `/opt/swing-bot/logs/` (the container path `/app/logs` is wrong there).
- **Raw export CSVs are scratch only, never committed.** Committed run artefacts: `docs/superpowers/results/<date>-book-autopsy.{json,md}` and `docs/superpowers/results/<date>-scout-slate.md`.
- **Hard boundaries, verbatim from the spec:** "No gate moves. A slate row is a hypothesis. It never edits code, config, thresholds or live alerts, and never licenses a re-run of a closed pre-registration." "Every entry or filter idea still needs a `SCREEN-PASS` row before its spec." "Numbers come from one autopsy run." "Every autopsy-derived row is exploratory, and the holdout is protected." The slate repeats boundary 5 (constant `HOLDOUT_REMINDER`, ledger TS9).
- **Data availability (spec block, binding):** net R is **modelled** locally (`apply_frictions`, `commission_r`, `swingbot/core/edge/frictions.py:15,22`; header flag `net_of_frictions: "modelled"`); fill rate comes from `plans` rows (unfilled plans have no journal row); "never touched" vs "expired unfilled" is derived from bars over the plan's validity; sector is today's `universe.sector_map` and labelled not-PIT (never a regime-desk argument); FOMC from `market_events.FOMC_DECISION_DATES`, OPEX from `opex.opex_tier`; **CPI and NFP cuts are omitted** (`market_events.py` only computes forward approximations, it carries no past dates) and the header says so; near-TP exits are `close_reason` `auto (near-TP stall)` / `auto (near-TP timeout)`.
- **Bars (known-traps § two OHLCV caches):** the autopsy reads bars only from `--bars-dir`, files named like `backtest_cache.cache_path` (`<TICKER with = ^ / → _>.csv`, columns `Date,Open,High,Low,Close,Volume`). TS13 fills a **scratch** directory with `BACKTEST_CACHE_DIR=$SCRATCH/autopsy_bars python scripts/data/fetch_backtest_data.py --tickers ... --start ... --end today` (free yfinance). **Never** `--force` into `data/backtest_cache/` (frozen backtest inputs; it ends 2025-12-30 and does not cover the live book anyway). The autopsy itself does no network I/O. Bars are split/dividend-adjusted: a row whose plan-day close differs from its planned entry by more than `SPLIT_GUARD = 0.25` (fraction) counts as not bar-covered. Every bar cut prints bar-covered N beside total N.
- **No lookahead:** `risk_features` fields are frozen at issuance (PIT). Dollar volume is the 20-bar mean of `Close*Volume` ending at the plan day. The near-stop reversal and wider-stop checks read **only bars strictly after the exit date**. Sector is today's mapping (labelled).
- **Statistics (spec § 1, binding):** every R cell prints N, distinct ISO weeks, win rate, net ExpR, gross ExpR, `Δ = mean net R(cell) − mean net R(complement)` with a 95% percentile interval from `week_cluster_bootstrap(complement, cell, statistic)` (baseline = complement, component = cell, same week draw; never a cell against a pool containing it), a two-sided bootstrap p (`two_sided_bootstrap_p`) and a BH q-value over **every** cell tested (`bh_qvalues`). `thin` = N < 30 **or** fewer than 8 distinct weeks; thin cells are still tested and counted, never ranked as evidence. Default resamples `WEEK_BOOTSTRAP_RESAMPLES` (10 000), seed 42; tests pass 200. The bootstrap feeds per-week sums (objects with an `.entry_date` attribute: `group_by_week` reads the attribute, dicts do not work), never per-trade lists, so a full run finishes in minutes.
- **Win** = gross R > 0. **Complement** of a cell = the trades of the same cut whose key is not `None` and differs from the cell's value (rows a cut cannot place are excluded from both arms and counted as uncovered).
- **Skill text (tests/hooks/test_skill_shape.py):** every new `SKILL.md` ≤ 80 lines; no bare comparator before a number (`>=|<=|>|<|=` then a digit) and no `<number> R` / `<number> pp` anywhere in the body (thresholds live in `docs/claude/skills-tools.md` § Generator roles (v161) or in the scripts); `description:` a double-quoted scalar, ≥ 40 characters, kept short (listed every session); model-invocable skills carry `## Trigger table` with ≥ 3 `Should fire:` and ≥ 3 `Should not fire:` lines and no `disable-model-invocation`. All four new skills join `TIER_1_AND_3`.
- **Codex mirror in the same commit:** any `.claude/skills|agents` change runs `python $WT/scripts/dev/sync_codex.py` and commits `.agents/skills/<n>/SKILL.md` / `.codex/agents/scout.toml` with it; `sync_codex` copies only `SKILL.md`, so `setup-scout` cites its playbook by repo path `.claude/skills/setup-scout/references/playbook.md`. `AGENTS.md` gets exactly one table row naming `` `trade-scout` ``, `` `exit-harvester` ``, `` `setup-scout` ``, `` `regime-desk` `` and `` `scout` `` and must stay under 32 768 bytes (31 837 at HEAD 35a36cdb; a test pins it).
- **Tests:** new directory `tests/scout/` (with `__init__.py`) joins a **new suite `scout`** in `tests/suites.toml` in TS1's commit (the `tooling` suite already counts about 1 139 test functions against `max_tests = 1200`, so it cannot absorb ~90 more). Per-task runs are `python $WT/scripts/dev/testrun.py file <test>`; the only full-suite run is TS14. Tests build fixtures in `tmp_path`; no fixture data files under `tests/scout/`.
- **Complexity:** every new function < 15 (`python -m radon cc -s -n C <files>` prints nothing). No legacy function is touched.
- **Do not re-run or cite closed pre-registrations as licences.** The merge's closed-table parser stops at the first non-table line after `### Closed pre-registrations — do not re-run these` (the table runs to EOF today).
- **Green means `0 failed` and `0 xfailed`.**

## Parallelisation

| Task | Files (disjoint?) | Depends on | Why sequential |
|---|---|---|---|
| TS1 export script, `tests/scout/`, suite | `scripts/ops/export_book_rows.sh`, `tests/scout/__init__.py`, `tests/scout/test_export_script.py`, `tests/suites.toml` | — | Creates the worktree, the test directory and its suite every later task writes into |
| TS2 rows loader, modelled net R | `scripts/reports/autopsy/{__init__,rows}.py`, `tests/scout/test_autopsy_rows.py` | TS1 | Its test cross-checks `EXPORT_COLUMNS` against TS1's script aliases |
| TS3 cell statistics | `scripts/reports/autopsy/cells.py`, `tests/scout/test_autopsy_cells.py` | TS2 | Consumes `BookRow` |
| TS4 categorical cuts | `scripts/reports/autopsy/cuts.py`, `tests/scout/test_autopsy_cuts.py` | TS3 | Consumes `cut_cells`. Can run **in parallel with TS5 and TS6** (disjoint files, contracts fixed in the ledger) |
| TS5 bar-reading cuts | `scripts/reports/autopsy/bars.py`, `tests/scout/test_autopsy_bars.py` | TS3 | Can run **in parallel with TS4 and TS6** |
| TS6 exit and alert-supply cuts | `scripts/reports/autopsy/exits.py`, `tests/scout/test_autopsy_exits.py` | TS3 | Can run **in parallel with TS4 and TS5** |
| TS7 report, CLI, quant-engineer review | `scripts/reports/autopsy/report.py`, `scripts/reports/book_autopsy.py`, `tests/scout/test_book_autopsy.py` | TS4, TS5, TS6 | Assembles every cut |
| TS8 merge parsing and closed-name matching | `scripts/dev/scout_merge.py`, `tests/scout/test_scout_merge_parse.py` | TS1 | Needs only `tests/scout/`. Can run **in parallel with TS2–TS7** (disjoint files; the autopsy JSON shape is fixed in the ledger) |
| TS9 merge drops, ranking, slate, CLI | `scripts/dev/scout_merge.py`, `tests/scout/test_scout_merge.py` | TS8 | Same file as TS8. Can run **in parallel with TS2–TS7** |
| TS10 generator role skills and playbook | `.claude/skills/{exit-harvester,setup-scout,regime-desk}/SKILL.md`, `.claude/skills/setup-scout/references/playbook.md`, `.agents/skills/{exit-harvester,setup-scout,regime-desk}/SKILL.md`, `tests/hooks/test_skill_shape.py`, `tests/scout/test_generator_roles.py`, `AGENTS.md` | TS1 | Needs `tests/scout/`. Can run **in parallel with TS2–TS9** (disjoint files; cites the cell-id and Row format contracts below) |
| TS11 `scout` agent, `trade-scout` skill, docs | `.claude/agents/scout.md`, `.claude/skills/trade-scout/SKILL.md`, `.agents/skills/trade-scout/SKILL.md`, `.codex/agents/scout.toml`, `tests/hooks/test_skill_shape.py`, `tests/hooks/test_agent_shape.py`, `tests/scout/test_trade_scout_skill.py`, `docs/claude/skills-tools.md` | TS10 | Same `test_skill_shape.py` and generated mirror as TS10; the docs section names TS10's roles |
| TS12 `DATA_READERS` rows | `scripts/dev/select_tests.py`, `tests/scout/test_scout_routing.py` | TS7, TS9, TS11 | Rows point at test files that must exist (a missing target widens) |
| TS13 first live run (partner-gated) | `docs/superpowers/results/<date>-book-autopsy.{json,md}`, `docs/superpowers/results/<date>-scout-slate.md` | TS12 | Uses every tool; production command needs the partner's go |
| TS14 full suite | — | TS1–TS13 | Final gate |

Recommended order: TS1, then {TS2→TS3, TS8→TS9, TS10→TS11} with at most 2 implementers at once, then {TS4, TS5, TS6} two at a time, then TS7, TS12, TS13, TS14. Dispatch the `quant-engineer` review (TS7 last step) only after TS4–TS6 are merged into the branch.

## Shared contracts (binding for every part)

**Export columns** (`rows` mode CSV header and `autopsy.rows.EXPORT_COLUMNS`, this exact order):
`row_kind, trade_id, plan_id, ticker, strategy, horizon, direction, plan_created_at, plan_first_status_at, plan_status, plan_status_reason, entry_type, expiry_bars, valid_session, planned_entry, opened_at, entry, stop_loss, take_profit, target2, closed_at, exit_price, close_reason, last_leg_reason, outcome, r_realized, mfe_r, mae_r, exit_efficiency, holding_days, stop_width_atr, atr_pct, regime2_state, session_bucket, days_to_earnings, rs_percentile`.
`row_kind` is `trade` (journal ⋈ trades ⟕ plans, one row per closed trade) or `plan` (plans with no trade, trade columns NULL). Rejections mode CSV header: `date,reason,count`.

**Cell id:** `<cut>=<value>`, `cut` snake_case from the cut names below, `value` the cell's key text (may contain `|`, never `;`). Tally ids use the same form.

**Cut names:** categorical (TS4) `strategy_horizon`, `direction`, `ticker`, `sector_today`, `regime`, `weekday`, `friday_entry`, `weekend_hold`, `earnings_proximity`, `opex_week`, `fomc_proximity`, `atr_pct_bucket`, `session_bucket`, `alert_hour`; bars (TS5) `open_gap_bucket`, `gapped_through_entry`, `dollar_volume_bucket`, `near_stop_reversal`; exits (TS6) `exit_reason`, `near_tp_close`, `gap_through_stop`, `holding_bucket`. Tallies: `fill_status` (TS5), `alerts_per_day`, `alert_hour_session`, `actionable_before_open`, `rejection_reason` (TS6).

**Autopsy JSON** (written by TS7, read by TS9):
```json
{"header": {"window": ["YYYY-MM-DD", "YYYY-MM-DD"], "n": 0, "pooled_net_expr": 0.0,
            "pooled_win_rate": 0.0, "net_of_frictions": "modelled", "cells_tested": 0,
            "bar_covered_n": 0, "resamples": 10000, "seed": 42, "notes": ["..."]},
 "cells": [{"id": "cut=value", "cut": "cut", "value": "value", "n": 0, "weeks": 0,
            "win_rate": 0.0, "net_expr": 0.0, "gross_expr": 0.0, "delta": 0.0,
            "ci": [0.0, 0.0], "p": 0.0, "q": 0.0, "thin": true,
            "bar_covered_n": null, "extra": {}}],
 "tallies": [{"id": "cut=value", "cut": "cut", "value": "value", "count": 0, "extra": {}}],
 "giveback": {"n": 0, "mean": 0.0, "median": 0.0}}
```
`delta`, `ci`, `p`, `q` are `null` when the bootstrap returned no draws. `window` is the first and last exit date of the closed trades.

**Row format** (role output → merge input; one block per row, keys in this order, two-space indent):
```
- idea: <kebab-case name, unique>
  claim: <one sentence>
  evidence: cell <cell id>; N <n>; weeks <w>; Δ net ExpR <d> [<lo>, <hi>]; q <q>   |   playbook <entry id>
  exploratory: yes
  edge: expectancy | harvest | volume
  mechanism: <one or two sentences>
  order_form: <stop-buy / limit / market-on-open, validity>
  manual_actions: none | <action>
  pairs_with: <where volume or R comes back> | n/a
  divergence: no | yes
  route: /screen <idea> | /prereg | harvest-headroom <results path>
```
The role-output file the controller writes groups blocks under `## role: <name>` lines.

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Creates, consumed later |
|---|---|---|---|---|---|
| TS1 | Read-only VM export script, `tests/scout/`, suite `scout` | 1 | sonnet | C `scripts/ops/export_book_rows.sh`, C `tests/scout/__init__.py`, C `tests/scout/test_export_script.py`, M `tests/suites.toml` | Script run as `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rows" < scripts/ops/export_book_rows.sh > $SCRATCH/rows.csv` and `... -- rejections" ... > $SCRATCH/rejections.csv`; header order = Export columns above; `[suites.scout] paths = ["tests/scout/"]` |
| TS2 | Rows loader and modelled net R | 1 | sonnet | C `scripts/reports/autopsy/__init__.py`, C `scripts/reports/autopsy/rows.py`, C `tests/scout/test_autopsy_rows.py` | `EXPORT_COLUMNS: tuple[str, ...]`; `@dataclass BookRow` with fields `row_kind, trade_id, plan_id, ticker, strategy, horizon, direction, plan_date: str \| None, plan_hour: int \| None, plan_status, plan_status_reason, entry_type, expiry_bars: int \| None, valid_session, planned_entry: float \| None, entry_date: str \| None, entry: float \| None, stop: float \| None, take_profit: float \| None, target2: float \| None, exit_date: str \| None, exit_price: float \| None, close_reason: str, outcome, gross_r: float \| None, net_r: float \| None, mfe_r, mae_r, exit_efficiency, holding_days: float \| None, stop_width_atr, atr_pct, days_to_earnings, rs_percentile: float \| None, regime2_state, session_bucket: str \| None, bars: dict = field(default_factory=dict)` (all text fields `str \| None` unless noted; `entry_date` is the ISO fill date, the attribute `group_by_week` reads); `load_rows(path: Path) -> list[BookRow]`; `closed_trades(rows) -> list[BookRow]` (row_kind trade with `gross_r` not None); `plan_rows(rows) -> list[BookRow]`; `modelled_net_r(row: BookRow) -> float \| None`; `@dataclass(frozen=True) RejectionCount(date: str, reason: str, count: int)`; `load_rejections(path: Path) -> list[RejectionCount]` |
| TS3 | Cell statistics: Δ vs complement, week bootstrap, BH | 1 | opus | C `scripts/reports/autopsy/cells.py`, C `tests/scout/test_autopsy_cells.py` | `THIN_MIN_N = 30`; `THIN_MIN_WEEKS = 8`; `@dataclass CellStats(id: str, cut: str, value: str, n: int, weeks: int, win_rate: float, net_expr: float, gross_expr: float, delta: float \| None, ci: tuple[float, float] \| None, p: float \| None, q: float \| None, thin: bool, bar_covered_n: int \| None = None, extra: dict = field(default_factory=dict))` with `to_json() -> dict`; `@dataclass Tally(id: str, cut: str, value: str, count: int, extra: dict = field(default_factory=dict))` with `to_json() -> dict`; `is_thin(n: int, weeks: int) -> bool`; `cell_stats(cut: str, value: str, members: list, complement: list, *, n_resamples: int, seed: int) -> CellStats` (extra always carries `tickers: int`, `top_ticker_share: float`); `cut_cells(cut: str, trades: list, key: Callable[[BookRow], str \| None], *, n_resamples: int, seed: int) -> list[CellStats]` (one cell per distinct non-None key; uncovered count in each cell's `extra["uncovered"]`); `apply_bh(cells: list[CellStats]) -> int` (sets `q`, returns cells tested) |
| TS4 | Categorical cuts: strategy, regime, calendar, events, volatility, timing | 1b | sonnet | C `scripts/reports/autopsy/cuts.py`, C `tests/scout/test_autopsy_cuts.py` | `categorical_cuts(sector_of: Mapping[str, str]) -> tuple[tuple[str, Callable[[BookRow], str \| None]], ...]` (names: the 14 categorical cut names, in that order); `load_sector_map() -> dict[str, str]` (today's `universe.sector_map`, `{}` when unavailable); `CUT_NOTES: dict[str, str]` (`sector_today` → "today's sector map, not point-in-time"; `fomc_proximity` → coverage note; `macro` → "CPI and NFP omitted: market_events.py carries no past dates") |
| TS5 | Bar-reading cuts: fill reality, gaps, liquidity, reversals | 2 | opus | C `scripts/reports/autopsy/bars.py`, C `tests/scout/test_autopsy_bars.py` | `SPLIT_GUARD = 0.25`; `REVERSAL_BARS = 10`; `WIDER_STOP_ATR = 0.5`; `load_bars(bars_dir: Path \| None, ticker: str) -> pd.DataFrame \| None`; `enrich_with_bars(rows: list[BookRow], bars_dir: Path \| None) -> int` (fills each row's `bars` dict with keys `covered`, `fill_day_open`, `open_gap_pct`, `gapped_through`, `dollar_volume`, `fill_status`, `reversal`, `wider_stop_lost`; returns bar-covered N); `bar_cuts() -> tuple[tuple[str, Callable[[BookRow], str \| None]], ...]` (the 4 bar cut names); `fill_tallies(rows: list[BookRow]) -> list[Tally]` (`fill_status=` filled / expired_unfilled / never_touched / risk_cap / invalidated / open / unknown) |
| TS6 | Exit and alert-supply cuts, give-back, stop extras | 2 | sonnet | C `scripts/reports/autopsy/exits.py`, C `tests/scout/test_autopsy_exits.py` | `exit_cuts() -> tuple[tuple[str, Callable[[BookRow], str \| None]], ...]` (the 4 exit cut names); `STOP_CUTS = frozenset({"exit_reason", "gap_through_stop", "near_stop_reversal"})`; `stop_extra(members: list[BookRow], balance: float) -> dict` (`mean_stop_atr`, `dollar_loss_at_2pct`); `giveback_summary(trades: list[BookRow]) -> dict` (`n`, `mean`, `median` of `mfe_r − gross_r` over every trade with `mfe_r`); `alert_supply_tallies(rows: list[BookRow], rejections: list[RejectionCount]) -> list[Tally]` |
| TS7 | Report assembly, Markdown, CLI, quant-engineer review | 2b | sonnet | C `scripts/reports/autopsy/report.py`, C `scripts/reports/book_autopsy.py`, C `tests/scout/test_book_autopsy.py` | `MD_MAX_LINES = 150`; `build_report(rows: list[BookRow], rejections: list[RejectionCount], *, bars_dir: Path \| None, n_resamples: int, seed: int, balance: float) -> dict` (the Autopsy JSON shape); `render_markdown(report: dict) -> str`; CLI `python scripts/reports/book_autopsy.py <rows.csv> <rejections.csv> [--bars-dir DIR] [--out-dir docs/superpowers/results] [--date YYYY-MM-DD] [--resamples N] [--seed N] [--balance USD]` writing `<out-dir>/<date>-book-autopsy.json` and `.md`; `main(argv: list[str] \| None = None) -> int` |
| TS8 | Merge: role-output parsing and closed-name matching | 2b | sonnet | C `scripts/dev/scout_merge.py`, C `tests/scout/test_scout_merge_parse.py` | `CLOSED_HEADING = "### Closed pre-registrations — do not re-run these"`; `ROW_FIELDS: tuple[str, ...]` (the 11 Row format keys); `@dataclass ScoutRow(role: str, idea: str, claim: str, evidence: str, exploratory: str, edge: str, mechanism: str, order_form: str, manual_actions: str, pairs_with: str, divergence: str, route: str)` with properties `cell_id -> str \| None`, `playbook_id -> str \| None`, `quoted_n -> int \| None`; `@dataclass(frozen=True) Drop(idea: str, role: str, reason: str)`; `normalise(name: str) -> str`; `parse_rows(text: str) -> tuple[list[ScoutRow], list[Drop]]`; `closed_names(methodology: Path) -> set[str]`; `ledger_names(ledger: Path) -> dict[str, str]` (normalised name → ledger id); `closed_match(idea: str, names: Iterable[str]) -> str \| None` |
| TS9 | Merge: drops, pinning, ranking, slate, CLI | 3 | sonnet | M `scripts/dev/scout_merge.py`, C `tests/scout/test_scout_merge.py` | `EDGE_ORDER = ("expectancy", "harvest", "volume")`; `HOLDOUT_REMINDER: str` (boundary 5); `screen_rows(rows: list[ScoutRow], *, closed: set[str], ledger: dict[str, str], cells: dict[str, dict]) -> tuple[list[ScoutRow], list[Drop]]`; `rank(rows: list[ScoutRow], cells: dict[str, dict]) -> list[ScoutRow]`; `render_slate(ranked: list[ScoutRow], drops: list[Drop], header: dict, *, date: str, autopsy_path: str) -> str`; CLI `python scripts/dev/scout_merge.py <role-output.md> --autopsy <json> [--ledger PATH] [--methodology PATH] [--out-dir docs/superpowers/results] [--date YYYY-MM-DD]` writing `<out-dir>/<date>-scout-slate.md`; `main(argv: list[str] \| None = None) -> int` |
| TS10 | Generator role skills, playbook, shape test, AGENTS.md row | 3 | sonnet | C `.claude/skills/exit-harvester/SKILL.md`, C `.claude/skills/setup-scout/SKILL.md`, C `.claude/skills/setup-scout/references/playbook.md`, C `.claude/skills/regime-desk/SKILL.md`, C `.agents/skills/{exit-harvester,setup-scout,regime-desk}/SKILL.md` (generated), M `tests/hooks/test_skill_shape.py`, C `tests/scout/test_generator_roles.py`, M `AGENTS.md` | Skill names `exit-harvester`, `setup-scout`, `regime-desk`, first heading `## Generator lens`, sections `## Generator lens`, `## Checklist`, `## Red flags`, `## Out of scope`, `## Row format`, `## Trigger table` in that order; playbook entry ids `gap-and-hold`, `gap-fill-reversal`, `tight-base-breakout`, `rs-leader-index-pullback`, `failed-breakdown-reclaim`, `atr-reentry-after-stop`, `three-bar-weekly-reversal` |
| TS11 | `scout` agent, `trade-scout` skill, skills-tools.md | 3b | sonnet | C `.claude/agents/scout.md`, C `.claude/skills/trade-scout/SKILL.md`, C `.agents/skills/trade-scout/SKILL.md` and `.codex/agents/scout.toml` (generated), M `tests/hooks/test_skill_shape.py`, M `tests/hooks/test_agent_shape.py`, C `tests/scout/test_trade_scout_skill.py`, M `docs/claude/skills-tools.md` | Agent `scout` (tools `Read, Grep, Glob, Skill`, `model: sonnet`, returns rows, `NO ROWS: <why>`, `UNKNOWN ROLE: <...>` or `BLOCKED: <one question>`); skill `trade-scout`; docs heading `## Generator roles (v161)` carrying the q cut-off (`q ≤ 0.10`) and the thin rule |
| TS12 | `DATA_READERS` rows for the scout tests | 3b | haiku | M `scripts/dev/select_tests.py`, C `tests/scout/test_scout_routing.py` | — |
| TS13 | First live run: export (partner-gated), autopsy, scouts, merge, panel | 3b | opus | C `docs/superpowers/results/<date>-book-autopsy.json`, C `docs/superpowers/results/<date>-book-autopsy.md`, C `docs/superpowers/results/<date>-scout-slate.md` | — |
| TS14 | Full suite | 3b | haiku | — | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-15-v161-trade-scout_1-export-autopsy-core.md` | TS1–TS3 | Phase A: VM export, test directory and suite. Phase B: rows, cell statistics |
| 1b | `2026-10-15-v161-trade-scout_1b-categorical-cuts.md` | TS4 | Phase B: categorical cuts (split from part 1 to stay under 1500 lines) |
| 2 | `2026-10-15-v161-trade-scout_2-bars-exits-report-merge.md` | TS5–TS6 | Phase B: bar cuts, exit and supply cuts |
| 2b | `2026-10-15-v161-trade-scout_2b-report-merge-parse.md` | TS7–TS8 | Phase B: report and CLI with the quant-engineer review. Phase C: merge parsing (split from part 2 to stay under 1500 lines) |
| 3 | `2026-10-15-v161-trade-scout_3-slate-roles-run.md` | TS9–TS10 | Phase C: merge ranking and slate. Phase D: generator role skills and playbook |
| 3b | `2026-10-15-v161-trade-scout_3b-agent-routing-run.md` | TS11–TS14 | Phase D: `scout` agent, `trade-scout` skill, docs, routing (split from part 3 to stay under 1500 lines). Phase E: first live run and full suite |
