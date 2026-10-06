# v133 — Liquidity pools and four-role coverage in the entry snapshot: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part file whole** — pull one task: `/task-brief V133-2` or `grep -n "^### Task V133-2" -A 260 docs/superpowers/plans/2026-10-06-v133-liquidity-role-coverage_1-liquidity-roles-snapshot.md`.

**Bump:** bot patch (only if the verdict is "more informative" and the branch merges; otherwise none — see V133-10)
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-06-v133-liquidity-role-coverage-design.md`](../specs/2026-10-06-v133-liquidity-role-coverage-design.md)
**Progress:** planning complete; implementation not started.

**Goal:** Build the missing liquidity instrument (equal-high / equal-low pools and their sweeps), stamp five liquidity keys and five role keys on every entry snapshot, and answer once, on TRAIN, whether the number of distinct roles a setup covers separates trade outcomes better than the number of level votes it collects.

**Architecture:** Two new pure modules sit beside v121's `structure.py` in `swingbot/core/market/`. `liquidity.py` builds an event table of pools from `structure.pivot_confirmations(df, k=3)` and reads it as of one bar; `roles.py` turns the already-computed v121 and liquidity dicts, plus one `reaction.reaction_kind` call, into four flags and their count. `edge/context.py:entry_context` merges both with one branch-free statement, so the live stamp and both replay paths pick the ten keys up with no new wiring. `scripts/reports/role_coverage_report.py` imports v121's bucketing and replay helpers and prints six tables plus the pre-registered verdict.

**Tech Stack:** Python 3.11, pandas/numpy, `market.indicators.atr`, `market.structure`, `market.reaction`, `scripts/reports/volume_context_report.py`, pytest (real-Postgres `db_conn` fixture for the storage task).

## Preconditions (check before V133-1 and again before V133-5)

```bash
git grep -n "^def pivot_confirmations\|^def confirmed_pivots\|^def structure_features\|^MIN_BARS = 60\|^PIVOT_K = 3\|^def _num" -- swingbot/core/market/structure.py
git grep -n "^def is_test\|^def reaction_kind\|^RECLAIM_BARS = 2\|^R1, R2, R3\|def from_frame" -- swingbot/core/market/reaction.py
git grep -n "out.update(structure_features(df, direction))" -- swingbot/core/edge/context.py
git grep -n "^def window_refusal\|^def quintile_edges\|^def bucket_of\|^def bucket_table\|^def confluence_rows\|^def strategy_rows\|^def replay_ticker\|^def replay_all\|^def live_rows\|^class ReportRow" -- scripts/reports/volume_context_report.py
git grep -n "n_confl, families = levels.count_confirming_strategies" -- swingbot/core/backtesting/backtest_scenarios.py
python -c "from swingbot.core.edge.context import FEATURE_KEYS; assert len(FEATURE_KEYS) == 43, len(FEATURE_KEYS)"
```

Expected: six hits, five hits, one hit, ten hits, one hit, no assertion error. **If a name is missing or has a different signature, stop and report BLOCKED** — the code blocks import these names verbatim. A key count of 51 means v130 landed first: read "Cross-plan" under Parallelisation, then continue.

Implementation happens in a worktree created with the `worktree-lifecycle` skill, branch and directory `2026-10-06-v133-liquidity-role-coverage` (the plan's file stem). Nothing in this plan is implemented on `main`.

## Frozen readings (decisions the spec left open; the plan follows these)

None of these changes a spec definition, constant, bucket edge or verdict clause. Each is the reading the code blocks implement.

1. **Where the six constants live.** `POOL_TOLERANCE_ATR`, `POOL_LOOKBACK_BARS`, `SWEEP_RECLAIM_BARS` in `liquidity.py`; `PATH_NEAR_ATR`, `PATH_SWEEP_RECENT_BARS`, `TRIGGER_TEST_K` in `roles.py`. Values exactly as the spec's table.
2. **Three helpers beyond the spec's four functions.** `liquidity.pools_asof(table, t)`, `liquidity.features_at(table, t, ...)` and `roles.flags_at(bars, atr_arr, t, ...)`. The spec's truncation test compares a truncated frame against "row `t` of the full frame", so something must read row `t` of a full-frame result. `liquidity_features` and `role_features` are thin wrappers over them at the final bar: one code path, not two.
3. **`pools(df)` columns:** `side` (`"sell"` / `"buy"`), `level`, `older_pos`, `newer_pos`, `exists_pos`, `dead_pos`, `sweep_pos`. Positional bar indices; `NaN` where a pool never died or was never reclaimed. The two pivot columns are extra to the spec's list and exist for the tests.
4. **ATR edge cases.** A pool whose `ATR14[i2 + 3]` is not finite does not form. At the entry bar, an ATR that is `NaN` or zero makes `liq_stop_side_atr`, `liq_target_side_atr` and `stop_in_pool` `None` (as v121 treats a zero ATR) and `role_path` `None`. `liq_sweep_bars_ago` and `target_past_pool` need no ATR and are still stated.
5. **A missing or non-finite `stop` / `target`** makes `stop_in_pool` / `target_past_pool` `None`. Neither function ever raises: a raise inside `entry_context` blanks the whole live snapshot (`stamp_entry_context` swallows into `{}`) and crashes replay.
6. **Bearish mirrors, spelled out.** `stop_in_pool`: `level ≤ stop ≤ level + POOL_TOLERANCE_ATR × ATR14[t]` for a live buy-side pool above the close. `target_past_pool`: `target <` the nearest live sell-side pool below the close.
7. **`role_trigger` reads `reaction_kind`'s single return value.** That function ranks R3 > R2 > R1, so a bar that is both a rejection and a follow-through returns `R2` and the flag is `False`. `L` comes from `confirmed_pivots(df).iloc[-1]` (`last_sl` / `last_sh`). With a `NaN` ATR `is_test` returns `False`, so the flag is `False` or (on a reclaim) `True`, never `None`: the spec makes it `None` only when no pivot exists.
8. **`role_location` at the exact midpoint is `True`** (the spec's `≤`).
9. **How the target confluence count reaches a report row.** Verified at writing: `n_confl` (`backtest_scenarios.py:145`) is a local, computed against `sc.take_profit`. `build_confluence_plan` then picks `tp1` with `select_structural_target`, so the count cannot be recomputed from the plan afterwards, and `TradePlanV2` has no field for it. V133-6 therefore adds an optional keyword `confluence_counts: dict | None = None` to `replay_scenarios` (filled `{plan_id: n_confl}` through a helper, so the function's complexity of 15 does not rise) and an optional `annotate=` hook to `volume_context_report`'s `confluence_rows`, `strategy_rows`, `replay_ticker` and `replay_all`. Both default to today's behaviour. **These two files are not in the spec's "In" list**; the spec's Report section requires the count on the row and the helpers imported rather than copied, and this is the smallest change that gives both. Controller: confirm before V133-6 starts.
10. **Report-only row facts.** `report_target_votes` and `report_swept_stop_out` ride on the report row's context dict, never on the plan, and are in no snapshot key list.
11. **Bucket labels.** Coverage `0-1`, `2`, `3-4`, `None`. Votes `2`, `3`, `4+`, plus `<2` (possible only if `MIN_TARGET_CONFLUENCE_COUNT` is below 2) and `None` (live rows). `<2` and `None` enter no spread.
12. **Table 4 quintile edges** come from every closed TRAIN replay row pooled (v121's `quintile_edges`, unchanged) and are written to `data/v133_train_quintiles.json` (gitignored). A live run requires that file.
13. **Table 5.** A "losing trade" is `outcome == "loss"`; its stop bar is `exit_index`; "within `SWEEP_RECLAIM_BARS` bars" is the stop bar and the three after it, the same inclusive window the Sweep definition uses. Replay rows only: live records carry no bars.
14. **Table 6** counts the closed-trade rows (their stamped entry bars) per `horizon_key`, pooled over source and direction. "Live stop-side pool" is `liq_stop_side_atr is not None`.
15. **Verdict reading (frozen here, before any run).** The spec says "per direction" and then, in clause 4, exempts a thin bearish side. Clauses 1–3 therefore cannot be required of both directions (a thin bearish side fails clause 3 by definition). The reading: **clauses 1–3 are evaluated on bullish confluence trades; clause 4 requires the bearish `spread_roles` to have the same sign, unless the bearish side is thin.** "Thin" for clause 4 is either bearish coverage bucket entering `spread_roles` (`0-1`, `3-4`) under `N = 30`. A bullish spread that cannot be computed fails. `N` is the count of closed trades in the bucket. `--source live` and any partial replay (a `--tickers` subset or a sub-window) print no verdict. `--json` refuses to overwrite: the measurement runs once. Controller: confirm before V133-9.
16. **Close-out follows `document-lifecycle.md`.** `no-lift/` means `main` holds none of the plan's code, so the branch merges, and the bot patch bump happens, **only** on "more informative" (the plan then moves to `implemented/` and the spec stays live for its follow-on). On "not more informative" the branch stays unmerged, `Bump:` is amended to `none`, and plan plus spec move to `no-lift/`. The measurement therefore runs on the branch.
17. **Truncation on a real symbol** is every cut of the first 400 bars of `tests/fixtures/ohlcv/TSLA.csv`, marked `slow` (about 2–5 s per test). No stride.
18. **Cost, measured on a prototype.** `liquidity_features` takes about 5 ms on a 700-bar frame and 6.5 ms on 1,900 bars. Replay stamps one snapshot per plan.

## Global Constraints

- Measurement only: no gate, entry, stop, target, exit, confidence score, embed or chart reads the new keys.
- Everything reads `structure.pivot_confirmations(df, k=3)`. No second pivot detector. v121's, v125's, v88's and v49's functions and keys stay byte-identical.
- Frozen module constants, not config knobs: `POOL_TOLERANCE_ATR = 0.25`, `POOL_LOOKBACK_BARS = 100`, `SWEEP_RECLAIM_BARS = 3`, `PATH_NEAR_ATR = 1.0`, `PATH_SWEEP_RECENT_BARS = 5`, `TRIGGER_TEST_K = 0.25`. No search over any of them or over a bucket edge.
- Sell-side pool: confirmed k=3 swing lows at `i1 < i2`, `i2 − i1 ≤ 100`, `|Low[i1] − Low[i2]| ≤ 0.25 × ATR14[i2 + 3]`, and no `Low[i1+1 .. i2+3]` other than `Low[i2]` strictly below `min(Low[i1], Low[i2])`. Level `min(Low[i1], Low[i2])`. Exists from `i2 + 3`, never back-dated. Buy-side mirrors with highs and `max`.
- A pool is live until the first bar `j` with `Low[j] < level`, and dead from `j` whatever follows. Sweep-and-reclaim: some `j'` in `[j, j + 3]` with `Close[j'] > level`, dated at the first such `j'`, a fact only from `j'` onward.
- `reaction.is_reclaim` is not used for sweeps. `role_trigger` is `reaction_kind(...) in (R1, R3)` with `tested_now = is_test(t, L, 0.25, ATR14[t])`, `tested_prev = is_test(t−1, L, 0.25, ATR14[t−1])`, `floor_index = t − reaction.RECLAIM_BARS`.
- `role_coverage` is the number of `True` flags, and `None` when any flag is `None`.
- Frames shorter than 60 bars return `None` for every new key and never raise.
- Truncation stability is the no-lookahead contract: every value computed on `df.iloc[:t+1]` equals the value read at row `t` of the full frame.
- Every stored value is a plain `bool`, `int`, `float` or `None` (the snapshot is JSONB).
- Replay reads TRAIN `2020-01-01..2023-12-31` only. Any window touching 2024-01-01 or later is refused. Buckets with `N < 30` print `thin` and no ExpR.
- No backfill and no read-time upcasting: an old record reads `None` through `dict.get`.
- Every function written or changed ends at cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>`). `entry_context` is `C (17)` and `replay_scenarios` is `C (15)` today: add **no branch** to either.
- Per-task test runs: `python scripts/dev/testrun.py file <path>`. The full suite runs **once**, in V133-10. A backtest from another session may be running: never start a second heavy run beside it.
- Read `architecture.md`, `known-traps.md`, `code-complexity.md` and `backtest-methodology.md` before editing. Invoke `schema-change` in V133-3, `no-lookahead` in V133-8 and `backtest-gate` before V133-9's run.
- Commits happen on the worktree branch, small and per task (`feat(v133): ...`, `test(v133): ...`).

