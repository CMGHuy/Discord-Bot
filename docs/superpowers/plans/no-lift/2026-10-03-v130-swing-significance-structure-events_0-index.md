# v130 — Swing significance tiers and BOS/CHoCH events: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part file whole** — pull one task: `/task-brief V130-2` or `grep -n "^### Task V130-2" -A 180 docs/superpowers/plans/2026-10-03-v130-swing-significance-structure-events_1-tiers-events-snapshot.md`.

**Bump:** none (measurement closed not-more-informative; no code reached main)
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-03-v130-swing-significance-structure-events-design.md`](../specs/2026-10-03-v130-swing-significance-structure-events-design.md)
**Progress:** planning complete; implementation not started. Blocked on v121 merging to `main` (see Preconditions).

**Goal:** Give every confirmed k=3 pivot a causal major/minor tier, label breaks of major swings as BOS or CHoCH, stamp eight new keys on the entry snapshot, and answer once, on TRAIN, whether structure read off major swings separates trade outcomes better than v121's k=3 structure.

**Architecture:** v121's `swingbot/core/market/structure.py` gains four pure functions on top of `pivot_confirmations`: `pivot_tiers` (one row per pivot with the bar it became major), `major_pivots` (per bar, the last two major highs and lows known at that bar), `structure_events` (per bar, the latest BOS/CHoCH) and `major_structure_features` (the eight snapshot keys). `edge/context.py:entry_context` merges that dict with one unconditional statement, so the live stamp and both replay paths pick the keys up with no new wiring. `scripts/reports/structure_tier_report.py` imports v121's bucketing helpers and prints four tables plus the pre-registered verdict.

**Tech Stack:** Python 3.11, pandas/numpy, `market.indicators.atr`, v121's `structure.py` and `volume_context_report.py`, pytest (real-Postgres `db_conn` fixture for the storage task).

## Preconditions (check before V130-1 and again before V130-4)

v121 must be on `main`. At writing it is not: only V121-1 (`confirmed_pivots`) exists, on branch `2026-10-02-v121-structure-volume-context`. This plan is written against v121's **planned** contracts (its tasks V121-2, V121-3 and V121-5), so verify them before starting:

```bash
git grep -n "^def structure_features\|^def _state\|^MIN_BARS = 60\|^def confirmed_pivots\|^def pivot_confirmations" -- swingbot/core/market/structure.py
git grep -n "out.update(structure_features(df, direction))" -- swingbot/core/edge/context.py
git grep -n "^def bucket_table\|^def quintile_edges\|^def replay_all\|^def live_rows\|^def window_refusal\|^class ReportRow" -- scripts/reports/volume_context_report.py
python -c "from swingbot.core.edge.context import FEATURE_KEYS; assert len(FEATURE_KEYS) == 34, len(FEATURE_KEYS)"
```

Expected: five hits, one hit, six hits, no assertion error. **If any is missing or v121 landed with a different name or signature, stop and report BLOCKED** — the code blocks below import these names verbatim. V130-5 alone has no v121 dependency and may start early.

Implementation happens in a worktree created with the `worktree-lifecycle` skill, branch `2026-10-03-v130-swing-significance-structure-events`.

## Spec corrections and frozen readings (the plan follows these)

1. **A fourth public function, `pivot_tiers(df)`.** The spec names three. Table 4 (the tier census) needs every pivot with the bar it became major, and `major_pivots` is built from the same table, so there is one tier implementation, not two.
2. **An undercut on the qualifying bar itself disqualifies.** The spec says "before both conditions hold". A daily bar cannot order its low against its close, so a bar that both undercuts `Low[i]` and closes above `SH_ref` is read conservatively: never major.
3. **ATR14 at the pivot must be a positive number.** A pivot in the first 13 bars (ATR is NaN) or on a zero-range series stays minor, and its reaction key is `None`.
4. **A close beyond a major pivot while the major state is `None` fires no event and spends the pivot.** "Each major SH fires at most once: the first such close" is read literally: the first close is the only candidate, whether or not it produced an event.
5. **Table 4 is printed once, not per horizon.** Every horizon replays the same daily frame (`replay_scenarios(ticker, df, horizon_key, ...)`), so the census cannot differ by horizon. It counts pivots formed inside the window and reads no bar after the window end; pivots near the end are right-censored, and the table says so by construction (it reports "ever became major *within TRAIN*").
6. **Table 3 quintile edges are fixed per direction from the TRAIN replay** and written to `data/v130_train_quintiles.json` (gitignored). A live run requires that file and refuses without it, as v121's report does.
7. **Verdict reading (pre-registration, frozen here before any run):**
   - Conditions 1 and 2 are evaluated on the confluence-sourced population **pooled over both directions**. The keys are direction-normalised ("aligned" means `up` for a long and `down` for a short), which is what makes pooling meaningful.
   - `N` is the count of closed trades in the bucket. "Aligned" is the key being `True`, "not aligned" is `False`; `None` enters neither.
   - Condition 3 compares the sign of `spread(structure_aligned_major)` on confluence bullish against confluence bearish. Bearish thin (either of its two buckets under 30) passes. Bullish thin with bearish not thin **fails**.
   - A spread that cannot be computed (thin, or no closed R) fails condition 1.
   - `--source live` prints the tables only: no verdict.
   - The measurement runs **once**. `--json` refuses to overwrite an existing verdict file.
8. **Close-out follows `document-lifecycle.md`.** `no-lift/` means `main` holds none of the plan's code. So the branch merges, and the bot patch bump happens, **only** on "more informative". On "not more informative" the branch is kept unmerged, `Bump:` is amended to `none`, and plan plus spec move to `no-lift/`. The measurement therefore runs on the branch, before any merge.
9. **Storage is "add → doc, no revision".** `trades` is a hybrid table and `entry_context` lives in `doc JSONB` (v121's V121-4 finding). V130-5 re-checks it with the `schema-change` skill and pins it with a round-trip test.
10. **One v121 test line changes.** `tests/edge/test_edge_context_structure.py` asserts `FEATURE_KEYS[20:] == STRUCTURE_NEW`; appending eight keys makes that `FEATURE_KEYS[20:34]`. V130-4 makes the edit. No v121 behaviour changes.
11. **Cost.** Prototyped on a 2500-bar frame: `major_structure_features` takes about 27 ms per call beside v121's 19 ms for `structure_features`. Replay stamps one snapshot per plan, so replay-heavy tests get slower. V130-8 says what to do if one regresses badly.

12. **Truncation tests run every cut on the hand-built and synthetic frames, and a stride on the real-symbol frame.** The spec asks for every cut on both. `tests/fixtures/ohlcv/TSLA.csv` (first 700 bars) is checked every 7th cut for `major_pivots` and `structure_events`, and every 5th for the feature dict; every cut there would cost about 10 s per test for no extra coverage of the rule. The tier rule itself is also checked pivot-by-pivot against a literal bar-by-bar reading of the spec on the same frames.

## Global Constraints

- Measurement only: no gate, entry, stop, target, exit, alert text, chart or score reads the new keys.
- Everything reads v121's `pivot_confirmations(df, k=3)`. No second pivot detector. v121's and v124's functions and keys stay byte-identical.
- `SWING_MAJOR_ATR_M = 2.0` is a frozen module constant, not a config knob. Event-age buckets are fixed at `0-5`, `6-20`, `21+`. No search over either.
- Major rule (bullish; bearish mirrors every comparison): a confirmed k=3 swing low at `i` becomes major at the first bar `j >= i + 3` where `Close[j] > SH_ref` **and** `max(High[i..j]) − Low[i] >= 2.0 × ATR14[i]`, with `SH_ref` the High of the last confirmed swing high whose index is `< i`. A strictly lower Low on any bar `i+1..j` disqualifies it for good. No `SH_ref` means minor.
- The tier is a fact from bar `j` onward, never back-dated. Majors are ordered by pivot index, not by when they qualified.
- Events: at bar `j`, with `MSH` the last major swing high known at `j − 1`, `Close[j] > High[MSH]` fires once per `MSH`. State `down` at `j − 1` → bullish `choch`; `up` or `mixed` → bullish `bos`; `None` → no event.
- Frames shorter than 60 bars return `None` for every new key and never raise.
- Truncation stability is the no-lookahead contract: every function computed on `df.iloc[:t+1]` equals row `t` of the full-frame result.
- Replay reads TRAIN `2020-01-01..2023-12-31` only. Any window touching 2024-01-01 or later is refused.
- Buckets with `N < 30` print `thin` and no ExpR.
- No backfill of historical trade records and no read-time upcasting: an old record reads `None` through `dict.get`.
- Every function written or changed ends at cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>`). `entry_context` is already `C (17)`: add **no branch** to it.
- Per-task test runs: `python scripts/dev/testrun.py file <path>`. The full suite runs **once**, in V130-8.
- Read `architecture.md`, `known-traps.md`, `code-complexity.md` and `backtest-methodology.md` before editing. Invoke `no-lookahead` in V130-4 and `backtest-gate` before V130-7's run.

