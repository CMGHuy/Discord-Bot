# v140 Idea screen: Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V140-3` or `grep -n "^### Task V140-3:" -A 260 docs/superpowers/plans/2026-10-08-v140-idea-screen_*.md`.

**Bump:** none
**Edge:** expectancy
**Spec:** [`docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`](../../specs/implemented/2026-10-08-v140-idea-screen-design.md)

**Goal:** Build a research-only screen that answers "does this entry predict anything, after costs, beyond its own trend state?" on the point-in-time S&P 500 members of 2010-2019 that are cached (506 of 719 at writing; the results doc discloses the live counts), make it a hard gate for new entry specs (`**Screen:**` header, enforced by a test), and screen the first batch of four published daily-bar effects once each.

**Architecture:** A new package `swingbot/core/backtesting/screen/` (no live path imports it, pinned by a test): causal `indicators`, a frozen `ideas` registry with four triggers, `race` (the fixed 1.5/3 ATR trade, vectorised per ticker, with the one-open-race book), `null` (K = 20 matched random bars per event), `forward` (reported-only drift and rank correlation) and `verdict` (paired ΔExpR, week-cluster bootstrap from `instrument/stats`, the four-clause pass rule). `scripts/backtest/screen_idea.py` runs one idea end to end, writes the results doc and appends the ledger row, refusing any idea already ledgered. The ledger vocabulary gains three `SCREEN-*` verdicts and the `screen-v1` instrument.

**Tech Stack:** Python 3.11, pandas, numpy (no scipy: it is not in `requirements.txt`), pytest. Existing, verified with `git grep -n`: `swingbot/core/backtesting/instrument/stats.py` (`week_cluster_bootstrap`, `group_by_week`, `WEEK_BOOTSTRAP_RESAMPLES`, `WEEK_BOOTSTRAP_SEED`, `VERDICTS`, `INSTRUMENTS`, `LEDGER_PATH`, `validate_ledger_row`, `append_ledger_row`, `load_ledger`, `ledger_qvalues`), `swingbot/core/edge/frictions.py` (`apply_frictions`, `commission_r`), `swingbot/core/marketdata/pit_membership.py` (`load_intervals`, `is_member`, `members_between`), `swingbot/config.py` (`DATA_DIR`, `SLIPPAGE_BPS`, `COMMISSION_PER_TRADE`, `COMMISSION_RISK_BASIS`), `scripts/reports/preregistration_ledger.py`, `scripts/dev/sync_codex.py`, `scripts/dev/testrun.py`, `scripts/reports/runner_headroom.py`, `swingbot/core/analytics/exit_quality.py`. Data: `data/backtest_cache_ext/<SYM>.csv` (Date,Open,High,Low,Close,Volume; gitignored, main tree only) and `data/universe/sp500_membership.csv` (tracked).

## Where to work