## File map

| File | Responsibility |
|---|---|
| `swingbot/core/market/liquidity.py` (new) | `pools`, `pools_asof`, `features_at`, `liquidity_features`; `POOL_TOLERANCE_ATR`, `POOL_LOOKBACK_BARS`, `SWEEP_RECLAIM_BARS`, `POOL_COLUMNS`, `LIQUIDITY_KEYS`. |
| `swingbot/core/market/roles.py` (new) | `role_features`, `flags_at`; `PATH_NEAR_ATR`, `PATH_SWEEP_RECENT_BARS`, `TRIGGER_TEST_K`, `ROLE_FLAGS`, `ROLE_KEYS`. |
| `swingbot/core/edge/context.py` (modify) | Append the ten keys to `FEATURE_KEYS`; merge both dicts through `_liquidity_and_roles`. |
| `swingbot/core/backtesting/backtest_scenarios.py` (modify) | `confluence_counts` out-parameter on `replay_scenarios`; `_note_votes`. |
| `scripts/reports/volume_context_report.py` (modify) | Optional `annotate=` hook on the replay row builders. |
| `scripts/reports/role_coverage_report.py` (new) | Six tables, the verdict, the CLI. |
| `tests/market/liquidity_fixtures.py` (new) | Hand-built OHLC frames with exact pool geometry, each mirrorable. |
| `tests/market/test_liquidity_pools.py`, `test_liquidity_features.py`, `test_roles.py` (new) | One file per function group. |
| `tests/edge/context_witness.py`, `tests/fixtures/v133/entry_context_witness.json`, `tests/edge/test_edge_context_roles.py` (new) | Witness of every older key, merge tests, live-stamp test. |
| `tests/edge/test_edge_context_location.py` (modify, two lines) | v125's key-count assertion narrows to `[34:43]`. |
| `tests/db/test_entry_context_roles_doc.py` (new) | The ten keys round-trip through `trades.doc`. |
| `tests/backtesting/test_replay_confluence_counts.py`, `tests/scripts/test_volume_context_report_annotate.py`, `tests/scripts/test_role_coverage_report.py` (new) | Row facts and the report. |
| `.gitignore` (modify) | `data/v133_*.json`. |
| `docs/superpowers/results/2026-10-06-v133-role-coverage.{txt,json,md}` (new, V133-9) | The recorded run. |

