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
| `swingbot/core/marketdata/universe.py`, `pit_membership.py` | Live snapshot manifest and historical membership/sector as-of lookup; keep old `load()` behavior. |
| `swingbot/core/scanning/scan_run.py`, `analyze.py`, `swingbot/commands/scanning/loops.py` | Bounded extra pass after the base alert send, bearish-only scan, existing confirmation/order decisions. |
| `swingbot/core/scanning/short_funnel.py` | Direction/source/mode counters and stable rejection reasons. |
| `swingbot/core/scanning/alert_embeds.py` and delivery adapters | Same borrow-check and decision date in Discord and simple/email/push. |
| `swingbot/config.py`, `.env.example` | Default-off feature and bounded fetch budget. |
| `swingbot/core/backtesting/arms/` and `scripts/backtest/measure_arms.py` | Extend the standard stamped arm producer to a whole-scan additive population only after its pilot proves equivalent to live gates. |

The names above are intended new seams. The current `measure_arms.py` worker receives one ticker frame and its confluence engine skips live confidence/RS/confirmation; it cannot measure v118 by adding a new config knob alone. Task V118-7 adds a whole-scan adapter or stops for a pre-registered bespoke-instrument amendment. Do not call the existing strategy-only backtest an evaluation of this lane. Do not add persisted trade-store fields for issuance facts without invoking `schema-change`.

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

**Interfaces:** Produce `ShortSnapshot(symbols, membership_asof, sector_of)` and `short_snapshot(day: str, *, live: bool) -> ShortSnapshot | None`; on historical dates read `pit_membership.load_intervals()`/`is_member()` plus dated sector intervals, and on live dates require a dated snapshot. `None` skips the extra lane, never falls back to today's list.

- [ ] Write tests with a fixture containing `AAA` ending on `2024-01-03` and `BBB` beginning then. Assert `short_snapshot("2024-01-02", live=False)` contains `AAA`, while `2024-01-03` contains `BBB`; missing membership CSV returns `None`. Assert a missing/stale `as_of` returns `None` live and `universe.load("sp500")` still returns its legacy rows.

  ```python
  before = short_snapshot("2024-01-02", live=False)
  after = short_snapshot("2024-01-03", live=False)
  assert "AAA" in before.symbols and "AAA" not in after.symbols
  assert "BBB" not in before.symbols and "BBB" in after.symbols
  assert short_snapshot("2024-01-03", live=True) is None  # no dated live snapshot
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/marketdata/test_short_snapshot.py`; expect the new API test to fail.
- [ ] Add dated snapshot metadata beside the static universe list. Keep `load()`'s row shape stable and validate the metadata only in `short_snapshot`; use the existing `normalize_symbol()` and half-open interval rule. Live freshness must be evaluated against the last completed exchange session, including holidays, not `date.today()`.
- [ ] Run the same file to green and `python -m radon cc -s -n C swingbot/core/marketdata/universe.py scripts/data/build_universe.py` for changed functions; commit only these files and the test.

**Implementation detail.** Keep `sp500.json` a list: `universe.load()` discards extra keys and is used by the base scan. Add a sibling `sp500.snapshot.json` written atomically by `build_universe.py --as-of YYYY-MM-DD`, with `{"as_of": "...", "source": "manual_csv", "raw_sha256": "...", "universe_sha256": "..."}`. Hash the exact raw CSV bytes and the generated JSON bytes. Validate `universe_sha256` against the current JSON before trusting its rows, so a later manual overwrite cannot inherit an old date. Never stamp `today` for a manually copied file whose as-of date is unknown. The live lane requires `as_of <= decision_date` and no more than five completed NYSE sessions of age; `nyse_calendar().sessions_between()` supplies that count. This is a fixed operational default, not a parameter to search against outcomes.