## File map

| File | Responsibility |
|---|---|
| `swingbot/core/market/structure.py` (modify) | `pivot_tiers`, `major_pivots`, `structure_events`, `major_structure_features`, `SWING_MAJOR_ATR_M`, `TIER_COLUMNS`, `MAJOR_COLUMNS`, `EVENT_COLUMNS`, `MAJOR_KEYS`. Appended below v121's code; nothing above it changes. |
| `swingbot/core/edge/context.py` (modify) | Append the eight keys to `FEATURE_KEYS`; merge `major_structure_features`. |
| `tests/market/structure_tier_fixtures.py` (new) | Hand-built frames with known tiers and events, each mirrorable. |
| `tests/market/test_structure_tiers.py`, `test_structure_events.py`, `test_major_structure_features.py` (new) | One file per function group. |
| `tests/edge/test_edge_context_major.py`, `tests/fixtures/v130/entry_context_witness.json` (new) | Witness of every older key, merge tests, live-stamp test. |
| `tests/edge/test_edge_context_structure.py` (modify, one line) | v121's key-order assertion narrows to `[20:34]`. |
| `tests/db/test_entry_context_major_doc.py` (new) | New keys round-trip through `trades.doc`. |
| `scripts/reports/structure_tier_report.py`, `tests/scripts/test_structure_tier_report.py` (new) | The four tables, the census and the verdict. |
| `.gitignore` (modify) | `data/v130_*.json`. |

