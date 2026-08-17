# v31 — Structural target selection: every plan's TP1 becomes a real level at 1.5–2.5R

Version: ui 1.5.1 · bot 1.1.4
Bump: bot minor (1.1.4 → 1.2.0)

Built from `docs/superpowers/specs/2026-08-16-v31-structural-targets-design.md`.

## Stable baseline before implementation starts

`Version:` above is when this plan was **written** (`document-conventions.md`'s
rule: never refreshed afterwards). This is a separate, later mark: the last
known-good state before v31's own code changes begin, since a full release
cycle of unrelated UI/backend work shipped on `main` between authoring this
plan and starting on it.

**`ui 1.7.0 · bot 1.1.4`, commit `43387ce`.** If v31's implementation needs to
be rolled back, this is the commit to return to — everything from here up to
(not including) v31's first implementation commit is unrelated to this plan
and should be treated as part of the stable base, not as work to unwind.

`bot` minor by the `working-conventions.md` test — observable difference, not
diff size. Every number the bot posts in every alert changes, and the precedent
is exact: `bot 1.1.0` (`9b979be`) was earned by Plan Engine v2 because "how
trade plans are produced changed". This changes it again, in the same place.
`ui` bumps nothing: the admin renders whatever the plan says.

## The problem, stated once

`plan_engine` prices the stop against real structure and then prices the target
as `entry ± risk * rr`, where `rr` is 0.30–0.40 for nearly every strategy
(`strategy_types.STRATEGY_RR_OVERRIDE`, and `HORIZONS[*]["reward_risk_ratio"]`
behind it). Every posted plan therefore risks ~3x what it stands to make.
Observed live: AXON LONG 617.38 → TP 621.85 / SL 604.59 — reward 4.47 against
risk 12.79.

The real structure-based target already exists. `levels.build_scenarios` picks
it (`scenario.take_profit`), and `levels._check_constraints` already proves it
clears `MIN_RISK_REWARD_RATIO` (1.5) before the scenario is built at all. The
engine throws it away and keeps it only as `tp2`.

The fix is one shared selector: **the nearest real level beyond entry that sits
at least `MIN_RISK_REWARD_RATIO` out, capped at `MAX_RISK_REWARD_RATIO`; no
qualifying level means no plan.**

## Global constraints

1. **One global band, every strategy, every horizon (2w…9m).** No per-strategy
   table, no per-horizon table. That is the whole point — the per-strategy and
   per-horizon tables are what produced the inverted R:R and they are deleted
   here (Task 14).
2. **Nearest-qualifying wins, not farthest.** A closer target preserves win
   rate; the band's floor is what guarantees the payoff.
3. **Cap, don't skip.** A qualifying level beyond `max_rr` produces a synthetic
   target at exactly `entry ± risk * max_rr` — not a search further out, not a
   rejection.
4. **`None` means no setup.** No fallback to the old small-`rr` arithmetic
   anywhere. A builder that cannot find a target returns `None`, the plan is
   not built, and the caller drops the ticker/horizon.
5. **Ships as default, immediately.** No feature flag, no shadow mode, no dual
   path. `PLAN_ENGINE_V2` already exists and is not repurposed for this.
6. **Forward-only.** Nothing re-prices an open paper trade. `data/plans.json`
   and `data/trades.json` are untouched; there is no migration.
7. **Both plan paths or neither.** `apply_level_lifecycle`'s docstring records
   why: `DATA_DRIVEN_STOPS_ENABLED` scored exactly 0.0000 and burned its
   pre-registered shot because it reached `build_strategy_plan` while the
   backtest sized through `backtest._trade_plan_at`. Every builder change here
   lands in a shared function both paths call, and Task 12 pins that with a
   test.
8. **`quality.py` is out of scope.** No R:R-aware scoring component is added.

## What this deliberately does NOT change

- `levels._check_constraints`' `min_risk_reward` check stays exactly as it is.
  It becomes a **cheap non-authoritative prefilter** — it runs before clustering
  work is spent, and on the confluence path it happens to agree with the
  selector by construction (both read `MIN_RISK_REWARD_RATIO`, both measure
  against `resistances[0]`/`supports[0]`). The selector is the final gate.
- `MAX_TARGET2_LEG_MULTIPLE` (`levels.py:102`) keeps its current job — capping
  the **tp1 → tp2** leg, in `levels.build_scenarios` and `plan_engine.select_tp2`.
  It is **not** reused for the tp1 cap: that cap is `risk * MAX_RISK_REWARD_RATIO`,
  a config-driven risk multiple, not a leg-proportion heuristic. Two different
  quantities that happen to both be "don't go silly far"; merging them would
  couple a frozen chart-realism constant to a live risk setting. Recorded here
  so the next session does not go hunting for the merge.