```python
# marketdata/universe.py -- new, read-only adapter; old load() stays unchanged.
@dataclass(frozen=True)
class ShortSnapshot:
    symbols: tuple[str, ...]
    membership_asof: str
    sector_of: dict[str, str]

def live_short_snapshot(day: str) -> ShortSnapshot | None:
    meta = read_json(os.path.join(UNIVERSE_DIR, "sp500.snapshot.json"), {})
    asof = meta.get("as_of")
    if not asof or asof > day or meta.get("source") != "manual_csv":
        return None
    if meta.get("universe_sha256") != sha256_file(os.path.join(UNIVERSE_DIR, "sp500.json")):
        return None
    age = nyse_calendar().sessions_between(date.fromisoformat(asof), date.fromisoformat(day))
    if age is None or age > 5:
        return None
    rows = load("sp500")
    return ShortSnapshot(tuple(row["symbol"] for row in rows), asof,
                         {row["symbol"]: row["sector"] for row in rows})

def short_snapshot(day: str, *, live: bool) -> ShortSnapshot | None:
    return live_short_snapshot(day) if live else historical_short_snapshot(day)
```

For historical replay, load `sp500_membership.csv` with `pit_membership.load_intervals()` and require `sp500_sector_history.csv` with `(ticker,start_date,end_date,sector)` and the same half-open interval rule. `historical_short_snapshot(day)` returns `None` when membership is absent; its `sector_of` omits a symbol with no as-of sector instead of borrowing today's sector. Add a test where a ticker switches sectors at an interval boundary. Commit command: `git add swingbot/core/marketdata/universe.py swingbot/core/marketdata/pit_membership.py scripts/data/build_universe.py tests/marketdata/test_short_snapshot.py && git commit -m "feat(v118): date short universe membership"` (omit an unchanged path).

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

**Implementation detail.** Keep the base `edge/factors.relative_return()` intact: it compares terminal positions even when dates differ. The extra lane gets a strict aligned helper and a pure panel whose `rels` never writes `rs_cache.json`. The sector frame may be `None` for broad weakness; isolated weakness requires it.

```python
# scanning/short_reference.py
def aligned_window(stock: pd.DataFrame, spy: pd.DataFrame,
                   sector: pd.DataFrame | None, now) -> tuple | None:
    stock, spy = completed_frame(stock, now), completed_frame(spy, now)
    if stock is None or spy is None or stock.empty or spy.empty:
        return None
    if stock.index[-1].date() != spy.index[-1].date():
        return None
    if sector is not None:
        sector = completed_frame(sector, now)
        if sector is None or sector.empty or sector.index[-1].date() != stock.index[-1].date():
            return None
    common = stock.index.intersection(spy.index)
    if sector is not None:
        common = common.intersection(sector.index)
    if len(common) < 64:
        return None
    return (stock.loc[common], spy.loc[common],
            None if sector is None else sector.loc[common])

def return_63(frame: pd.DataFrame) -> float:
    close = frame["Close"]
    return float(close.iloc[-1] / close.iloc[-64] - 1.0)
```

Build `reference_rels` once from eligible extra frames and the same SPY window. Require enough valid symbols for a meaningful percentile; if the panel is empty, skip the extra lane rather than accepting the current `rs_percentile()` synthetic 50.0. Broad selection requires `spy_regime` bearish and percentile at or below `config.RS_LAGGARD_PERCENTILE`; isolated selection requires SPY not bearish, dated sector mapping, and `return_63(stock) < return_63(sector)`. Return named failures such as `unaligned_spy`, `missing_sector`, `short_history` and `not_laggard`. Commit the two new modules and `tests/scanning/test_short_candidates.py` by explicit paths.

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

**Implementation detail.** Define the issuance facts once and keep the new list separate from the four base inputs through the complete base analyze/strategy pass. A duplicate ticker belongs to base even if it qualifies for the extra mode. Avoid mutating `ScanParams` (frozen and picklable); read the new default-off flag from `config` only at orchestration and snapshot it at scan start.

```python
# scanning/short_candidates.py
@dataclass(frozen=True)
class ShortCandidate:
    ticker: str
    mode: Literal["broad", "isolated"]
    source: str
    decision_bar_date: str
    membership_asof: str
    reference_id: str

def extra_symbols(snapshot: ShortSnapshot, base_tickers: Sequence[str]) -> tuple[str, ...]:
    base = set(base_tickers)
    return tuple(symbol for symbol in snapshot.symbols if symbol not in base)

# scanning/scan_run.py -- preserve references before any extra fetch.
base_tickers = tuple(tickers)
base_frames = fresh_data
base_breadth = rs_factors.breadth_pct_above_50ema(base_frames)
base_rs_cache = rs_cache  # the already-computed base cache; never refresh twice
extra_queue = () if not short_enabled else extra_symbols(snapshot, base_tickers)
```