- **Branch and worktree:** `2026-10-08-v140-idea-screen` at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen`. V140-1 Step 0 creates it with the `worktree-lifecycle` skill. Every implementation task and every screen run happens there. Name the worktree in every subagent dispatch, and after each task run `git -C E:/Documents/Private/Projects/Discord-Bot status --short` to confirm the main tree is unchanged.
- **Data:** `data/backtest_cache_ext/` is gitignored, so the worktree has none. The runs pass `--cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext`. The membership CSV is tracked, so the worktree's own copy is used. Never fetch into any cache from this plan.
- **Ledger:** `stats.LEDGER_PATH` resolves relative to the module file, so a run inside the worktree appends to the worktree's `docs/superpowers/results/preregistration-ledger.jsonl`. That is intended: the row lands on `main` with the merge.
- **Skills:** `no-lookahead` before V140-1, V140-3, V140-4, V140-6..9 and V140-13 (they decide what a bar knew). `backtest-gate` before each of V140-15..18. `worktree-lifecycle` before creating, merging and removing the worktree.

## Parts

| Part | File | Tasks |
|---|---|---|
| 0 | this index | header, constraints, review focus, frozen readings, parallelisation |
| 1 | `2026-10-08-v140-idea-screen_1-foundation.md` | Phase 1: V140-1 (package, indicators, import guard), V140-2 (idea registry), V140-3 (race and book) |
| 2 | `2026-10-08-v140-idea-screen_2-null-forward-ideas.md` | Phase 2, Group A: V140-4 (null), V140-5 (forward), V140-6..9 (four triggers) |
| 3 | `2026-10-08-v140-idea-screen_3-ledger-header-verdict.md` | Phase 3, Group B: V140-10 (ledger vocabulary), V140-11 (header test and docs); Phase 4: V140-12 (verdict) |
| 4 | `2026-10-08-v140-idea-screen_4-screen-script.md` | Phase 4: V140-13 (universe and per-ticker pipeline), V140-14 (CLI, results doc, ledger, refusals) |
| 5 | `2026-10-08-v140-idea-screen_5-runs-and-closeout.md` | Phase 5: V140-15..18 (the four screens, one at a time), V140-19 (results close-out), V140-20 (full suite) |

## File map

| File | Created / modified by | Responsibility |
|---|---|---|
| `swingbot/core/backtesting/screen/__init__.py` | V140-1 | package docstring only |
| `swingbot/core/backtesting/screen/indicators.py` | V140-1 | `wilder_mean`, `true_range`, `atr`, `rsi`, `sma`, `rolling_max` |
| `swingbot/core/backtesting/screen/ideas/__init__.py` | V140-2 | `Idea`, `IDEA_MODULES`, `IDEAS` |
| `swingbot/core/backtesting/screen/ideas/{high52w,uptrend_pullback,gap_volume,turn_of_month}.py` | V140-2 (constants + stub), V140-6..9 (trigger) | `CAP`, `PARAMS`, `SUMMARY`, `SOURCE`, `events(df)` |
| `swingbot/core/backtesting/screen/race.py` | V140-3 | `RaceResult`, `race`, `warm_mask`, `candidate_events`, `non_overlapping`, `run_book` |
| `swingbot/core/backtesting/screen/null.py` | V140-4 | `K`, `MIN_CANDIDATES`, `null_seed`, `member_mask`, `trend_state`, `month_key`, `eligible_mask`, `candidates`, `NullDraw`, `matched_null` |
| `swingbot/core/backtesting/screen/forward.py` | V140-5 | `HORIZONS`, `forward_atr`, `excess_drift`, `spearman`, `yearly_rank_corr` |
| `swingbot/core/backtesting/screen/verdict.py` | V140-12 | `PairedEvent`, `WeekSum`, `Verdict`, `decide` and its clause helpers |
| `swingbot/core/backtesting/instrument/stats.py` | V140-10 | `VERDICTS` + 3, `INSTRUMENTS` + `screen-v1` |
| `scripts/backtest/screen_idea.py` | V140-13, V140-14 | load, screen, summarise, render, publish, refuse |
| `tests/backtesting/screen/` | V140-1..9, V140-12 | `helpers.py` plus one test file per module |
| `tests/backtesting/test_instrument_stats_ledger.py` | V140-10 | vocabulary pin |
| `tests/scripts/test_screen_idea.py` | V140-13, V140-14 | script tests |
| `tests/hooks/test_spec_screen_header.py` | V140-11 | the `**Screen:**` enforcement |
| `docs/claude/backtest-methodology.md`, `docs/claude/document-conventions.md`, `CLAUDE.md`, `AGENTS.md`, `.claude/skills/new-doc/SKILL.md`, `.claude/agents/plan-writer.md` (+ generated `.agents/skills/new-doc/SKILL.md`, `.codex/agents/plan-writer.toml`) | V140-11 | Stage −2 and the `Screen:` line, one commit with the Codex mirror |
| `docs/superpowers/results/<run-date>-screen-<idea>.md`, ledger | V140-15..18 | one results doc and one ledger row per idea |
| `docs/claude/backtest-methodology.md` closed table, `docs/superpowers/results/<date>-v140-screen-summary.md`, spec `Status:` | V140-19 | close-out |

## Global Constraints

- Research tooling only: nothing under `swingbot/` outside `swingbot/core/backtesting/` imports `swingbot.core.backtesting.screen` (pinned by V140-1's test). No config flag, store, alert, chart or live path changes. `Bump: none`.
- Universe / window: point-in-time S&P 500 (`data/backtest_cache_ext`, membership from `data/universe/sp500_membership.csv`), 2010-01-01..2019-12-31; events count from 2011-01-01 (2010 primes the indicators, F14). The screen never reads 2020+.
- The fixed trade: event on bar *t* (known at *t*'s close); entry = open of *t+1*; `risk = 1.5 × ATR14[t]`; stop = entry − risk; target = entry + 2 × risk (3 × ATR14; reward:risk 2.0). Long only. On each of bars *t+1 … t+cap*: open at or below the stop → exit at the open; else open at or above the target → exit at the open; else low touches the stop → exit at the stop (checked first); else high touches the target → exit at the target. After bar *t+cap*, exit at its close.
- Costs: entry and exit each worsened by `SLIPPAGE_BPS` (default 5 bps, `edge/frictions.apply_frictions`), plus `commission_r()` (0.02R at the default basis). Both arms pay them.
- Drops and skips, each counted: `dropped_window` (race would read past the window), `dropped_warmup` (no full ATR14/SMA200 warm-up), `skipped_overlap` (one open race per ticker), `dropped_no_match` (fewer than 5 null candidates).
- Matched baseline: eligible bar = member at *t* (`pit_membership.is_member` semantics), warm-up complete, race completes inside the window, *t* not an event bar. Trend state = `close[t] > SMA200[t]`. **K = 20** draws without replacement, same ticker, same `YYYY-MM`, same trend state; fewer than 5 candidates → dropped. Seed 42, deterministic per (idea, ticker): `np.random.default_rng([42, zlib.crc32(idea.encode()), zlib.crc32(ticker.encode())])`. Null bars are not subject to the one-open-race rule.
- Triggers, frozen, one parameter set each, no grid: `high52w` (close ≥ 0.95 × max(high, 252) and SMA50 > SMA200; first true bar after ≥ 20 consecutive false bars; cap 60), `uptrend_pullback` (close > SMA200 and Wilder RSI(2) < 10; cap 10), `gap_volume` (open ≥ close[t−1] + 1.0 × ATR14[t−1], volume ≥ 2 × mean(volume, 50 bars ending t−1), close ≥ open; cap 20), `turn_of_month` (*t* is the last trading day of its calendar month from the ticker's own bar dates; cap 4).
- Verdict, per kept event `d_i = R_event_i − mean(R_null_i)`: (1) ΔExpR = mean(d) ≥ +0.10R; (2) lower 95% bound > 0 — `week_cluster_bootstrap` over ISO entry weeks, 10,000 resamples, seed 42, statistic mean(d); (3) same sign in ≥ 7 of 9 calendar years (2011–2019), a year with no events counts against; (4) N ≥ 300 kept events. All four → `SCREEN-PASS`; N < 300 → `SCREEN-UNDERPOWERED` (closed like a fail); else `SCREEN-FAIL`. Forward drift and rank correlation are printed beside the verdict and never read by it.
- Disclosure in every result: N kept and every drop/skip counter; the PIT members missing from the cache; mean `R_event` and mean `R_null` separately; stop/target/timeout/gap mix for both arms; per-year `mean(d)` and N; the forward-drift table.
- Discipline: one shot per idea (`screen_idea.py` refuses a `screen-<name>` id already in the ledger); a fail is closed, never re-screened with new parameters, and gets no spec; a pass buys a spec, not a verdict. Existing ledger rows are untouched.
- Enforcement: every spec numbered above v140 carries `**Screen:**` under `**Edge:**`; `tests/hooks/test_spec_screen_header.py` enforces it. v140 and earlier are grandfathered by number.
- Every function written or changed ends at cyclomatic complexity < 15: `python -m radon cc -s -n C <files>` prints nothing.
- TDD in every code task. Per-task check: `python scripts/dev/testrun.py file <the task's test file>`. The full suite runs **once**, in V140-20.