## Review Focus

1. **Reading the event table without the as-of filter.** `pools(df)` holds deaths and sweeps dated after any earlier bar. Only `pools_asof` may read it at a bar. Pinned by `test_a_sweep_is_not_visible_before_its_reclaim_bar` and the every-cut tests (V133-1, V133-2).
2. **Back-dating a pool.** A pool must not exist before `i2 + 3`. Pinned by `test_a_pool_never_exists_before_its_newer_pivot_is_confirmed` (V133-1).
3. **A dead pool coming back.** Price returning above a broken level must not make it live. Pinned by `test_a_broken_pool_is_never_live_again` (V133-2).
4. **A missing role counted as a failed one.** `role_coverage` must be `None`, not a smaller integer, when any flag is `None`. Pinned by `test_role_coverage_is_none_when_any_flag_is_none` (V133-4).
5. **R2 leaking into the trigger.** Pinned by the `follow-through-alone` case of `test_role_trigger_is_r1_or_r3_at_the_last_confirmed_swing` (V133-4).
6. **A numpy scalar in the snapshot** fails JSONB serialisation on the live path only. Pinned by `test_every_value_is_a_plain_json_type` in both feature test files.
7. **A thin bucket leaking an ExpR into the verdict.** Pinned by `test_spread_is_none_when_either_bucket_is_thin` (V133-7).
8. **Table 5 becoming a snapshot key.** It reads bars after the exit. Pinned by `test_the_report_only_facts_are_in_no_snapshot_key_list` (V133-7).