The actual insertion must remain after base crawl and before extra analysis; the shown names explain the data split, not a second RS refresh. Pass exactly `base_tickers`/`base_frames` to `_maybe_run_strategy_pass()`. Pin the base baseline with a fixed clock and deterministic frames so the byte-equivalence assertion covers order as well as numerical values. Commit config, `.env.example`, `scan_run.py`, `short_candidates.py` and the narrow test with explicit `git add` paths.

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

**Implementation detail.** The current scheduled caller is `commands/scanning/loops.py`: it awaits `run_scan()` and then `_send_alerts()`. Run the extra pass only **after** that send so a cold extra ticker cannot hold back a ready watchlist alert. The manual `!check` path in `commands/scanning/commands.py` gets the same sequencing after its base result is sent; a recap/display-only caller stays base-only. Snapshot `SHORT_UNIVERSE_MAX_SYMBOLS=50` and `SHORT_UNIVERSE_FETCH_BUDGET_SECONDS=120` as operational safeguards, not search knobs. Process cache-first chunks up to 20; check the deadline between chunks. Never use a cross-shell or process-pool workaround to bypass the existing cache.

```python
# commands/scanning/loops.py -- scheduled path; send order is the invariant.
base_alerts = await scan_engine.run_scan(require_confirmation=True, bot=bot, progress=progress)
await _send_alerts(channel, base_alerts, route_by_confidence=True)
if config.SHORT_UNIVERSE_ENABLED:
    short_alerts = await scan_engine.run_short_universe_scan(
        require_confirmation=True, bot=bot, progress=short_progress)
    await _send_alerts(channel, short_alerts, route_by_confidence=True)

# scanning/analyze.py -- filter AFTER levels.build_scenarios, preserving DCB meaning.
def scenarios_for_direction(scenarios, allowed_directions):
    if allowed_directions is None:
        return scenarios
    return [s for s in scenarios if s.direction in allowed_directions]
```

Add an optional `allowed_directions=None` argument to `_scan_one()` and replace `for scenario in scenarios:` with `for scenario in scenarios_for_direction(scenarios, allowed_directions):`; this keeps the legacy function's CC from rising. Add a `monitor_existing` switch through a small new wrapper rather than rerunning `update_open_trades()` for a ticker in both lanes. For every outstanding extra-lane paper trade, perform its monitoring even when today's weakness selector rejects that symbol; skipping new entries must not strand an open plan. The extra pass uses the existing `state.confirm_or_update`, `paper_trade_decision`, dedup and send path, but its own reference `rs_cache` is an in-memory `{ "rels": ... }` and never calls `refresh_rs_cache()` (which writes base `rs_cache.json`). Assert scheduled base send occurs before the first extra fetch. Commit the scan/command/config changes and narrow tests by name.

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

**Implementation detail.** `_scan_one()` runs in `map_tickers()` workers and already returns a stats dict; it must not mutate a shared `ShortFunnel`. Add per-item stage/reason tuples to the per-ticker result and merge them serially in the scan runner. The same stable key scheme covers base LONG, base SHORT and each extra mode. Count a stage when reached, and a rejection under that stage only once; a scenario that fails geometry cannot also count as an RS rejection.

```python
# scanning/short_funnel.py
STAGES = ("candidate", "aligned", "scenario", "geometry", "confidence",
          "rs", "plan", "trade_decision", "dedup", "send")

@dataclass
class ShortFunnel:
    counts: Counter = field(default_factory=Counter)

    def record(self, direction: str, source: str, mode: str | None,
               stage: str, reason: str | None = None) -> None:
        if stage not in STAGES:
            raise ValueError(stage)
        self.counts[(direction, source, mode or "base", stage, reason or "ok")] += 1

    def snapshot(self) -> dict[str, int]:
        return {"/".join(key): value for key, value in sorted(self.counts.items())}
```

