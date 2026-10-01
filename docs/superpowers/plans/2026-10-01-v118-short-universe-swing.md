# SHORT candidate universe for existing swing horizons — implementation plan

> **For agentic workers:** Use the repo's `task-brief` and one-task implement/review cycle. Steps use `- [ ]` for tracking; the spec is the contract.

**Goal:** Add qualified SHORT confluence candidates in broad and isolated weakness without changing the existing watchlist scan or its LONG scores.
**Architecture:** Build an optional candidate lane with its own completed-bar reference panel, then feed only bearish scenarios into the existing confluence decisions. Preserve the base scan inputs and measure the additive population at scan level before enabling it.
**Tech Stack:** Python 3.11, pandas, existing scan/plan/alert modules, pytest.
**Spec:** `docs/superpowers/specs/2026-10-01-v118-short-universe-swing-design.md`
**Bump:** bot patch (only if qualified alerts ship)
**Edge:** volume
**Progress:** planning complete; implementation and measurement not started.

## Global constraints

- Keep `SCAN_UNIVERSE`, the ten live confluence horizons, current quality/RS/stop/RR gates, and one-open-trade behavior unchanged for the base lane.
- New lane defaults off, has no broker order connection, and never claims borrow availability.
- Use completed, date-aligned stock/SPY/sector observations; no forming daily bar or today's S&P membership projected into old bars.
- An extra symbol can produce bearish confluence only. It cannot enter the base breadth, base RS cache, base strategy pass, or a bullish alert.
- Do not reuse `block_bullish` as a direction filter. Invoke `alert-surface`, `no-lookahead`, and `backtest-gate` when their edit/run boundaries are reached; read `architecture.md`, `known-traps.md`, and `backtest-methodology.md` first.
- Every changed function stays below cyclomatic complexity 15. Each implementation task runs its named narrow test file and commits its own files; final full suite runs once.
- Measurement is pre-registered before outcome inspection. Do not rerun closed v104/v113 research or spend validation to repair a failed TRAIN result.

## File map and interfaces

| File | Responsibility |
|---|---|
| `swingbot/core/scanning/short_candidates.py` | Pure membership/date/regime selection and immutable candidate facts. |
| `swingbot/core/scanning/short_reference.py` | Separate completed-bar reference panel and aligned returns. |
| `swingbot/core/marketdata/universe.py` | Live snapshot as-of metadata and freshness validation; keep old `load()` behavior. |
| `swingbot/core/scanning/scan_run.py`, `analyze.py` | Bounded extra fetch, bearish-only scan, merge into existing confirmation/order decisions. |
| `swingbot/core/scanning/short_funnel.py` | Direction/source/mode counters and stable rejection reasons. |
| `swingbot/core/scanning/alert_embeds.py` and delivery adapters | Same borrow-check and decision date in Discord and simple/email/push. |
| `swingbot/config.py`, `.env.example` | Default-off feature and bounded fetch budget. |
| `scripts/backtest/measure_short_universe.py` | Scan-level reachability/arm measurement using the same selector and scenario path. |

The names above are intended new seams. An implementer must inspect existing call signatures with `symbol-verifier`/narrow code reads before coding; retain adjacent names if the current checkout differs. Do not add persisted trade-store fields for issuance facts without invoking `schema-change`.

## Review focus

1. A ticker that exists in both lanes must run once through the base lane; Task V118-3 tests deduplication.
2. SPY/stock/sector dates that differ by one trading day must fail closed for the extra lane; Task V118-2 tests this.
3. A stale S&P snapshot or missing sector map must leave base alerts intact and record the skip; Tasks V118-1 and V118-3 test this.
4. A large cold extra pool must not delay or reorder base candidates; Task V118-4 tests the budget boundary.
5. A reversed/open LONG or lost mirror message must not become an unexplained SHORT order suggestion; Tasks V118-5 and V118-6 test routing.

## Parallelisation

- **Phase 1:** V118-1 and V118-2 may run in parallel only if their test files and production files remain disjoint; otherwise serial. V118-3 consumes both contracts.
- **Phase 2:** Sequential V118-4 → V118-5 → V118-6; all touch the scan item's source/mode metadata or scan merge.
- **Phase 3:** Sequential V118-7 → V118-8 → V118-9; reachability precedes any outcome measurement, and the full suite is the last plan task.

# Phase 1 — Frozen inputs

### Task V118-1: Point-in-time and fresh live membership

**Files:** Modify `swingbot/core/marketdata/universe.py`; create `tests/marketdata/test_short_snapshot.py`; modify the snapshot generator in `scripts/data/build_universe.py` only after confirming it owns `sp500.json`.