## Frozen readings (the spec is silent or loose; fixed here, before any run, and quoted in every results doc's trigger line or code docstring)

| # | Reading | Where |
|---|---|---|
| F1 | `turn_of_month` decides "last trading day" from the next bar's **date** (never its prices). The final bar of any frame has no next bar and is `False`. Its lookahead guard therefore compares every bar but the truncated frame's last, and a second test pins that the trigger reads no price column at all. The exchange calendar is public in advance; no price after *t* is read | V140-9 |
| F2 | Events are masked by PIT membership at *t* exactly as null bars are (the universe is point-in-time). A non-member event bar is counted as `dropped_nonmember`, a fifth counter beside the spec's four | V140-3, V140-13 |
| F3 | `high52w`'s "≥ 20 consecutive false bars" counts only bars where the condition is computable (252-bar max, SMA50 and SMA200 all defined). Warm-up bars are not "false"; otherwise the first computable bar would always fire | V140-6 |
| F4 | One open race per ticker: an event at bar *s* is skipped while *s* < the running race's exit bar. An event on the exit bar itself is a new race (the position closed during or at the end of that bar). Overlap is decided before null matching; an event later dropped for `dropped_no_match` still occupied the book | V140-3, V140-13 |
| F5 | The week-cluster bootstrap receives one `WeekSum(entry_date, total, n)` per ISO week and the statistic `sum(total) / sum(n)`. This is draw-for-draw identical to passing one object per event with statistic `mean(d)` (same sorted week keys, same picks, a picked week contributes all its events), and ~50× cheaper. A test pins the equivalence | V140-12 |
| F6 | The ledger `p` is the one-sided bootstrap share of resamples with mean(d) ≤ 0. Reported, never gating, as every ledger p | V140-12, V140-14 |
| F7 | A null draw takes `min(K, candidates)` bars: 5..19 candidates are all used, 20+ are sampled to 20. Same-month candidates include bars after the event (the null is a counterfactual, not a feature) | V140-4 |
| F8 | Warm-up also requires `ATR14[t] > 0` (zero risk cannot define R) | V140-3 |
| F9 | An event's ISO week and calendar year are those of its **entry** bar *t+1* | V140-12, V140-13 |
| F10 | Forward drift is `(close[t+h] − close[t]) / ATR14[t]`; rank correlation is pooled across tickers per calendar year over bars that are members and warm, with the raw event indicator | V140-5, V140-13 |
| F11 | `screen_idea.py` gains `--dry-run` (print only, no doc, no ledger) and `--tickers` (accepted only with `--dry-run`), so a smoke test can never spend the one shot | V140-14 |
| F12 | `Idea` also carries `summary` and `source` strings, quoted in the results doc and the ledger hypothesis | V140-2 |
| F13 | The header test applies the spec's `Edge:` → `Screen:` table as written: a ledger pass fits `expectancy`/`volume`, a headroom path fits `expectancy`/`harvest`, `exempt` fits `none (integrity)` only. A split spec carries the line in its `_0-index` part | V140-11 |
| F14 | Partner decision 2026-10-08: the data window starts 2010-01-01 but **events count from 2011-01-01** (`EVENT_START`, folded into the warm mask, so 2010 events count as `dropped_warmup` and 2010 bars are never null candidates). 2010 only primes ATR14, SMA200 and the 252-bar max, which otherwise left every idea a near-empty 2010 and `high52w` none at all. The year rule becomes ≥ 7 of 9 (2011–2019): the same bar for all four ideas and stricter than 7 of 10 | V140-12, V140-13 |