## Review Focus

1. **Same-bar leakage in events.** An event at bar `j` must read majors from row `j − 1`. Reading row `j` lets a pivot fire on the bar it became major. Pinned by `test_an_event_reads_only_majors_known_the_bar_before` (V130-2).
2. **Back-dating a tier.** `major_pivots` must not show a pivot before its `major_pos`, even though the pivot's own index is earlier. Pinned by `test_a_major_is_never_known_before_its_qualifying_bar` (V130-1).
3. **Qualifying order.** An older pivot can qualify after a newer one; the "last two" must still sort by pivot index. Pinned by `test_majors_sort_by_pivot_index_not_by_when_they_qualified` (V130-1).
4. **A raise inside `major_structure_features`** would blank the whole live snapshot (`stamp_entry_context` swallows into `{}`) and crash replay (`backtest.py` calls `entry_context` bare). Pinned by the NaN-bar, flat-frame and `None`-frame tests (V130-3).
5. **Old live records carry none of the new keys.** The report must bucket them as `None`, never `KeyError`. Pinned by `test_live_prints_the_holdout_warning_and_no_verdict` (V130-6).
6. **A thin bucket leaking an ExpR into the verdict.** `spread` must return `None` when either bucket is under 30. Pinned by `test_verdict_fails_when_a_spread_bucket_is_thin` (V130-6).

## Parts

| Part | File | Tasks |
|---|---|---|
| 1 | `2026-10-03-v130-swing-significance-structure-events_1-tiers-events-snapshot.md` | V130-1 .. V130-5 (Phases 1–2: tiers, events, snapshot keys, snapshot merge, storage re-check) |
| 2 | `2026-10-03-v130-swing-significance-structure-events_2-report-and-measurement.md` | V130-6 .. V130-8 (Phases 3–4: report, the one TRAIN run, full suite and close-out) |

## Parallelisation

- **Sequential chain:** V130-1 → V130-2 → V130-3. All three append to `structure.py`. V130-2 consumes `major_pivots`; V130-3 consumes `_major_table`, `_events_table` and `_major_state`.
- **Group A (parallel with the chain):** V130-5. Its only file is `tests/db/test_entry_context_major_doc.py`, and it imports nothing this plan or v121 introduces.
- **Sequential:** V130-4 after V130-3 (imports `major_structure_features`, `MAJOR_KEYS`). V130-6 after V130-4 (buckets the keys the snapshot now emits) — it also needs V130-1's `pivot_tiers` and the fixtures file.
- **Sequential tail:** V130-7 after V130-6 (runs the report). V130-8 last (the one full-suite run, then the verdict-dependent close-out).
- **Cross-plan:** v122 and v123 also consume `structure.py` after v121. They append different functions; whichever lands second rebases. v125 (`location-plan-provenance-context`) appends nine keys to `FEATURE_KEYS` and is also written against the 34-key tuple. If v125 merged first, the Preconditions count is 43, not 34: shift every `34`/`42` literal in V130-4 (the witness length, the key-order test, the `[20:34]` edit is then already made by v125 or no longer needed) by nine, all together, and say so in the commit body.

## Close-out (2026-10-08)

TRAIN verdict: **not more informative** (confluence-sourced; spread k3 -0.002417, major -0.169736; 12207 closed trades; `major_spread_larger` FAIL). Results: `docs/superpowers/results/2026-10-03-v130-structure-tier.{txt,json}`. The run used the 72 cached local-watchlist tickers passed via `--tickers` because the configured DB host was unavailable, not a DB-resolved universe.

Branch `2026-10-03-v130-swing-significance-structure-events` is deliberately left unmerged (a considered decision) and must not be deleted. Its full suite was 5564 passed, 2 failed: the v1 byte-identical golden tests in `tests/backtesting/instrument/` fail because v130 added major-tier keys to `entry_context`; the golden was not regenerated since nothing reaches main. No release, no follow-on spec.