Stamp `candidate_context` onto `ScanItem` at the result merge, before `attach_plan_v2()`, and preserve it through dedup. Emit `existing_trade` when `paper_trade_decision` blocks; emit `send` only after the alert tuple enters the returned list. The current `notify_secondary()` executes during `_sync_run_scan`, so tests must spy on it too: suppressed extra items must not send email/push. Add a test for an extra-owned open SHORT whose selection mode disappears: the manager/monitor still checks its stop, while the new-entry funnel records `not_selected`. Commit `short_funnel.py`, `scan_run.py`, `analyze.py`, and tests.

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

**Implementation detail.** Confluence alerts render through `alert_embeds.build_embed()` and `build_simple_alert()`, while email/push use `infra/notifier.notify_secondary()`. Supply a small immutable `ShortNotice` from `candidate_context` and the already-clamped `item.plan_v2`; format its human text once in `presentation/short_notice.py`. Keep `plan_numbers_for_display()` as the sole price cutover. Attach a stale marker if the completed decision date differs from the current completed session, and do not stamp a fresh date from the send time.

```python
# presentation/short_notice.py
BORROW_TEXT = "CHECK BORROW AVAILABILITY"

def short_notice_line(mode: str, decision_bar_date: str, *, stale: bool) -> str:
    state = "STALE · " if stale else ""
    return f"{state}{mode} weakness · bar {decision_bar_date} · {BORROW_TEXT}"

# scanning/alert_embeds.py, after plan_numbers_for_display()
if item.candidate_context is not None:
    line = short_notice_line(item.candidate_context.mode,
                             item.candidate_context.decision_bar_date,
                             stale=item.candidate_context.decision_bar_date != completed_day)
    embed.add_field(name="SHORT execution check", value=line, inline=False)
```

The simple embed, email and push consume the same `line` and same `plan_numbers_for_display()` values; do not independently recompute or unclamp stops. `CHECK BORROW AVAILABILITY` means a manual broker check, not an available locate. Run `tests/scanning/test_simple_alerts.py`, `test_short_alert_parity.py`, and `test_notifier_clamped_stop.py` narrowly; commit only touched presentation and notifier files.

# Phase 3 — Evidence and close gate

### Task V118-7: Scan-level reachability and pre-registration

**Files:** Modify `scripts/backtest/measure_arms.py`, `swingbot/core/backtesting/arms/engine.py`, `swingbot/core/backtesting/arms/reachability.py`, `swingbot/config.py`; create `swingbot/core/backtesting/arms/short_universe_engine.py`, `swingbot/core/scanning/scan_replay.py`, `tests/backtesting/test_measure_short_universe.py`, and `docs/superpowers/results/2026-10-01-v118-short-universe-preregistration.md` after the instrument contract is proven.

**Interfaces:** The measurement calls the same `build_extra_candidates` and `scan_extra_candidate` functions as live scan at each historical decision date. Its output records base and added alerts separately with mode, source, decision date, entry, stop, target, exclusion reason and close outcome.

- [ ] Write a fixture with one PIT member that passes and one ex-member that must disappear; assert an extra bearish scenario travels through geometry and plan construction, and the base-only run produces identical base alerts.

  ```python
  assert [row.ticker for row in measured.added] == ["AAA"]
  assert measured.added[0].direction == "bearish"
  assert measured.added[0].planned_rr is not None
  assert measured.added[0].source == "confluence"
  assert measured.base_alerts == baseline.base_alerts
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/backtesting/test_measure_short_universe.py`; expect failure.
- [ ] Freeze population, periods, costs, membership source, selector values, two mode cohorts, borrow-fee sensitivity, dedup and acceptance rule in the pre-registration before reading outcomes. Extend the standard stamped arm producer with a whole-scan engine that calls the shared selector, scenario and final-gate path. If the instrument cannot express the additive arm, stop at reachability and document the missing instrument/acceptance amendment before any selection run.
- [ ] Run the narrow file and a single deterministic Stage −1 fixture, not a broad backtest. Invoke `backtest-gate` before even that command. Commit harness, test and frozen record.

**Implementation detail.** `measure_arms.py` currently sends `(ticker, df)` to `ArmEngine.run_ticker()` and `ConfluenceEngine` calls `replay_scenarios()` without live confidence, RS or dedup. Registering `SHORT_UNIVERSE_ENABLED` as reachable would be false. First extract `qualify_short_item(candidate, scenario, context) -> Accepted | Rejected` from the live scan, with explicit benchmark/reference, as-of prices, frozen hard filters, prior-open state and confirmation state. Characterize the current base result before the extraction and commit the behavior-preserving refactor separately. No network, journal, current open trades or wall clock may hide in the pure helper.