## Parts

| Part | File | Tasks |
|---|---|---|
| 1 | `2026-10-06-v133-liquidity-role-coverage_1-liquidity-roles-snapshot.md` | V133-1 .. V133-5 (Phases 1–2: pools, liquidity keys, storage re-check, role flags, snapshot merge) |
| 2 | `2026-10-06-v133-liquidity-role-coverage_2-report-and-measurement.md` | V133-6 .. V133-10 (Phases 3–4: row facts, report, review, the one TRAIN run, full suite and close-out) |

## Parallelisation

**Phase 1 — Liquidity instrument and storage re-check**

- **Group 1 (parallel):** V133-1 and V133-3. Disjoint files (`liquidity.py` and its tests against `tests/db/test_entry_context_roles_doc.py`) and no shared symbol: V133-3 names the ten keys as string literals.
- **Sequential:** V133-2 after V133-1 (same file, `liquidity.py`; it consumes `_pool_table` and `pools_asof`).

**Phase 2 — Role flags and the snapshot**

- **Sequential throughout:** V133-4 after V133-2 (`roles.py` consumes the liquidity dict's keys and the fixtures file). V133-5 after V133-4 (it merges both outputs and extends `FEATURE_KEYS`).

**Phase 3 — Report**

- **Sequential throughout:** V133-6 after V133-5 (its replay test asserts on stamped plans). V133-7 after V133-6 (the report passes `annotate=` to `replay_all` and reads the stored keys).

**Phase 4 — Review, measurement and close-out**

- **Sequential throughout:** V133-8 after V133-7 (it reviews the finished code; a lookahead bug found after the one run would taint the record). V133-9 after V133-8 (runs the report). V133-10 last (the one full-suite run, then the verdict-dependent close-out).

**Cross-plan**

- `swingbot/core/edge/context.py` is also edited by v130's snapshot task (V130-4), which appends eight keys to `FEATURE_KEYS`. **Do not run V133-5 beside it in the same tree.** v125 has already merged (the tuple has 43 keys at writing); v130 has no branch yet. Whichever of v130 and v133 lands second rebases its tuple edit; the keys do not overlap. If v130 landed first, the Preconditions count is 51: V133-5's tests are written against `FEATURE_KEYS[-10:]` and a witness captured at implementation time, so nothing else shifts.
- `swingbot/core/backtesting/backtest_scenarios.py` and `scripts/reports/volume_context_report.py` (V133-6) are shared with every open measurement plan. The edits are additive keyword parameters; rebase rather than merge by hand if either file moved.