**Interfaces:** Produce `short_snapshot(date: str, *, live: bool) -> tuple[list[str], str] | None`; on historical dates read `pit_membership.load_intervals()` and `is_member()`, and on live dates require a dated snapshot. `None` means skip extra lane, not fall back to today's list.

- [ ] Write tests with a fixture containing `AAA` ending on `2024-01-03` and `BBB` beginning then. Assert `short_snapshot("2024-01-02", live=False)` contains `AAA`, while `2024-01-03` contains `BBB`; missing membership CSV returns `None`. Assert a missing/stale `as_of` returns `None` live and `universe.load("sp500")` still returns its legacy rows.

  ```python
  before, asof = short_snapshot("2024-01-02", live=False)
  after, _ = short_snapshot("2024-01-03", live=False)
  assert "AAA" in before and "AAA" not in after
  assert "BBB" not in before and "BBB" in after
  assert short_snapshot("2024-01-03", live=True) is None  # no dated live snapshot
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/marketdata/test_short_snapshot.py`; expect the new API test to fail.
- [ ] Add dated snapshot metadata beside the static universe list. Keep `load()`'s row shape stable and validate the metadata only in `short_snapshot`; use the existing `normalize_symbol()` and half-open interval rule. Live freshness must be evaluated against the last completed exchange session, including holidays, not `date.today()`.
- [ ] Run the same file to green and `python -m radon cc -s -n C swingbot/core/marketdata/universe.py scripts/data/build_universe.py` for changed functions; commit only these files and the test.

### Task V118-2: Aligned reference and weakness modes

**Files:** Create `swingbot/core/scanning/short_reference.py`, `swingbot/core/scanning/short_candidates.py`, `tests/scanning/test_short_candidates.py`.

**Interfaces:** `align_completed(stock, spy, sector, now) -> tuple[DataFrame, DataFrame, DataFrame | None] | None`; sector may be absent for broad weakness. `select_mode(stock, spy, sector, *, spy_regime, reference_rels) -> tuple[str | None, str | None]` returns either a mode or a stable rejection reason.

- [ ] Test broad SPY bearish plus laggard stock, isolated SPY nonbearish plus `stock_63d < sector_63d`, non-laggard rejection, missing sector, missing SPY, one-day date mismatch, and a still-forming today bar. Use synthetic frames where the last close flips the comparison so accidental lookahead is visible.

  ```python
  mode, reason = select_mode(stock, spy, None, spy_regime=bearish,
                             reference_rels=laggard_panel)
  assert (mode, reason) == ("broad", None)
  mode, reason = select_mode(stock, spy, stale_sector, spy_regime=neutral,
                             reference_rels=laggard_panel)
  assert (mode, reason) == (None, "unaligned_sector")
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/scanning/test_short_candidates.py`; expect the selector test to fail.
- [ ] Implement aligned 64-observation windows on the same completed dates. For example, calculate `stock_return = close.iloc[-1] / close.iloc[-64] - 1` only after index intersection and assert all final dates equal. Use the existing `get_market_regime` result, the extra panel's RS percentile, and a single source of sector ETF mapping. Do not alter `edge/factors.relative_return()` globally in this task.
- [ ] Truncate every frame at bar `t` and repeat the selector test; results at `t` must equal the full-frame results recorded at `t`. Run the narrow file, radon on both new modules, and commit.

### Task V118-3: Extra candidate contract and base invariance

**Files:** Modify `swingbot/core/scanning/scan_run.py`; create `tests/scanning/test_short_lane_split.py`.

**Interfaces:** `build_extra_candidates(base_tickers, *, decision_date, snapshot, reference) -> list[ShortCandidate]`; candidate facts are `ticker`, `source="short_universe"`, `mode`, `decision_bar_date`, `membership_asof`, `reference_id`. If no valid snapshot/reference, return an empty list with a reason.

- [ ] Pin a base-only scan fixture's tickers, breadth, `rs_cache["rels"]`, strategy-pass tickers and ordered LONG alert payload. With flag off, assert byte-equivalent outputs. With flag on, assert a symbol shared with base is absent from extra candidates and no extra symbol enters those four base inputs.

  ```python
  assert base_off.tickers == base_on.tickers
  assert base_off.breadth == base_on.breadth
  assert base_off.rs_rels == base_on.rs_rels
  assert base_off.long_payloads == base_on.long_payloads
  assert set(extra_symbols).isdisjoint(base_off.tickers)
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/scanning/test_short_lane_split.py`; expect failure.
- [ ] Add default-off config field `SHORT_UNIVERSE_ENABLED` and `.env.example` description. Build the extra list after preserving `base_tickers` and `base_fresh_data`; pass an immutable extra reference/context to a separate scan call rather than extending the original `tickers`/`fresh_data` objects used for breadth and RS. Missing data returns an empty extra lane with reason.
- [ ] Run the narrow file and `tests/scanning/test_regime_frame_reuse.py`; commit config, scan split and tests.