```python
# arms/short_universe_engine.py -- a whole-window pass, not one ticker.
class ShortUniverseEngine:
    engine_id = "short_universe"

    def run_population(self, frames: dict[str, pd.DataFrame], window: tuple[str, str],
                       params: ScanParams, *, mode: str) -> list[ArmTrade]:
        base = replay_base_scan(frames, window, params)   # shared scan gates
        if mode == "off":
            return base
        added = replay_extra_short_scan(frames, window, params, allowed_modes={mode})
        return base + added
```

Create `replay_base_scan()` and `replay_extra_short_scan()` in `scanning/scan_replay.py` using the pure helper, the PIT membership/sector intervals from V118-1, and deterministic dedup/confirmation order. Extend `measure_arms.produce()` with a population-engine branch that loads each cached frame once, runs baseline with `enabled=False` and component with `enabled=True`, then calls its existing `build_stamp()` with the identical full universe/window/code hashes. Arm rows use `acceptance.arm_trade_from_plan()` and the current `ArmTrade` schema. A fixture with one added SHORT proves base rows are identical flag off/on; a second fixture where RS or confidence fails produces zero added rows. Classify the new knob `REACHABLE` in `arms/reachability.py` only after those tests pass; pin CLI refusal if the population engine is absent. If live-gate parity requires unbounded refactoring, classify it `LIVE_SCAN_ONLY`, commit the reachability finding and stop. A bespoke route would require a separate pre-registration and an explicit `--bespoke-instrument` reason.

Add research-only `SHORT_UNIVERSE_RESEARCH_MODE` (`off|broad|isolated`, default `off`) to the config schema; the standard producer applies it through `apply_knobs()` inside each worker. The first actual run is `python scripts/backtest/measure_arms.py --stage pilot --knob SHORT_UNIVERSE_RESEARCH_MODE=broad --preregistration docs/superpowers/results/2026-10-01-v118-short-universe-preregistration.md --out docs/superpowers/results/2026-10-01-v118-broad-pilot-arms.json` and separately `...=isolated`; invoke `backtest-gate` before each. Do not hand-author arm JSON or bypass `validate_component.py` stamp checks.

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

**Implementation detail.** Admit broad and isolated separately. Schema and `.env.example` provide `SHORT_UNIVERSE_ENABLED`, `SHORT_UNIVERSE_BROAD_ENABLED`, and `SHORT_UNIVERSE_ISOLATED_ENABLED`, all false. The runtime guard is pure and precedes every extra fetch and alert side effect:

```python
def admitted_short_modes(cfg) -> frozenset[str]:
    if not cfg.SHORT_UNIVERSE_ENABLED:
        return frozenset()
    return frozenset(mode for mode, allowed in (
        ("broad", cfg.SHORT_UNIVERSE_BROAD_ENABLED),
        ("isolated", cfg.SHORT_UNIVERSE_ISOLATED_ENABLED),
    ) if allowed)
```

The test helper `emit_modes()` in the earlier assertion invokes this guard against a fake config. After each serial stage, record separate arm rows by mode and the applicable acceptance clauses, with counts of added, unchanged, excluded and unmeasurable candidates. Derive any reported expectancy/win rate/N from the actual arm rows. A pass authorizes a reviewed default change in code; this plan gives no production deployment authorization. Commit the mode guard/test separately from the measured result record.

### Task V118-9: Full-suite verification

**Files:** No new feature files; fix only failures attributable to this plan and update their narrow tests.

- [ ] Run `python scripts/dev/testrun.py full` once (or use the `test-runner` role). Green requires `0 failed` and `0 xfailed`.
- [ ] If it fails, fix forward, run the named narrow file, then resolve the suite failure. Check changed functions with radon and review base LONG invariant, no-lookahead, and all four alert mirrors.
- [ ] Close the plan as implemented or no-lift by the repo's document lifecycle. Only an actual shipped observable alert gets the spec's bot patch bump, resolved from then-current `VERSION.json`; do not hard-code a release number here.