- `select_tp2` itself is unchanged. Its contract ("first clustered level
  strictly beyond tp1") is already what decision 6 of the spec asks for.
- **`build_level_map` is not modified.** It already returns
  `(supports, resistances)` as ordered `Level` lists, nearest-first — its
  docstring at `levels.py:506` says so and the sorts at `:508-509` prove it. The
  "ordered candidate list" this work needs already exists; only *threading* it
  is new (Task 4). An early draft of this plan assumed otherwise; it was wrong.

## Parallelisation

- **Sequential: Task 1 → Task 2 → everything.** Task 1 fixes the candidate-source
  decision that Tasks 8–11 consume; Task 2 introduces `select_structural_target`,
  which Tasks 5, 8, 9, 10, 11 and 13 all call. Nothing may start before both land.
- **Group A (parallel), after Task 2:** Task 3 (`config.py` + `.env.example`) and
  Task 4 (`levels.py` helper). Disjoint files, no contract between them.
- **Group B (parallel), after Task 5:** Task 6 (`scanning/engine.py`) and
  Task 7 (`backtesting/backtest_scenarios.py`) — both after Task 5, which
  changes `build_confluence_plan`'s signature that both call.
- **Tasks 8, 9, 10, 11 are NOT parallel.** All four edit
  `swingbot/core/planning/plan_engine.py`, and this working tree is shared, so a
  second agent overwrites the first. Sequential 8 → 9 → 10 → 11.
- **Sequential tail:** 12 after 8–11 (propagates their `None`). 13 after 12
  (rollback needs the finished builders). 14 after 13 (deletes what 13 stopped
  using). 15 after 14. 16 after 15 (spot-check needs green). 17 → 18 → 19 → 20
  strictly in order — a validation shot before the TRAIN measurement is a burned
  budget, and the version bump goes last by `working-conventions.md`.
- Genuinely wide groups here are small because eight of twenty tasks edit
  `plan_engine.py`. Say so rather than pretending otherwise.

## Verification

While iterating: `python scripts/dev/testrun.py file tests/planning/test_structural_target.py`
(~7s). Per task, the named file(s). Before each commit:
`python scripts/dev/testrun.py fast` (~27s). The gate before the phase closes:
`python scripts/dev/testrun.py full` — reference baseline `1686 passed,
66 skipped, 0 failed`. **Green means `0 failed` AND `0 xfailed`.** A changed
pass count is expected here (Task 15 retires tests); a `failed` or an `xfailed`
is not. Prefer dispatching the `test-runner` subagent for `full` so ~1150
progress lines stay out of context.

## Progress

- [x] Phase 1 — Ground truth and the selector (Tasks 1-2, commits c0a275c, 7c4e119)
- [x] Phase 2 — Config and the confluence (live-alert) path (Tasks 3-7, commits 2f34f9a..d49322b)
- [x] Phase 3 — The four strategy builders (Tasks 8-11, commits 71704ea..4eddeaa)
- [x] Phase 4 — Lifecycle, dead code, and the parity harness (Tasks 12-15, commits 6340a72..d561153)
- [ ] Phase 5 — Prove it, then ship it (Task 16 done below; Tasks 17-18 need
      explicit go-ahead before running -- Task 18 is a one-shot, irreversible
      VALIDATION run per this plan's own methodology)

### Task 16: Manual spot-check on real tickers, including AXON

Live-data spot check, 2026-08-17. Not a committed script (per the task's own
instruction) -- run via scratch REPL calls to the real pricing path
(`levels.build_level_map` -> `levels.build_scenarios` ->
`plan_engine.build_confluence_plan(level_map=...)` for the confluence path,
`plan_engine.build_strategy_plan` for the strategy path), against real
`get_daily_data` fetches, no synthetic data.

**Confluence path, real priced plans found (horizon 4w, full 76-ticker
watchlist scanned):**

```
CRWV: Entry 105.26 / TP1 99.63 / TP2 98.37 / SL 107.51 -> R:R = 2.500  [OK]
WDC:  Entry 508.80 / TP1 531.84 / TP2 548.56 / SL 494.19 -> R:R = 1.577  [OK]
```

Both land inside [1.5, 2.5] as required. Zero out of band.

**Strategy path, `!ticker`-equivalent (`build_strategy_plan` over every
triggered strategy/horizon):** AXON itself has **zero triggered strategy
signals today** (a real, independent market fact, confirmed via
`evaluate_all("AXON", df)` returning 110 combos evaluated / 0 triggered) --
so there is nothing for `!ticker AXON` to price right now regardless of this
plan. Across the full watchlist, exactly one ticker had a triggered signal
today:

```
V: VWAP/4w (bullish): Entry 364.15 / TP1 385.60 / SL 349.85 -> R:R = 1.500  [OK]
```

**The AXON failure that started this plan, eyeballed directly:** real AXON
has no live signal today to run end-to-end, so the direct proof is
`tests/planning/test_structural_target.py::test_the_axon_case` (entry
617.38, stop 604.59 -- the exact numbers from the original bad alert):
`select_structural_target` now returns **640.0** (1.77R; the old alert's
621.85 is only 0.35R and is correctly rejected as failing to clear
`MIN_RISK_REWARD_RATIO`). The shape that started this plan cannot recur.

**Point 3 (a ticker with no plan, reported via `filtered_by_rr`, not
posted):** the mechanism is unit-tested and passing
(`test_a_plan_that_cannot_clear_min_rr_never_reaches_scan_items`,
`test_returns_none_when_no_level_clears_min_rr`,
`test_shadow_mode_keeps_the_legacy_alert_when_v2_rejects` -- Tasks 5-6). Live
confirmation is more nuanced than "find one": scanning the full 76-ticker
watchlist at both 4w and 2w horizons found **74-76 of 76 tickers producing no
scenario at all** (levels.build_scenarios' own hard filter -- real market
conditions, unrelated to this plan: mostly the pre-existing
`min_stop_distance_pct` gate, e.g. AXON's nearest support sits 1.37% away
against a 2.0% floor) but **zero live cases of a scenario building and then
`build_confluence_plan` rejecting it** (`filtered_by_rr` specifically).
This is the expected shape, not a gap: Task 5's own note observes that
`levels._check_constraints` already requires `rr >= MIN_RISK_REWARD_RATIO`
against `resistances[0]` (the nearest candidate) before a scenario is ever
built, so the prefilter and the selector agree by construction for the
common case -- a live `filtered_by_rr` divergence needs a specific shape
(the nearest candidate clears the OLD, looser scenario-building check by a
sliver while the selector's own epsilon/cap logic disagrees), which is real
but not common. The counter and the drop-before-`scan_items` behavior are
proven correct by the unit tests; today's watchlist simply didn't produce a
live specimen at either horizon checked.

**Verdict:** every priced plan found (3 of 3, across both the confluence and
strategy paths) landed inside [1.5, 2.5]. None below 1.5, none above 2.5.

---

# Phase 1 — Ground truth and the selector

### Task 1: Confirm the candidate-level source for each of the six call sites

**No production code changes.** This task exists because Tasks 8–11 each need a
different answer and getting one wrong is a silent mis-pricing rather than a
crash.

Read and record, in a comment block added at the top of the "sizing builders"
section of `swingbot/core/planning/plan_engine.py`, what each builder can
legitimately offer as target candidates:

1. **`build_confluence_plan`** (`plan_engine.py:654`) — candidates come from the
   unified map. Confirm what is already established and do not re-derive it:
   `levels.build_level_map` (`levels.py:505`) already returns
   `(supports, resistances)` as **ordered `Level` lists, nearest-first**
   (`supports` sorted by `-price`, `resistances` by `price`). So the ordered
   candidate list **already exists** — it is `[lv.price for lv in resistances]`
   (bullish) or `[lv.price for lv in supports]` (bearish). No change to
   `build_level_map` or `build_scenarios` is needed; only threading (Task 4).
   Confirm both holders of that map: `engine.ScanItem.level_map`
   (`scanning/engine.py:173`, staged in `_scan_one`, consumed at
   `engine.py:1248`) and `backtest_scenarios.py:82-88`, which re-splits an
   as-of map against the current bar's price.
2. **`_fibonacci_plan`** (`plan_engine.py:314`) — receives only
   `swing_high`/`swing_low`. Its native ladder is
   `indicators.fibonacci_levels(df, h["fib_lookback"])`: `swing_high`,
   `swing_low`, and retracements at 0.236/0.382/0.5/0.618/0.786 measured down
   from the swing high. Confirm there are no extension ratios in that function
   (there are not — `indicators.py:39-59`) and decide whether the plan adds
   1.272/1.618 extensions of the same swing as targets beyond `swing_high`.
   **Recommendation: yes, add them** — otherwise a bullish fib plan entering
   near the swing high has at most one candidate and returns `None` constantly.
3. **`_elliott_plan`** (`plan_engine.py:366`) — receives only `wave2`.
   `indicators.elliott_wave3_entries` already hands every caller
   `{"wave0", "wave1", "wave2", "wave0_idx", "wave1_idx", "wave2_idx"}`
   (`indicators.py:235-239`) and its docstring explicitly says callers may use
   these "without recomputing pivots themselves". Native wave-3 targets are the
   classic projections off wave 2: `wave2 ± k * |wave1 - wave0|` for
   `k ∈ (1.0, 1.618, 2.618)`, plus `wave1` itself. Confirm the sign convention
   for the bearish branch (`kind0 == "high"`, `p2 < p0`).
4. **`_sr_plan`** (`plan_engine.py:342`) — takes **no `df` at all**; its target
   today is a pure percentage band interpolated by volume strength
   (`h["sr_target_min_pct"] … h["sr_target_max_pct"]`). It has **no native
   levels**. Its natural ones are the structure the strategy actually trades:
   `df["High"].rolling(h["sr_lookback"]).max().shift(1)` and the matching
   rolling low, plus the existing percentage band prices as a floor so the
   candidate list is never empty.
5. **`_atr_plan`** (`plan_engine.py:170`) — the fallback for **8 of 11
   strategies** (EMA Crossover, VWAP, RSI, MACD, MA Ribbon, Break & Retest,
   RSI Divergence, Volume Profile). It has no price structure of any kind; its
   only native scale is volatility.
   **This is the one open decision in this plan.** Options:
   (a) an ATR ladder — `entry ± k * atr_val` for `k ∈ (1,2,3,4,5,6,8,10)`;
   (b) borrow the unified map (rejected by the spec's per-strategy decision);
   (c) return `None` for all eight strategies (rejected — it empties
   `!ticker`, empties the backtest for those strategies, and therefore empties
   the badge registry that `stamp_badge` reads).
   **Recommendation: (a).** With `atr_stop_multiple = 2.0` the risk is 2 ATR,
   so `min_rr = 1.5` puts the floor at 3 ATR and `max_rr = 2.5` at 5 ATR — the
   ladder brackets the whole band, the nearest-qualifying rule lands on 3 ATR,
   and the answer is deterministic and honest ("this strategy's structure is
   volatility"). Record the decision explicitly in the comment block.
6. **`apply_level_lifecycle`** (`plan_engine.py:233`) — already builds or
   receives a classified level list via `_lifecycle_levels`, which returns
   `levels_lifecycle.LevelState` objects carrying `.price`. Confirm those are
   usable as selector candidates directly (they are — Task 13 uses `.price`),
   and confirm `preferred_stop_anchor` / `gatekeepers_between` signatures at
   `levels_lifecycle.py:184` and `:197`.

**Done when:** the comment block exists in `plan_engine.py`, names a decided
candidate source for each of the six sites, and the `_atr_plan` decision is
stated with its reason. `python scripts/dev/testrun.py fast` still green
(comment-only change).

---

### Task 2: `select_structural_target()` with unit tests

TDD — write `tests/planning/test_structural_target.py` first.

Add to `swingbot/core/planning/plan_engine.py`, immediately above the
"Sizing builders" section:

```python
def select_structural_target(entry: float, stop_loss: float, is_bull: bool,
                             candidate_levels, min_rr: float,
                             max_rr: float) -> float | None:
    """THE target price for every plan this engine builds.

    Nearest real level beyond `entry` that pays at least `min_rr` times the
    plan's own risk, capped at `max_rr`. Returns None when no candidate
    clears the floor -- which means "there is no trade here", not "fall back
    to something smaller". There is deliberately no fallback: pricing a
    target off a fixed fraction of risk is exactly the arithmetic that made
    every posted plan risk 3x what it stood to make (plan v31).

    NEAREST-qualifying, not farthest: the floor already guarantees the
    payoff, and a closer target is reached more often. Beyond `max_rr` the
    result is a SYNTHETIC price at exactly `entry +/- risk * max_rr` -- not
    the level, not None. That level is still a real level, and select_tp2
    will pick it up as tp2 (the cap declines it as tp1, it does not delete
    it).

    `candidate_levels` is an iterable of plain prices; each caller supplies
    ITS OWN source (unified level map for the confluence path, the
    strategy's own native levels for the strategy builders -- see the
    sizing-builders comment block above). Nothing is looked up in here, for
    the same reason `_atr_plan` takes an injected `stop_mult`: this function
    is shared by the live path and the backtest, and a hidden lookup would
    price 2020 backtest bars off today's live data.
    """
    risk = abs(entry - stop_loss)
    if risk <= 0 or min_rr <= 0:
        return None
    if max_rr < min_rr:
        raise ValueError(f"max_rr {max_rr} < min_rr {min_rr}")

    # Relative epsilon: a level sitting EXACTLY at the floor must qualify,
    # and float arithmetic on a $600 stock does not land exactly.
    eps = 1e-9 * max(1.0, abs(entry))
    floor_dist, cap_dist = risk * min_rr, risk * max_rr

    beyond = [float(p) for p in candidate_levels
              if p and (p > entry if is_bull else p < entry)]
    qualifying = [p for p in beyond if abs(p - entry) >= floor_dist - eps]
    if not qualifying:
        return None

    nearest = min(qualifying, key=lambda p: abs(p - entry))
    if abs(nearest - entry) > cap_dist + eps:
        return entry + cap_dist if is_bull else entry - cap_dist
    return nearest
```

Tests to write (all pure, no fixtures, no data cache):

- `test_picks_nearest_qualifying_not_farthest` — entry 100, stop 96 (risk 4),
  min 1.5/max 2.5 → band [106, 110]; candidates `[102, 107, 109]` → **107**.
- `test_skips_candidates_under_the_floor` — same, candidates `[101, 102, 103]`
  → `None`.
- `test_caps_instead_of_skipping_or_searching_on` — candidates `[130]` → exactly
  `110.0`, and assert it is **not** 130 and **not** `None`.
- `test_a_level_exactly_at_the_floor_qualifies` — candidate `[106.0]` → `106.0`.
  Repeat with entry 617.38 / stop 604.59 (the AXON risk) to prove the epsilon
  holds at real prices.
- `test_bearish_mirrors_exactly` — entry 100, stop 104, `is_bull=False`,
  candidates `[98, 93, 91]` → **94.0** (cap), and `[98, 93]` → 93.
- `test_candidates_on_the_wrong_side_of_entry_are_ignored` — bullish with
  candidates `[80, 70]` → `None`.
- `test_zero_or_inverted_risk_returns_none` — `stop_loss == entry`.
- `test_max_below_min_raises` — `pytest.raises(ValueError)`.
- `test_no_candidates_at_all_returns_none` — empty list, and `None`-ish entries
  filtered.
- `test_the_axon_case` — entry 617.38, stop 604.59, candidates
  `[621.85, 640.0, 700.0]` with min 1.5/max 2.5 → **640.0** (621.85 is only
  0.35R and is correctly rejected; 640 is 1.77R). This is the regression that
  names the bug.

**Done when:** `python scripts/dev/testrun.py file tests/planning/test_structural_target.py`
reports 10 passed, 0 failed. Nothing else in the codebase calls the function yet.

---

# Phase 2 — Config and the confluence (live-alert) path

### Task 3: Add `MAX_RISK_REWARD_RATIO`

`swingbot/config.py` — one `Field`, immediately after the existing
`MIN_RISK_REWARD_RATIO` entry (currently `config.py:147-150`; **verify the line
number before editing**, it moves). Match that entry's shape exactly — same
section, same `type="float"`, same `min`/`step` convention:

```python
    Field("MAX_RISK_REWARD_RATIO", "MAX_RISK_REWARD_RATIO", "Trade Filters & Risk",
          "Max reward:risk ratio",
          type="float", default="2.5", min=0, step=0.1,
          help="The ceiling on how far a target may sit, as a multiple of the plan's own risk. "
               "A real level further out than this does not disqualify the setup -- the target "
               "is simply placed AT the ceiling instead, and that further level becomes TP2. "
               "Together with 'Min reward:risk ratio' this is the band every trade plan's "
               "target is chosen inside, for every strategy and every horizon."),
```

`MIN_RISK_REWARD_RATIO` keeps its `1.5` default and its help text unchanged.

`.env.example` — add `MAX_RISK_REWARD_RATIO=2.5` next to the existing
`MIN_RISK_REWARD_RATIO=1.5` (line 77). This is not optional:
`tests/test_env_example_sync.py` asserts both directions of that mapping and
will fail without it.

**Done when:** `python scripts/dev/testrun.py file tests/test_env_example_sync.py`
green, and `python -c "from swingbot import config; print(config.MAX_RISK_REWARD_RATIO)"`
prints `2.5`. The admin Settings page picks it up with no further work (one
`Field` feeds both parser and UI).

---

### Task 4: `levels.target_candidates()` — one place that picks the right side of the map

Three call sites need "the ordered price list beyond entry, on the trade's
side" and would otherwise each re-derive the resistances/supports pick. Add to
`swingbot/core/market/levels.py`, directly under `build_level_map`:

```python
def target_candidates(supports: list, resistances: list, direction: str) -> list:
    """Ordered candidate TARGET prices for a plan, nearest to entry first.

    Just the trade-direction side of a build_level_map() pair, unwrapped to
    plain prices -- bullish plans target resistance, bearish plans target
    support. Both lists arrive nearest-first from build_level_map, and that
    order IS the selection order plan_engine.select_structural_target walks,
    so this must not re-sort.
    """
    side = resistances if direction == "bullish" else supports
    return [float(lv.price) for lv in side]
```

Test in `tests/market/test_levels_scenarios.py` (the module that already owns
`build_scenarios`/target-2 behaviour):

- `test_target_candidates_returns_the_direction_side_nearest_first` — build a
  map from a synthetic frame, assert bullish returns strictly increasing prices
  all above `current_price`, bearish strictly decreasing all below.
- `test_target_candidates_preserves_build_level_map_order` — assert the returned
  list equals `[lv.price for lv in resistances]` element-for-element (guards
  against someone adding a `sorted()`).

**Done when:** `python scripts/dev/testrun.py file tests/market/test_levels_scenarios.py`
green.

---

### Task 5: `build_confluence_plan` selects a structural TP1 and may return `None`

`swingbot/core/planning/plan_engine.py:654`. Replace the
`rr = STRATEGY_RR_OVERRIDE.get(primary_strategy, 0.35)` block:

```python
def build_confluence_plan(scenario, df, *, ticker, horizon_key,
                          primary_strategy, level_map=None,
                          quality_inputs=None) -> TradePlanV2 | None:
```

- Return type becomes `TradePlanV2 | None` — update the docstring's "TP1 is
  RECOMPUTED under the unified exit policy" paragraph, which describes the
  behaviour being deleted.
- `candidates = levels.target_candidates(*level_map, scenario.direction)` when
  `level_map` is not None. When it is `None`, fall back to
  `[scenario.take_profit]` filtered for `not None` — the scenario's own target
  is a real level and is the minimum honest candidate set. Do **not** invent a
  synthetic candidate.
- `tp1 = select_structural_target(entry, scenario.stop_loss, is_bull, candidates,
  config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)`.
- `if tp1 is None: return None` — before any `TradePlanV2` construction, before
  `uuid4()`, before `stamp_badge`.
- tp2: replace the old `scenario.take_profit if beyond tp1` block with
  `select_tp2(resistances_prices, supports_prices, direction, entry, tp1)` when
  `level_map` is present, else the existing `scenario.take_profit`-if-beyond
  rule. This makes Task 6's post-hoc tp2 patch in `attach_plan_v2` redundant
  (Task 6 removes it).

**Note for the executing session, so it is not mistaken for a bug:** on this
path the selector will usually return `scenario.take_profit` unchanged.
`levels._check_constraints` already required `rr >= MIN_RISK_REWARD_RATIO`
against `resistances[0]`, and `resistances[0]` is the nearest candidate — so
the prefilter and the selector agree by construction, and the visible change is
that the scenario's real target finally *is* TP1 instead of being demoted to
tp2. The `None` branch and the cap branch are the two places they diverge; both
are real and both need tests.

Rewrite `tests/planning/test_build_confluence_plan.py` (currently 8 tests, all
asserting the `STRATEGY_RR_OVERRIDE`/0.35 arithmetic — that arithmetic is gone,
so the module is rewritten, not patched). New tests:

- `test_tp1_is_the_scenarios_own_target_when_it_sits_in_the_band` — the AXON
  shape: entry 100, stop 96, `take_profit` 108 (2.0R) → `plan.tp1 == 108`.
- `test_tp1_is_capped_when_the_nearest_level_is_beyond_max_rr` — `take_profit`
  130 → `plan.tp1 == 110.0` and `plan.tp2 == 130.0` (the declined level becomes
  the stretch target — this is the pairing that proves "cap, don't skip").
- `test_returns_none_when_no_level_clears_min_rr` — level map with only
  `[101, 102]` above entry → `build_confluence_plan(...) is None`.
- `test_returns_none_builds_no_plan_id_and_stamps_no_badge` — patch
  `stamp_badge` with a mock, assert not called (proves the early return is
  before construction, not after).
- `test_reward_always_at_least_min_times_risk` — parametrised over ~6 scenario
  shapes, assert `abs(plan.tp1 - entry) >= abs(entry - plan.stop_loss) * 1.5 - 1e-9`
  for every plan returned. **This is the assertion that names the bug** and
  should read as such.
- `test_reward_never_exceeds_max_times_risk` — the mirror.
- Keep the existing `scenario_is_breakout` and entry-type tests unchanged; they
  do not touch pricing.

**Done when:** `python scripts/dev/testrun.py file tests/planning/test_build_confluence_plan.py`
green, and `git grep -n "STRATEGY_RR_OVERRIDE" swingbot/core/planning/plan_engine.py`
no longer matches inside `build_confluence_plan`.

---

### Task 6: `attach_plan_v2` and the scan loop drop a ticker with no qualifying target

`swingbot/core/scanning/engine.py:516` — `attach_plan_v2`:

- Pass `level_map=level_map` into `build_confluence_plan` (it is already a
  parameter of `attach_plan_v2` and already threaded from `item.level_map`).
- **Delete** the `if plan.tp2 is None and level_map is not None:` post-hoc tp2
  patch (lines ~537-539) — Task 5 does this inside the builder now, from the
  same map, so leaving it would be a second, divergent tp2 rule.
- `plan` may now be `None`. Distinguish the three outcomes explicitly, because
  the scan loop must treat them differently:

```python
        if plan is None:
            # No level beyond entry pays MIN_RISK_REWARD_RATIO against this
            # scenario's own risk. That is a real answer -- "no trade here" --
            # not a failure, so it is recorded rather than logged as a warning,
            # and _sync_run_scan drops the item instead of falling through to
            # the legacy scenario numbers (which is what plan_numbers_for_display
            # does for plan=None, and would silently re-post the very prices
            # this change exists to stop posting).
            item.plan_v2_rejected = "no_qualifying_target"
            return
        item.plan_v2 = plan
```

Add `plan_v2_rejected: str | None = None` to the `ScanItem` dataclass
(`engine.py:172`, next to `plan_v2`).

`_sync_run_scan`, the merge loop at `engine.py:1241-1255`: after the
`attach_plan_v2(...)` call and its `regime_aligned` block, add

```python
                if (config.PLAN_ENGINE_V2 == "on"
                        and getattr(item, "plan_v2_rejected", None)):
                    filtered_by_rr += 1
                    log.debug("%s (%s, %s): no level clears %.1f:1 reward:risk -- skipped",
                              item.result.ticker, item.result.horizon_key,
                              item.result.trend, config.MIN_RISK_REWARD_RATIO)
                    continue          # never reaches scan_items -> never alerts
```

before `scan_items.append(item)`. Declare `filtered_by_rr = 0` beside
`filtered_by_confirmation` and include it in the same scan-summary log line
that reports the other filter counts — a silent drop is exactly the failure
mode `known-traps.md` warns about.

The `config.PLAN_ENGINE_V2 == "on"` guard matters: in `"shadow"` mode
`plan_v2` is built but is not the priced plan (`engine.py:1453`, `1480`), so a
shadow rejection must not suppress a legacy alert.

Tests in `tests/scanning/test_engine_v2_plans.py` (which already monkeypatches
`engine.build_confluence_plan` at line 107, so the seam exists):

- `test_a_plan_that_cannot_clear_min_rr_never_reaches_scan_items` — patch the
  builder to return `None`, assert the item is absent from the returned items
  and that no alert tuple is produced.
- `test_shadow_mode_keeps_the_legacy_alert_when_v2_rejects` — same patch with
  `PLAN_ENGINE_V2 = "shadow"`, assert the item survives.
- `test_attach_plan_v2_records_the_rejection_reason` — assert
  `item.plan_v2_rejected == "no_qualifying_target"` and `item.plan_v2 is None`.
- `test_a_builder_exception_is_still_a_warning_not_a_rejection` — patch to
  raise, assert `plan_v2_rejected` stays `None` (a crash must not masquerade as
  a clean "no setup"; that distinction is the whole reason for the flag).

**Done when:** `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
green, and `python scripts/dev/testrun.py fast` green.

---

### Task 7: The confluence backtest supplies the same level map

`swingbot/core/backtesting/backtest_scenarios.py:110`. This module already has
`supports`/`resistances` in scope, re-split against the current bar's price at
lines 86-88 — it just never passes them:

```python
            plan = build_confluence_plan(
                sc, window, ticker=ticker, horizon_key=horizon_key,
                primary_strategy=primary_strategy_for(sc),
                level_map=(supports, resistances))
            if plan is None:
                continue          # no qualifying target -> no trade, same as live
            last_accepted[sc.direction] = i
            out.append((i, plan))
```

Note the ordering: `last_accepted[sc.direction] = i` must move **below** the
`None` check, or a rejected scenario would start the cooldown for a trade that
never happened.

**Done when:** `python scripts/dev/testrun.py file tests/backtesting/` green,
and a one-ticker smoke run
(`python scripts/backtest/run_backtest_range.py --from 2022-01-01 --to 2022-06-30 --strategy "RSI"`)
completes without an exception. Its *numbers* are not judged here — that is
Task 17.

---

# Phase 3 — The four strategy builders

All four edit `plan_engine.py`. **Strictly sequential (8 → 9 → 10 → 11).**

Each follows the same shape, and the shape is deliberate: the candidate list is
**injected**, never looked up inside the builder. That mirrors the existing
`stop_mult` contract and its docstring warning — these builders are shared by
`build_strategy_plan` (live) and `backtest._trade_plan_at` (historical), and a
lookup inside one would price 2020 bars off today's data.

Each builder also gains a paired `*_target_candidates(...)` module function that
**both callers** invoke, so the two paths cannot drift (Global constraint 7).

### Task 8: `_fibonacci_plan`

```python
def fib_target_candidates(df, index, h, entry) -> list[float]:
    """The Fibonacci strategy's OWN levels on the target side: the swing
    high/low that anchors the retracement, the 0.236/0.382/0.5/0.618/0.786
    retracements themselves, and the 1.272/1.618 extensions of the same
    swing. NOT the unified multi-method level map -- a Fibonacci plan
    targets Fibonacci structure (plan v31)."""
```

Built from `indicators.fibonacci_levels(df.iloc[:index + 1], h["fib_lookback"])`
— note the slice: `df` runs to the end of history in the backtest, and
`fibonacci_levels` takes `df.iloc[-lookback:]`, so an unsliced call is
lookahead. This is the same trap `_lifecycle_levels` documents at
`plan_engine.py:210-230`; copy that reasoning into the docstring.

`_fibonacci_plan(entry, atr_val, swing_high, swing_low, direction, horizon_key,
candidate_levels)` → returns `tuple | None`. Keep the stop derivation
(swing ± buffer, `max_risk_pct` cap) **byte-for-byte**; replace only the target
block — both the `STRATEGY_RR_OVERRIDE` branch and the
`min_structure_rr`/`max_structure_rr` branch — with one
`select_structural_target(...)` call, returning `None` when it does.

**Done when:** `tests/planning/test_plan_engine_sizing.py`'s fib cases assert
`tp` is either `None` or within `[1.5R, 2.5R]`, and a new
`test_fibonacci_targets_only_fibonacci_levels` asserts the returned tp is a
member of `fib_target_candidates(...)` **or** exactly the 2.5R cap.

### Task 9: `_elliott_plan`

`elliott_target_candidates(entry_level: dict, direction) -> list[float]` from
the `{"wave0","wave1","wave2"}` the caller already holds:
`wave1`, and `wave2 ± k * abs(wave1 - wave0)` for `k ∈ (1.0, 1.618, 2.618)`,
sign by direction. No `df` needed — `elliott_wave3_entries` already published
these precisely so callers need not recompute pivots
(`indicators.py:236-239`).

`_elliott_plan(entry, atr_val, wave2, direction, horizon_key, candidate_levels)`
→ `tuple | None`. Stop (wave2 ∓ buffer, risk-capped) unchanged.

**Done when:** a new `test_elliott_targets_wave_projections` asserts the tp is a
wave projection or the cap, and the bearish mirror is covered.

### Task 10: `_sr_plan`

`_sr_plan` currently takes no `df`. Add
`sr_target_candidates(df, index, h, entry, volume_ratio) -> list[float]`:
the rolling structural high/low
(`df["High"].rolling(h["sr_lookback"]).max().shift(1).iloc[index]` and the low
mirror — `.shift(1)` matching `collect_candidate_levels`' convention at
`levels.py:227-228`), plus the existing volume-strength band prices
`entry * (1 ± target_pct/100)` at both the `sr_target_min_pct` and
`sr_target_max_pct` ends. The band prices keep the list non-empty on a ticker
whose rolling structure sits the wrong side of entry.

`_sr_plan(entry, volume_ratio, direction, horizon_key, candidate_levels)` →
`tuple | None`. Stop (`h["sr_stop_pct"]` fixed percentage) unchanged.

**Done when:** a new `test_sr_target_is_structure_or_band_never_a_risk_multiple`
asserts membership-or-cap, and the existing S/R sizing tests are updated to the
new band.

### Task 11: `_atr_plan`

Per Task 1's recorded decision (recommendation: the ATR ladder):

```python
ATR_TARGET_LADDER = (1, 2, 3, 4, 5, 6, 8, 10)

def atr_target_candidates(entry, atr_val, direction) -> list[float]:
    """Volatility IS the structure for the eight strategies that size
    through _atr_plan (EMA Crossover, VWAP, RSI, MACD, MA Ribbon,
    Break & Retest, RSI Divergence, Volume Profile). None of them produces
    a price level of its own, and borrowing the unified level map here was
    rejected (plan v31) -- a MACD plan targeting a Fibonacci level is not a
    MACD plan. So the candidates are this ticker's own ATR bands. At the
    horizon default (atr_stop_multiple 2.0) risk is 2 ATR, which puts the
    1.5R floor at 3 ATR and the 2.5R cap at 5 ATR: the ladder brackets the
    whole band and the nearest-qualifying rule lands on 3 ATR."""
```

`_atr_plan(entry, atr_val, direction, horizon_key, strategy, stop_mult=None,
candidate_levels=None)` → `tuple | None`. Keep the whole `risk_distance` /
`stop_mult` / `max_risk_amount` block **exactly** as it is — including the
comment explaining why scaling `risk_distance` rather than the stop price is
correct, with its "the R:R table plus the 0.30 floor are frozen constants"
sentence rewritten (that table is deleted in Task 14; the sentence would
become a lie).

**Done when:** `test_atr_plan_target_is_an_atr_band_at_or_past_the_floor` passes
for all eight `_atr_plan` strategies × 3 horizons, and every returned plan
satisfies `1.5 <= reward/risk <= 2.5`.

---

### Task 12: Propagate `None` through both plan paths

`build_strategy_plan` (`plan_engine.py:493`):
- Each branch calls its `*_target_candidates(...)` and threads the result.
- After each `stop, tp1 = ...`, handle the `None` return: `if result is None:
  return None`. Keep it above the existing `if abs(close - stop) <= 0: return
  None` guard so both no-setup reasons exit the same way.
- The Elliott branch needs `entry_levels[index]` for its candidates — it
  already has it.

`backtest._trade_plan_at` (`swingbot/core/backtesting/backtest.py:126`):
- Same threading. Return `None` instead of the `(entry, stop, tp)` tuple when a
  builder declines. Update the docstring, which currently claims parity with
  the pre-extraction implementation is locked by `test_plan_engine_sizing.py` —
  it now claims something narrower (stop parity only; see Task 15).
- `run_backtest`'s call site (`backtest.py:256`):
  ```python
        plan_at = _trade_plan_at(...)
        if plan_at is None:
            continue            # no qualifying target -> not a trade
        entry, stop_loss, take_profit = plan_at
  ```
  placed above the existing `risk_per_share <= 0` guard, which it parallels.

`swingbot/commands/info.py` — the `!ticker` command (lines 81-96) already skips
a `None` plan silently. Make the absence legible instead:

```python
    if plan_lines:
        lines.append("**Trade plans (v2)**")
        lines.extend(plan_lines)
    elif any(r.triggered for r in results):
        lines.append(
            f"**Trade plans (v2)** — no qualifying setup: no level beyond entry "
            f"pays {config.MIN_RISK_REWARD_RATIO:.1f}:1 against its own stop.")
```

Add `tests/market/test_levels_lifecycle_wiring.py::test_both_paths_agree_on_none`
— the module already asserts the two paths agree (line 76); extend it so that
when one returns `None` the other does too, on the same bar. That is the
Global-constraint-7 guard.

**Done when:** `python scripts/dev/testrun.py fast` green, and
`python scripts/backtest/run_backtest_range.py --from 2022-01-01 --to 2022-03-31 --strategy "MACD"`
completes and reports a **lower** trade count than on `main` (the drop is the
change working, not a bug).

---

# Phase 4 — Lifecycle, dead code, and the parity harness

### Task 13: `apply_level_lifecycle` re-runs the selector, or rolls the widening back

`plan_engine.py:233-311`. Signature gains `candidate_levels=None`.

The `targets_on` branch (lines 294-309) is **deleted entirely** — it is the
`LEVEL_LIFECYCLE_TARGETS_ENABLED` feature, measured inert (rejected 248/248),
and Task 14 removes its flag. With it goes the `targets_on` local and the
`if not (stops_on or targets_on)` fast-path check, which becomes
`if not stops_on`.

The `stops_on` branch's recompute (line ~289) changes from
`tp1 = entry + risk * rr` to:

```python
            if 0 < risk <= max_risk_amount and risk > abs(entry - stop):
                new_tp1 = select_structural_target(
                    entry, candidate, is_bull, candidate_levels or [],
                    config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
                if new_tp1 is None:
                    # ROLL BACK. Widening the stop is a refinement; the
                    # reward:risk guarantee is the contract. A wider stop with
                    # no target that pays for it is strictly worse than the
                    # tighter stop we already had, so keep the original pair
                    # untouched -- do NOT keep the wide stop with the old
                    # target, which is exactly the inverted-R:R plan this
                    # change exists to stop shipping.
                    meta["lifecycle_stop_rolled_back"] = {
                        "price": round(anchor.price, 4), "state": anchor.state}
                else:
                    stop, tp1 = candidate, new_tp1
                    meta["lifecycle_stop"] = {...}   # unchanged
```

Both callers (`build_strategy_plan:547`, `backtest._trade_plan_at:159`) pass
the same `candidate_levels` they passed to the builder. Update the function
docstring: the "Two independent, independently-flagged adjustments" paragraph
and the "the frozen R:R table is preserved exactly" claim are both now false.

Tests in `tests/market/test_levels_lifecycle_wiring.py` (11 tests today; several
assert the deleted targets branch):

- `test_widening_that_keeps_a_qualifying_target_is_applied` — assert the new tp
  is re-derived against the **new** risk, not carried over.
- `test_widening_with_no_qualifying_target_is_rolled_back_entirely` — assert
  **both** `stop` and `tp1` equal the pre-lifecycle values, and
  `meta["lifecycle_stop_rolled_back"]` is set. Assert specifically that the
  wide stop was **not** kept.
- `test_rr_holds_after_the_lifecycle_runs` — replaces the existing
  `assert rr >= plan_engine.RR_FLOOR` at line 219 with
  `assert config.MIN_RISK_REWARD_RATIO - 1e-9 <= rr <= config.MAX_RISK_REWARD_RATIO + 1e-9`.
- Delete the tests parametrised on `targets=True`.

**Done when:** `python scripts/dev/testrun.py file tests/market/test_levels_lifecycle_wiring.py`
green with the targets-branch tests gone.

---

### Task 14: Delete the dead R:R machinery

Six deletions, one commit. Every one is now unreferenced by the live path —
`git grep` each symbol after removing it and confirm zero hits outside
`docs/superpowers/{plans,specs}/implemented/` (historical documents keep their
text; they describe what was true then).

1. **`STRATEGY_RR_OVERRIDE`** — `strategy_types.py:209-229` (the dict and its
   header comment). Then its importers:
   `plan_engine.py:23`; `backtest.py:72` (a `# noqa: F401` re-export — and
   `tests/market/test_entry_filters.py:6-11` asserts that re-export is the same
   object and that every value is `>= 0.30`; that test module's first three
   assertions go with it); `admin/queries.py:42` and `:143` (the
   `"rr_override": ...` key in the strategy-table row — remove the key, and
   check `frontend/` for a column binding on it before assuming the SPA
   tolerates its absence).
2. **`HORIZONS[*]["reward_risk_ratio"]`** — `strategy_types.py`, one key inside
   each of the ten horizon dicts (lines 45, 62, 79, 96, 113, 130, 147, 164,
   181, 198). **Only that key** — every other field in those dicts stays.
3. **`HORIZONS[*]["min_structure_rr"]` / `["max_structure_rr"]`** — the same
   ten dicts. Not named in the original brief, but they are collateral: their
   only live reader was `_fibonacci_plan`'s `else` branch, which Task 8
   deleted. (That branch was already unreachable, because `"Fibonacci"` was
   always present in `STRATEGY_RR_OVERRIDE`.) Leaving them is a table that
   looks live and is not — precisely the "empty tables that are measured
   answers rather than stubs" trap `known-traps.md` warns about, in reverse.
4. **`RR_FLOOR` and `_rr_for`** — `plan_engine.py:31` and `:164-167`. `_rr_for`
   has no callers left after Tasks 8-13. `RR_FLOOR` is referenced by
   `tests/edge/test_edge_stops.py:384` (a ceiling calculation) — rewrite that
   test against `config.MAX_RISK_REWARD_RATIO`, or delete it if it no longer
   states a true fact.
5. **`LEVEL_LIFECYCLE_TARGETS_ENABLED`** — `config.py:579-589` (the `Field`),
   `.env.example:348`, the `getattr(config, ...)` read at `plan_engine.py:257`
   (Task 13 removed the branch; remove the read), the monkeypatches in
   `tests/backtesting/test_sizing_parity.py:97` and
   `tests/planning/test_plan_engine_sizing.py`, the force-off in
   `scripts/reports/parity_sizing.py:92`, and the `INERT_COMPONENTS` entry in
   `scripts/backtest/wf_components.py:77-88`. Removing the `.env.example` line
   is mandatory — `tests/test_env_example_sync.py` fails both ways.
6. **`levels_lifecycle.gatekeepers_between`** — `levels_lifecycle.py:184-196`,
   plus its two tests at `tests/market/test_levels_lifecycle.py:195` and `:209`.
   Its only production caller was the deleted targets branch. (If a reviewer
   prefers keeping a pure tested utility, that is defensible — but say so in the
   commit rather than leaving it silently orphaned.)

**Done when:** `git grep -n "STRATEGY_RR_OVERRIDE\|reward_risk_ratio\|min_structure_rr\|max_structure_rr\|RR_FLOOR\|LEVEL_LIFECYCLE_TARGETS_ENABLED" -- swingbot/ scripts/ tests/ frontend/`
returns nothing, `make check` (or
`python -m py_compile bot.py admin_ui.py swingbot/**/*.py` on Windows) passes,
and `python scripts/dev/testrun.py full` is green.

---

### Task 15: Retire the tp1 half of the sizing-parity harness

`tests/backtesting/test_sizing_parity.py` compares the current
`backtest._trade_plan_at` against `tests/fixtures/legacy_trade_plan_at.py`, a
**deliberately frozen** pre-extraction copy. Its stated purpose is to prove the
earlier extraction did not change sizing.

The frozen copy prices targets off `STRATEGY_RR_OVERRIDE` and
`reward_risk_ratio`. **It must not be taught the new selector** — that is
exactly what makes it an independent witness, and the module's own docstring at
lines 75-94 says so about the lifecycle flags. So the harness now asserts a
narrower, still-true property:

- Keep the **stop** assertion (line 134). Stop derivation is genuinely
  unchanged by this plan and the witness still proves it.
- Delete the **tp1** assertion (line 138) and replace it with a comment stating
  that TP1 diverges **by design** as of plan v31, naming this plan, so the next
  session does not read the gap as a regression and "fix" it.
- Handle the new `None` return: `if new_plan is None: continue` with a counter,
  and assert at the end that the `None` count is reported in the skip message —
  a harness that silently checks zero bars is worse than a failing one.
- Update the module docstring's opening paragraph accordingly.
- Apply the identical change to `scripts/reports/parity_sizing.py` (the
  full-corpus version), whose docstring at lines 24-30 already carries a
  "KNOWN EXCEPTION" paragraph about the `RR_FLOOR` clamp — that paragraph now
  describes a constant that no longer exists and must be rewritten.

Leave `tests/fixtures/legacy_trade_plan_at.py` **completely untouched**.

**Done when:** `python scripts/dev/testrun.py file tests/backtesting/test_sizing_parity.py`
green (or cleanly skipped if `data/backtest_cache/` is absent), and
`git diff --stat tests/fixtures/legacy_trade_plan_at.py` is empty.

---

# Phase 5 — Prove it, then ship it

### Task 16: Manual spot-check on real tickers, including AXON

The suite proves the arithmetic. This proves the posted message.

1. A `python -c` harness (or a scratch REPL — **do not commit a script for
   this**) that, for AXON plus four watchlist names, calls the scan path
   end-to-end: `marketdata` fetch → `levels.build_level_map` →
   `levels.build_scenarios` → `plan_engine.build_confluence_plan(level_map=...)`
   → `embeds.plan_numbers_for_display` → `embeds.build_simple_alert`.
   Print the literal Entry/TP1/TP2/SL block for each.
2. For every plan produced, hand-check `(TP1 − Entry) / (Entry − SL)` lands in
   `[1.5, 2.5]`.
3. Confirm at least one ticker returns **no** plan and that the scan loop
   reports it under the new `filtered_by_rr` counter rather than posting.
4. `!ticker AXON` equivalent: call `commands.info`'s `build_strategy_plan` loop
   directly and confirm either plan lines with in-band R:R, or the new "no
   qualifying setup" line.

**Explicitly eyeball the failure that started this**: the AXON-shaped plan must
no longer read `Entry 617.38 / TP1 621.85 / SL 604.59`. If TP1 is still inside
the stop distance, something upstream is still pricing off risk and the phase
is not done.

**Done when:** the five blocks are pasted into this plan's Progress section with
their computed R:R, and none is below 1.5 or above 2.5.

---

### Task 17: New TRAIN pre-registration and measurement

**Read `docs/claude/backtest-methodology.md` in full before starting.** Two
things there bind this task:

- Its "Frozen constants" line (`:15`) names `STRATEGY_RR_OVERRIDE` + the 0.30
  R:R floor — both deleted by Task 14. That line must be rewritten in this
  task, not quietly left stale.
- Its acceptance gates (`:11`) are `win_rate >= 80`, `expectancy_r > 0`,
  `N >= 30`. **That win-rate gate is mathematically incompatible with this
  change and must not be carried over.** Break-even win rate at R:R = X is
  `1/(1+X)`: at the old 0.30 floor that is 76.9%, which is *why* the gate was
  80%. At a 1.5 floor it is 40%, and at 2.5 it is 28.6%. Demanding 80% at 1.5R
  is demanding an edge no strategy in this repo has ever shown, and re-running
  the old gate against the new engine produces a table of failures that says
  nothing.

**Write the pre-registration BEFORE running anything**, as a new file
`docs/superpowers/results/2026-08-1X-structural-target-train.md`, containing:

- The hypothesis, in one sentence.
- The selection rule, fixed in advance: `expectancy_r > 0` as primary,
  `win_rate >= 50` as a floor (a comfortable margin over the 40% break-even at
  the 1.5 band floor, and a number chosen from arithmetic rather than from a
  table you have seen), `N >= 30`, `scratches + timeouts <= 50%` of closed
  trades — that last one carried over unchanged.
- The windows: TRAIN 2020-01-01..2023-12-31 only.
- An explicit statement that this is a **NEW** pre-registration, not a re-run of
  any row in `backtest-methodology.md`'s closed table. Naming that is the
  point — the closed rows exist so nobody reopens them, and this is a different
  question about a different engine, not a looser re-ask of an old one.

Then run:
```bash
python scripts/data/fetch_backtest_data.py          # if the cache is stale
python scripts/backtest/run_backtest_range.py --train --exit-model v2 --scale-out --json train.json
```
This is a long run. **Dispatch the `backtest-runner` subagent** so its output
never enters this context, and confirm before starting that the script prints
one flushed line per ticker — `working-conventions.md` records the monitoring
session that rule cost.

Record the full table and an honest observations section. Expect the trade
count to fall (fewer bars produce a qualifying target) and the win rate to fall
substantially (targets are 4-7x further away). Both are the change working.
**Record failures; do not retune.**

Then update `docs/claude/backtest-methodology.md`:
- Rewrite the "Frozen constants" bullet — `STRATEGY_RR_OVERRIDE` and the 0.30
  floor are gone; the frozen pair is now `MIN_RISK_REWARD_RATIO = 1.5` /
  `MAX_RISK_REWARD_RATIO = 2.5`, alongside the surviving
  `BREAKEVEN_TRIGGER_FRACTION = 0.5` and `tp1_fraction = 0.50`.
- Rewrite the "Acceptance gates" bullet with the new win-rate floor **and the
  arithmetic that justifies it**, so the next reader does not restore 80%.
- Add a row to the closed pre-registration table once Task 18 finishes.

**Done when:** the pre-registration file exists and was committed **before** the
run, the results file carries the full table, and `backtest-methodology.md`'s
two bullets are updated.

---

### Task 18: The one VALIDATION shot, and the registry

**Only after Task 17's TRAIN result is recorded and committed.** Validation is a
one-shot budget: one pre-registered run, results recorded as-is, never retuned
after. A config that failed TRAIN never gets a validation shot.

```bash
python scripts/backtest/run_backtest_range.py --validation --exit-model v2 --scale-out \
  --emit-registry swingbot/core/backtesting/validation_registry.json \
  --run-date <today> --pass-wr <the floor fixed in Task 17>
```

`run_backtest_range.py:210` already parameterises the gate as `pass_wr=80.0`;
pass the new floor rather than editing the default, and record the value used
in the results doc.

Then check the blast radius before committing the artifact: `registry.get_badge`
is what `stamp_badge` reads, and a `WEAK` badge makes `embeds.py` render
`WEAK_CAUTION_TEXT` on every alert and drives `theme.plan_color` /
`badge_field_for`. If the new registry flips a large share of rows to `WEAK`,
that is a real finding about the new engine and it ships as measured — but it
must be **stated** in the results doc, not discovered later by a user seeing a
warning banner on every message.

Commit the regenerated `validation_registry.json` in the same commit as the
results doc (hand edits are forbidden; `registry.py`'s docstring says so).

**Done when:** the results file is committed with the full table and the pass/
fail verdict per strategy, `validation_registry.json` is regenerated and
committed, and the closed-pre-registration table in
`docs/claude/backtest-methodology.md` has its new row.

---

### Task 19: Documentation

Every reference to the deleted machinery, in one commit:

- `docs/features.md:216` — "the strategy/entry-filter layer (`entry_filters.py`,
  `strategy_types.py`'s `STRATEGY_GATES`/`STRATEGY_RR_OVERRIDE`)" — the second
  symbol no longer exists. Replace with the `MIN`/`MAX_RISK_REWARD_RATIO` band.
- `docs/features.md` Plan Engine v2 section — describe target selection as it
  now works: structural, banded, `None` means no setup.
- `docs/strategy.md` — the "how the bot decides" document. Add the band and the
  nearest-qualifying rule; it is the single most user-visible mechanic in the
  bot and it is currently described as a per-horizon R:R table.
- `README.md:97` — the settings list; add `MAX_RISK_REWARD_RATIO` beside
  `MIN_RISK_REWARD_RATIO`.
- `swingbot/core/backtesting/backtest.py:32-38` — the module docstring's whole
  "R:R floor rationale" paragraph describes the deleted floor. Rewrite it around
  the new band and the new break-even arithmetic.
- `swingbot/core/planning/plan_manager.py:64-68` — `pyramid_add_fraction`'s
  docstring says "stays correct for every strategy in `STRATEGY_RR_OVERRIDE`"
  and "TP1 sits near 0.35-0.5R, so the ceiling is 0.175-0.25". The derivation is
  still correct (it reads the plan's own numbers), but both sentences are now
  false: TP1 sits at 1.5-2.5R, so `banked_r` is 0.75-1.25 and
  `PYRAMID_MAX_FRACTION` (0.50) becomes the binding cap for the first time.
  Say that.
- `swingbot/core/market/levels.py` module docstring — its long opening section
  describes scenario targets; add one sentence that the plan engine now adopts
  `take_profit` as TP1 rather than demoting it.
- `.claude/skills/task-brief/SKILL.md` and any `docs/claude/*` cross-reference
  to the deleted flags — grep and confirm none dangles.

**Done when:** `git grep -rn "STRATEGY_RR_OVERRIDE\|reward_risk_ratio\|LEVEL_LIFECYCLE_TARGETS"`
returns hits only under `docs/superpowers/{plans,specs,results}/implemented/`
and this plan file.

---

### Task 20: Version bump

**Last, after every preceding task is committed and green** — the bump is a
release marker, not a prediction.

1. `VERSION.json`: `"bot": "1.1.4"` → `"1.2.0"`, and set
   `"bot_updated"` to the current UTC `YYYY-MM-DD HH-MM-SS`. **Do not touch
   the `ui` line or `ui_updated`.**
2. Commit alone: `release(bot): 1.2.0 -- structural target selection`
3. **Then** `python scripts/dev/build_version_matrix.py` and commit
   `swingbot/admin/version_history.json` as a separate commit. This is not
   optional — `test_the_committed_file_matches_the_current_generator` asserts
   the frozen file's `current` pair equals `VERSION.json`, and the generator
   walks `git log`, so it needs the bump **already committed** or it records
   `"commit": "uncommitted", "subject": "working tree"`.
4. `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
   (~1s). The local gate cannot catch this one structurally — the full run
   before the bump was green against the *old* version.

Minor rather than patch, per `working-conventions.md`: the shape of a minor is
that someone who used this yesterday has to look at it anew, and every alert
this bot posts now carries different numbers derived a different way. `bot 1.1.0`
was earned by Plan Engine v2 for exactly this reason.

**Done when:** `VERSION.json` reads `bot 1.2.0`, `version_history.json` is
regenerated and committed, and `python scripts/dev/testrun.py full` is green.

---

## Open questions to resolve before Task 8

1. **`_atr_plan`'s candidate source (Task 1, item 5).** The ATR ladder is the
   recommendation and the plan is written assuming it. If it is rejected, Tasks
   11 and 12 change materially and eight of eleven strategies stop producing
   plans at all — decide before Task 8, not during Task 11.
2. **`plan.target_sources` after re-pricing.** `embeds.build_simple_alert`
   renders "Setup: `<strategy>` · `<target sources>`" from the **scenario's**
   `target_sources`, not the plan's. When the selector caps TP1 to a synthetic
   price, that line names sources for a level the plan is no longer targeting.
   This mismatch already exists today (TP1 ≠ `scenario.take_profit` today
   either), so it is not a regression — but this change makes it visible. Adding
   the sources to `TradePlanV2` is a **persisted-schema change**, which
   `build_strategy_plan`'s own comment (lines 542-546) already deferred once for
   the lifecycle meta for the same reason. **Recommendation: leave it, note it
   in Task 19's docs, and raise it as its own plan.**
3. **Badge blast radius (Task 18).** If the new registry flips most rows to
   `WEAK`, every alert renders `WEAK_CAUTION_TEXT`. That is an honest outcome
   and it ships, but confirm the human partner wants it shipped rather than
   suppressed — the alternative (relaxing the badge threshold) would be
   retuning after a validation shot, which the methodology forbids.

## Closing

When this plan stops being live work, `git mv` it **and**
`docs/superpowers/specs/2026-08-16-v31-structural-targets-design.md` into their
respective `implemented/` directories as part of the closing commit, and
re-point any references in the same commit.