# Phase 2 — Qualifying alerts

### Task V118-4: Bounded fetch and bearish-only scenario analysis

**Files:** Modify `swingbot/core/scanning/fetch.py`, `scan_run.py`, `analyze.py`; create `tests/scanning/test_short_lane_scan.py`.

**Interfaces:** `scan_extra_candidate(candidate, frame, context, horizons) -> list[ScanItem]`; same level/scenario/geometry/quality/RS functions as base scan. Filter by `item.result.direction == "bearish"` after scenario creation, before plan/confirmation. The symbol budget is a max count and elapsed-time cap from explicit config defaults.

- [ ] Test one bullish and one bearish scenario from the same extra ticker: only bearish continues. Test current liquidity/data-quality rejection, a cold fetch timeout, budget exhaustion, and that the base scan's order and timing hooks are unchanged. Add a baseline snapshot of base LONG scores with flag both ways.

  ```python
  assert [item.result.direction for item in scan_extra_candidate(
      candidate, frame, context, ["2w"])] == ["bearish"]
  assert base_off.long_scores == base_on.long_scores
  assert base_off.strategy_tickers == base_on.strategy_tickers
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py`; expect failure.
- [ ] Prefetch extra symbols in bounded batches after base crawl. Reuse cache-first fetch and E12/E16 checks. Extract a small scenario-processing seam from `_scan_one` if needed; do not send extra candidates through the strategy pass or repurpose `block_bullish`. A budget exhaustion stops only the extra queue and records `budget_exhausted`.
- [ ] Run the narrow test and `tests/scanning/test_sidelist_cache_first.py`; run radon on changed files; commit.

### Task V118-5: Direction/source/mode funnel and existing-trade routing

**Files:** Create `swingbot/core/scanning/short_funnel.py`, `tests/scanning/test_short_funnel.py`; modify `scan_run.py` at the existing per-ticker result merge and send decisions.

**Interfaces:** `ShortFunnel.record(direction, source, mode, stage, reason=None)` counts by tuple, with stable stages `candidate`, `aligned`, `scenario`, `geometry`, `confidence`, `rs`, `plan`, `trade_decision`, `dedup`, `send`; `snapshot()` returns serializable counters.

- [ ] Test ordered stage counts for base LONG, base SHORT, broad extra SHORT and isolated extra SHORT. Test one-open-trade conflict and reversal: an existing LONG retains the current decision semantics, and the funnel says `existing_trade` rather than `send` if suppressed.

  ```python
  funnel.record("bearish", "short_universe", "broad", "trade_decision",
                reason="existing_trade")
  assert funnel.snapshot()["bearish/short_universe/broad/trade_decision/existing_trade"] == 1
  assert funnel.snapshot().get("bearish/short_universe/broad/send", 0) == 0
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/scanning/test_short_funnel.py`; expect failure.
- [ ] Aggregate each worker's immutable counter delta in `scan_run.py` after `map_tickers()` joins, following current race-avoidance pattern. Keep candidate facts attached to emitted items without changing persisted store shape. Add final scan telemetry keyed by direction/source/mode and explicit stale/missing/budget reasons.
- [ ] Run the narrow file plus `tests/scanning/test_paper_trade_decision.py`; commit.

### Task V118-6: Borrow-check and date parity across alert mirrors

**Files:** Modify `swingbot/core/scanning/alert_embeds.py` and the actual simple/email/push adapter found by `rg -n "build_strategy_simple_embed|simple_alert|push" swingbot/core/scanning swingbot/core/presentation`; create `tests/scanning/test_short_alert_parity.py`.

**Interfaces:** A single `short_lane_notice(candidate, plan) -> str` supplies mode, decision date, entry/stop/target/expiry and literal `CHECK BORROW AVAILABILITY` to each renderer. A stale date is marked `STALE`.