## Review Focus

Most likely to bite first. Each line names the test that pins it and the task that owns it.

1. **A trigger or indicator that reads a later bar.** Removing every bar after *t* must leave the value at *t* unchanged. Pinned by `helpers.assert_prefix_stable` on every indicator (V140-1) and on each trigger's known-answer frame and a random walk (V140-6..9); `turn_of_month` additionally by `test_turn_of_month_reads_no_prices` (V140-9).
2. **A 2020+ bar reaching the screen.** `load_frame` cuts every frame at the window end before anything else sees it; `--end` after 2019-12-31 is refused. Pinned by `test_load_frame_never_returns_a_bar_after_the_window`, `test_screen_reads_no_2020_bar_end_to_end` (V140-13) and `test_refuses_a_window_end_after_2019` (V140-14).
3. **A second shot at a ledgered idea.** The run is refused with exit 2 before any data is read, the ledger is byte-identical and the first results doc is not overwritten, including under `--dry-run`. Pinned by `test_second_run_of_a_ledgered_idea_is_refused_and_changes_nothing` and `test_dry_run_of_a_ledgered_idea_is_refused` (V140-14).
4. **Gap-through-stop pricing.** An open below the stop exits at that open, so R < −1 is possible and must not be clipped to −1; a gap over the target exits at the open above it. Pinned by `test_gap_through_the_stop_exits_at_the_open_below_minus_one_r` and `test_gap_over_the_target_exits_at_the_open` (V140-3).
5. **The null sampling an event bar.** Any raw event bar — kept, skipped, or dropped — is never a null candidate. Pinned by `test_null_never_samples_an_event_bar` across 50 seeds (V140-4) and `test_screen_ticker_passes_raw_events_to_the_null` (V140-13).

## Parallelisation

Mirrors the spec's grouping.

- **Sequential first:** V140-1 (`indicators`, test helpers) → V140-2 (the `Idea` registry and the four constant-carrying modules) → V140-3 (`race`). Every later screen unit consumes `indicators` and the registry; `null` consumes `race`.
- **Group A (parallel, after V140-3):** V140-4 (`null.py`), V140-5 (`forward.py`), V140-6 (`ideas/high52w.py`), V140-7 (`ideas/uptrend_pullback.py`), V140-8 (`ideas/gap_volume.py`), V140-9 (`ideas/turn_of_month.py`). Disjoint files, each with its own test file; the ideas consume only `indicators` and the module constants V140-2 already wrote, and edit only their own module (the registry is not touched again).
- **Group B (parallel with Group A, and with each other; may start any time):** V140-10 (`instrument/stats.py` vocabulary and its test), V140-11 (header test plus every documentation change and the Codex mirror, one commit). No shared files with the screen package or with each other. V140-11's tests use an in-memory ledger, so it does not consume V140-10.
- **Sequential last:** V140-12 (`verdict.py`; the spec orders it after `null`, though its code consumes only `instrument/stats`) → V140-13 (consumes every screen module and all four triggers) → V140-14 (same file as V140-13; consumes `verdict` and V140-10's vocabulary for the ledger row) → V140-15, 16, 17, 18 **one at a time** via `backtest-runner` (they append to one shared ledger file; two concurrent appends would race) → V140-19 (reads all four results) → V140-20 (the one full suite).