- [ ] Build a new-lane plan fixture and assert the literal borrow text, mode, bar date, numerical entry/stop/target and expiry appear in Discord and every enabled mirror. Assert a stale bar is labelled, never silently current. Assert a base LONG alert has no borrowed metadata.

  ```python
  for rendered in (discord_text, simple_text, email_text, push_text):
      assert "CHECK BORROW AVAILABILITY" in rendered
      assert "2026-10-01" in rendered
      assert "isolated" in rendered.lower()
      assert formatted_stop in rendered
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/scanning/test_short_alert_parity.py`; expect failure.
- [ ] Put the text/number formatting in one presentation helper and call it from Discord and the mirrors. Keep the recently fixed clamped-stop value as the source of truth. Do not represent a manual broker check as a verified locate.
- [ ] Run the narrow file plus `tests/scanning/test_notifier_clamped_stop.py`; commit.

# Phase 3 — Evidence and close gate

### Task V118-7: Scan-level reachability and pre-registration

**Files:** Create `scripts/backtest/measure_short_universe.py`, `tests/backtesting/test_measure_short_universe.py`, and `docs/superpowers/results/2026-10-01-v118-short-universe-preregistration.md` (use the repo's active results directory convention at execution time).

**Interfaces:** The measurement calls the same `build_extra_candidates` and `scan_extra_candidate` functions as live scan at each historical decision date. Its output records base and added alerts separately with mode, source, decision date, entry, stop, target, exclusion reason and close outcome.

- [ ] Write a fixture with one PIT member that passes and one ex-member that must disappear; assert an extra bearish scenario travels through geometry and plan construction, and the base-only run produces identical base alerts.

  ```python
  assert [row.ticker for row in measured.added] == ["AAA"]
  assert measured.added[0].direction == "bearish"
  assert measured.added[0].plan is not None
  assert measured.base_alerts == baseline.base_alerts
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/backtesting/test_measure_short_universe.py`; expect failure.
- [ ] Freeze population, periods, costs, membership source, selector values, two mode cohorts, borrow-fee sensitivity, dedup and acceptance rule in the pre-registration before reading outcomes. Write the scan-level harness using the shared path. Check that `measure_arms.py` and `validate_component.py` can express an *additive* arm; if not, stop at reachability and document the missing instrument/acceptance amendment before any selection run.
- [ ] Run the narrow file and a single deterministic Stage −1 fixture, not a broad backtest. Invoke `backtest-gate` before even that command. Commit harness, test and frozen record.

### Task V118-8: Serial evidence and conditional admission

**Files:** Add result record under `docs/superpowers/results/` using current convention; change `swingbot/config.py` default/mode allowlist only if the pre-registered gate passes; add `tests/scanning/test_short_lane_admission.py`.

**Interfaces:** `SHORT_UNIVERSE_ENABLED` remains false without a passing mode. Broad and isolated are individually admissible; a pooled improvement cannot admit a losing mode.

- [ ] Pin tests for default-off, broad-only, isolated-only and neither mode. Assert a mode not admitted cannot emit a live alert even if its selector fires; base alerts remain unchanged.

  ```python
  assert emit_modes(enabled=False, allowed={"broad", "isolated"}) == set()
  assert emit_modes(enabled=True, allowed={"broad"}) == {"broad"}
  assert emit_modes(enabled=True, allowed={"isolated"}) == {"isolated"}
  assert emit_modes(enabled=True, allowed=set()) == set()
  ```
- [ ] Run the narrow file and implement the minimal explicit mode allowlist behind the default-off flag; rerun narrow test and commit that inert code before evidence runs.
- [ ] With `backtest-gate` and `backtest-methodology.md` open, execute the pre-registered reachability → MDE → TRAIN plateau → folds → one VALIDATION sequence serially, only if each stage permits the next. Record all applicable acceptance clauses, incremental expectancy/WR/volume, the mode split, missing-data cost and break-even borrow fee. Stop on failure; no threshold edits, sample trimming or second validation shot.
- [ ] If admitted, shadow/soak and compare live vs replay alert numbers, order and latency; enabling on the production VM requires a separate explicit request. If not admitted, leave flag off and record no-lift. Commit the result record without fabricating a pass.

### Task V118-9: Full-suite verification

**Files:** No new feature files; fix only failures attributable to this plan and update their narrow tests.

- [ ] Run `python scripts/dev/testrun.py full` once (or use the `test-runner` role). Green requires `0 failed` and `0 xfailed`.
- [ ] If it fails, fix forward, run the named narrow file, then resolve the suite failure. Check changed functions with radon and review base LONG invariant, no-lookahead, and all four alert mirrors.
- [ ] Close the plan as implemented or no-lift by the repo's document lifecycle. Only an actual shipped observable alert gets the spec's bot patch bump, resolved from then-current `VERSION.json`; do not hard-code a release number here.
