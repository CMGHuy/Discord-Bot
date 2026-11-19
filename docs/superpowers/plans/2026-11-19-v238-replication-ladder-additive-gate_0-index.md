# v238 — Replication ladder and additive-strategy gate: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V238-7" -A 400 <part file>`); never read a part whole.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) — this plan is the spec's **Plan 2 (Parts B and C)**. Part A shipped as plan v230 ([implemented/2026-11-16-v230-screen-v2-rescreen_0-index.md](implemented/2026-11-16-v230-screen-v2-rescreen_0-index.md)) and plan v234 ([implemented/2026-11-17-v234-screen-v2-null_0-index.md](implemented/2026-11-17-v234-screen-v2-null_0-index.md)). Numbered fresh (v238) because the spec spawns more than one plan (`document-conventions.md`).
**Brief:** `.superpowers/briefs/2026-11-19-v230-ladder-additive-gate.md`

## Goal

Two of the three defects the v230 spec found are not in the screen itself but
in what happens after it. A screen pass is raced on one shape (a 1.5/3 ATR
stop and target from the next open, PIT S&P 500, 2010–2019, yfinance bars),
and the next test, as v180 showed with Turtle Soup, changes the stop, the
target, the universe, the period and the data source in one step: when it
fails, nobody can say which change killed it. And an added strategy is then
judged by the v72 filter gate, which makes the **book's pooled win rate** the
objective: a strategy that adds rows at reward:risk 2 breaks even at 33%,
lowers the pooled win rate while paying, and is refused (v180 died on a
−0.21pp pooled ΔWR). v180 also compared net added rows with a gross book.

Once this plan ships, a screen pass goes through a **replication ladder**
(`scripts/backtest/replicate_idea.py`, core in `screen/ladder*.py`): four
frozen shots, each changing one thing from the rung above, each a
`ladder-<name>-r<N>` ledger row under instrument `ladder-v1`. Rung 1 re-races
the screen's own trigger and shape on the Alpaca PIT store over
2017-03-01..2020-12-31 (a robustness check, 2020 printed alone); rung 2
anchors the same ATR stop and target on the **signal close**, so the trade
can be placed as resting orders when the alert posts; rung 3 swaps in the
bot's stop; rung 4 the bot's target band. A rung holds when the
week-clustered lower 95% bound of its net mean R is above zero with N ≥ 300;
rung 1 also needs a positive ΔExpR against the null. The ladder's result names
the shape a strategy spec may ship in (bot shape, or the orderable screened
shape), so a failure names its cause. Added strategies get their own gate,
`validate_component.py --gate additive` (`acceptance_additive.py`): own net
ExpR is the objective (clause 1), win rate must clear the strategy's **own
realised break-even** (clause 2), the book's total R must not fall when an
added position displaces a baseline plan (clause 3), and the gain must hold in
two of three walk-forward folds (clause 4). Both arms must be **net** of
costs, enforced by an arm-file stamp `provenance["r_basis"]` and one shared
net-R function that charges shorts borrow and longs never.

What it leaves alone: the v72 and v92 gates and their clauses, `check_stamp`'s
behaviour for every existing gate, today's gross arm booking (the default
stays byte-identical; net is opt-in), the screen and both nulls, every ledger
row already written, the live bot and its alerts. It runs **no ladder shot on
a real idea**: there is no valid `screen-v2` `SCREEN-PASS` row today (the v2
null was not accepted, stop gate 2 = STOP), so the instruments are built and
tested on fixtures only. Success is the two instruments merged with their
tests green in CI, the ledger able to take `ladder-v1` rows, `## Additive
gate` in `backtest-methodology.md`, and the stamp, refusal token and net-R
function pinned as named contracts v231 can build on.

## Architecture

- **Net basis (Part C foundation).** `swingbot/core/edge/frictions.py` gains
  `net_r_legs`, the one net-R function for arm rows (replay now, live journal
  rows in v231): entry and every exit leg slipped against the trade, one
  round-trip commission, and for shorts `borrow_r` over calendar days held.
  It matches `screen/sides.net_r` on a single leg. `arms/net_basis.py`
  books an engine row on a requested basis; the per-ticker engines
  (`confluence`, `strategy`) take `r_basis=None|"net"|"gross"` (None = today,
  byte-identical). `measure_arms.py --r-basis` threads it and stamps
  `provenance["r_basis"]`; `provenance.check_r_basis` refuses anything but
  `"net"` with `refused:r-basis`, called by `--gate additive` only.
- **Additive gate (Part C).** `swingbot/core/backtesting/acceptance_additive.py`
  holds the add-only split (`ADDITIVE_GATE_MISUSE`), the four clauses on
  week-cluster bootstraps (`instrument/stats.week_cluster_bootstrap`), the
  frozen-effect Stage 0 MDE, the disclosures and `evaluate_additive`, which
  returns the shared `acceptance.AcceptanceResult`. `validate_component.py`
  routes `--gate additive` through a stage table (`_stage_runner`) and a
  table-driven flag-conflict check, so `main` drops below its complexity 13.
- **Ladder (Part B).** `screen/ladder.py` holds the rules (ids, windows, hold
  rule, paired difference, refusals, next step); `screen/ladder_race.py` the
  close-anchored race with gap fills; `screen/ladder_bot.py` the bot stop and
  target adapters over `swingbot/core/planning/` (truncated frames) and the
  book-survival report. `scripts/backtest/replicate_idea.py` runs one rung per
  invocation: rung 1 through `screen_idea.screen_universe` (the **v1** null
  pipeline, called explicitly) on `data/market_data_pit/daily`, rungs 2–4 on
  rung 1's events, each checkpointed per ticker; it writes the results doc,
  then the ledger row.
- **Ledger vocabulary.** `stats.INSTRUMENTS` gains `ladder-v1`;
  `stats.VERDICTS` gains `LADDER-HOLD`, `LADDER-FAIL`, `LADDER-UNDERPOWERED`
  (appended, no upcasting). The additive gate's ledger rows use the existing
  `PASS` / `FAIL` / `NO-LIFT` (it is a funnel gate on instrument v1, like v72
  and v92), so it adds no verdict.

**Tech stack:** Python 3.11, numpy/pandas, pytest; no database, no frontend change.

## Handoff

Rulings from the controller, 2026-11-19, resolving the brief's discrepancies.
They bind every part writer and implementer.

1. **Rung 1 runs on the v1 null.** Partner decision 2026-11-18 (v234 index
   `## Handoff`, stop gate 2 = STOP): "Parts B and C proceed on the v1 null."
   Where the spec says "v2 null" for rung 1, this plan uses v1: rung 1 calls
   `screen_idea.screen_universe` (the v1 per-ticker pipeline) explicitly and
   `ladder.NULL_VERSION = "v1"`; every rung 1 results doc and ledger
   hypothesis says the v1 null is known biased (+0.27..+0.37R on next-open
   longs), citing `docs/superpowers/results/2026-11-18-v230-null-placebo.md`.
   `screen_idea.NULL_VERSION`'s default is **not** touched by this plan.
2. **`r_basis` is a file-level provenance stamp** `provenance["r_basis"]`,
   values `"net"` / `"gross"`, never an `ArmTrade` field (that would break
   every `ArmTrade(**row)` loader). Missing, gross or malformed stamps are
   refused by `--gate additive` only; `check_stamp` is not edited and the
   v72/v92 gates behave byte-identically.
3. **One shared net-R function** for arms: `frictions.net_r_legs` (contract
   below), `screen/sides.net_r` semantics (planned risk, both sides slipped,
   commission, borrow for shorts over days held), not
   `expectancy_attribution.net_r` (no borrow, risk re-based). `ArmTrade` gains
   no price or holding-day field. Turtle Soup's existing booking under
   `r_basis=None` is untouched.
4. **v231 contract.** v231 (`docs/superpowers/specs/2026-11-16-v231-direction-gates-design.md`
   § Constraints) builds on rulings 2–3 and edits `validate_component.py`,
   `measure_arms.py` and `arms/provenance.py`. The named contracts it may cite
   are in `## Cross-plan contracts (v231)` below; they are final.
5. **Ledger vocabulary is in scope** (V238-9): `ladder-v1`, the three ladder
   verdicts, the `research.py:79` and `preregistration_ledger.py:42`
   consumers and their pinned tests (including
   `tests/backtest_scripts/test_screen_avoid_mode.py:262`, which pins
   `VERDICTS[-1]`).
6. **Complexity.** `validate_component.main` is 13 and `check_stamp` 11:
   `--gate additive` goes through `_stage_runner` and `_flag_conflict`
   (V238-7); `check_stamp` is not edited.
7. **Rung 1 cannot reuse `screen_idea.refusal`** (hard 2019-12-31 end); the
   ladder has its own windows and refusals. Rungs 3/4 stop/target stand-ins
   are the builder's call (spec `## Left to the builder`): V238-12/13 name
   the candidates from the brief and record the choice in
   `ladder_bot.BOT_SHAPE` and every rung 3/4 results doc.
8. **`LADDER-UNAVAILABLE`** for an idea whose `context` series is absent
   from `data/market_data_pit/daily` (UUP, `^VIX`, `BREADTH_ATR1` today): a
   refusal before any outcome is read, no ledger row, no shot spent.
9. **No ladder run on a real idea.** The spec requires no run in Plan 2
   (since the 2026-11-19 ruling, `screen-v1` passes such as uptrend_pullback
   and turtle_soup are valid inputs, but running them is out of scope); the plan
   builds and tests the instruments on fixtures only. The first real rung is
   a later, separate dispatch to `backtest-runner`, one rung per chunk.
- 2026-11-19: index committed (61b419fa). **Partner ruling:** the ladder also accepts `screen-v1` SCREEN-PASS rows: `INPUT_INSTRUMENTS = ("screen-v1", "screen-v2")`; a v1 input is flagged biased-null in its results doc and ledger DESCRIPTION. Part writers for V238-9..17 apply this.
- 2026-11-19: Part 1 written (V238-1..3b). Writer split V238-2 -> V238-2b (engines) and V238-3 -> V238-3b (measure_arms flag); ledger rows added, contracts unchanged (V238-7 still consumes `check_r_basis`/`R_BASIS_REFUSAL` from V238-3). Writer's calls: `check_basis` refuses both `net` and `gross` under a non-v1 instrument (v2/v3 `r_total` is already costed); under any requested basis Turtle Soup books through `net_basis` and its sidecar logs the booked R (under `None` it stays on `tsr.net_r`); `--r-basis` with a population knob is refused (`refused:r-basis-population`). Next: part 2.

## Global Constraints

- **The default is byte-identical.** `r_basis=None` everywhere books exactly
  today's rows (gross for every strategy but Turtle Soup, which stays net via
  `turtle_soup_research.net_r`); `tests/backtesting/arms/test_v192_flag_off_golden.py`,
  `tests/backtesting/test_acceptance_v68_regression.py` and
  `tests/backtesting/instrument/test_v1_golden.py` stay green untouched.
  A stamp built without `r_basis` is key-for-key today's stamp.
- **v72 / v92 untouched.** `acceptance.py`'s clauses and `VERSION`,
  `acceptance_harvest.py`, `check_stamp` and every existing `validate_component`
  message stay as they are (the conflict messages move into a table verbatim).
- **No-lookahead** (`docs/claude/architecture.md`): rung 3/4 stops and targets
  are computed from `df.iloc[: signal_pos + 1]`; a truncation test
  (`tests/backtesting/screen/helpers.py:assert_prefix_stable`) proves they do
  not change when later bars are removed. Rung entries are `open[t+1]`.
- **The ladder never reads 2021 or later:** every frame is loaded with
  `end = ladder.READ_END = "2020-12-31"`; events run
  `ladder.EVENT_START = "2017-03-01"` .. `READ_END`; frames start at
  `ladder.STORE_START = "2016-01-04"`.
- **One shot per id** for `ladder-*`: a rung whose ledger row exists is
  refused; a crashed run that wrote no result may be re-run once, recorded in
  `crash.json` beside the rung's checkpoints and in its results doc.
- **Long runs checkpoint per ticker** (`<work-dir>/rung<N>/<TICKER>.json`
  for rungs 2–4; rung 1 uses `screen_universe`'s own `checkpoint_dir`); a
  restart skips finished tickers. Real rungs go to `backtest-runner`.
- **Week clusters** (`instrument/stats.iso_week_key`, 10,000 resamples,
  seed 42, undefined draws dropped) for every ladder and additive interval;
  "lower 95% bound" is the 2.5th percentile of the draws, the one-sided p is
  the share of draws ≤ 0.
- **Costs:** 5 bps a side plus commission (`frictions` defaults) on every rung
  and in `net_r_legs`; shorts also pay `frictions.borrow_r` over calendar days
  held, longs never. 2 × slippage re-priced beside each rung, never gating.
- **Complexity < 15** on every new or changed function
  (`scripts/dev/complexity_gate.py`).
- **Placement.** New logic in modules under `swingbot/core/`;
  `scripts/backtest/screen_idea.py` (2088 lines) is imported, never edited.
  Nothing outside `swingbot/core/backtesting/` imports the screen package
  (`test_import_guard.py`). A new script under `scripts/backtest/` gets its
  `test_date_literal_guard.py` entry.
- **Tests and suites.** New tests go in `tests/edge/` (suite `edge`),
  `tests/backtesting/arms/` and `tests/backtesting/screen/` (suite
  `backtesting-arms`), `tests/backtesting/test_acceptance_additive*.py`
  (`backtesting-a-k`), `tests/backtesting/test_validate_component_additive*.py`
  (`backtesting-l-z`), `tests/backtest_scripts/` (`backtest-scripts`),
  `tests/hooks/` (`dev-setup`). No new test directory. If a suite would pass
  its `max_tests`, split it by feature in `tests/suites.toml` in the same
  commit, never raise the limit. No database.
- **Verification is narrow:** `python scripts/dev/testrun.py file <test>`
  per task; **no task runs the full suite** (CI does, after the push).
- **Results docs and Markdown** are written with `encoding="utf-8",
  newline="\n"`; `replicate_idea.py` calls `screen_idea._utf8_stdout()`.
- **Ledger:** fixed fields (`stats.LEDGER_FIELDS` + optional `data_source`);
  ladder rows carry `data_source: "alpaca"`; the results doc is written before
  the row; cross-references go in `hypothesis` and the doc.
- **Codex mirror.** Doc and skill edits ship with `AGENTS.md` and
  `python scripts/dev/sync_codex.py` in the same commit
  (`tests/hooks/test_codex_mirror.py`).
- **Commits.** The implementer commits per task in the plan's worktree, in
  scoped commits; plan writers do not commit.

## Cross-plan contracts (v231)

Final; v231's plan cites these by name.

| Contract | Shape |
|---|---|
| Net-R function | `swingbot/core/edge/frictions.py: net_r_legs(entry: float, stop_loss: float, direction: str, legs: Sequence[Mapping], *, days: float) -> float`. `direction` in `NET_R_SIDES` (`"bullish"`/`"long"` → long, `"bearish"`/`"short"` → short); `risk = abs(entry - stop_loss)`; entry slipped against the trade (`apply_frictions`, default bps), each leg's `exit_price` slipped on the exit side and weighted by `leg["fraction"]`; minus `commission_r()`; shorts minus `borrow_r(entry, risk, days)`, longs never read `days`. `ValueError` on no legs, zero risk, unknown direction, or fractions not summing to 1 (±1e-9). |
| Stamp key / values | `provenance.R_BASIS_KEY = "r_basis"`; `provenance.R_BASES = ("net", "gross")`; written by `build_stamp(..., r_basis=None)` only when not None. |
| Refusal token | `provenance.R_BASIS_REFUSAL = "refused:r-basis"`, appended last to `REFUSAL_TOKENS`; returned by `provenance.check_r_basis(blob: dict, *, required: str = "net") -> str \| None` for a missing stamp, a missing key, or any value other than `required`. `check_stamp` never returns it. |
| Engine basis | `arms/net_basis.booked_r(plan, result, df, *, r_basis: str) -> float`; `engine.get_engine(engine_id, *, instrument=None, r_basis=None)`; `engine.run_arm(..., *, instrument=None, r_basis=None)`; `measure_arms.produce(..., r_basis=None)`; CLI `measure_arms.py --r-basis {net,gross}`. |
| Gate selector | `validate_component.py --gate {win_rate,harvest,additive}`; stage dispatch via `_stage_runner(args)`; per-gate runner tables `_STAGES` (today's) and `_ADDITIVE_STAGES`; flag conflicts in `_FLAG_CONFLICTS` / `_flag_conflict(args)`. v231 adds `direction` as one more table entry. |

## Decisions this index fixes (inside the spec's "left to the builder")

- **Add-only detection** (`acceptance_additive.split_additive`, by
  `acceptance.population_split` on `ArmTrade.key`): `ADDITIVE_GATE_MISUSE`
  when the component adds no row, when any shared key's outcome or R changed,
  or when more baseline rows vanished than rows were added (a displacement
  needs an added position). Every vanished baseline key is a displaced row.
  The replay does not expose a displacement cause today; the results doc
  lists each displaced row with cause `not exposed by the replay`.
- **Stage mapping for `--gate additive`:** `reachability` = Stage −1 (stamp
  gate, `check_r_basis`, add-only split); `mde` = Stage 0 (frozen
  `--expected-own-r` and `--expected-sd-r` from the pre-registration, N =
  count of added rows, no R read); `selection` = Stage 1 (clauses 1–3 per
  `--grid-arms` cell; with two or more cells, the adopted cell is the
  highest own net ExpR among cells passing 1–3, first in grid order on a tie,
  and `backtest_wf.plateau_report` is printed); `walkforward` = Stage 2
  (clause 4 on the arms' `folds`); `validation` = Stage 3 (all four, clause 4
  read from `--folds-arms`, the Stage 2 arms file).
- **Stage 0 spread.** The spec freezes the expected effect but not its
  spread; the pre-registration also freezes `--expected-sd-r` (the selected
  ladder rung's per-event net R standard deviation), so Stage 0 never reads
  fold-train R. `mde_own_expectancy = (z(0.975) + z(power)) × sd / sqrt(n)`.
- **`check_r_basis` runs under `--bespoke-instrument` too**: net arms are a
  precondition of the additive gate, not a provenance convenience.
- **`r_basis="net"` with a non-v1 instrument raises** (the v3 instrument
  already prices costs); **with a population engine raises** (scan replay
  rows are not booked by `net_basis`; a later spec may add it).
- **Rung shapes.** Rungs 2–4 race the `fixed` shape with a `next_open`
  entry; an idea with `race_shape != "fixed"` or `entry != "next_open"`
  stops after rung 1 with refusal `LADDER-UNAVAILABLE: rung N needs the
  fixed next-open shape` (no row). R is measured against the planned risk
  from the signal close (the share count the alert would size). An open
  beyond the stop or target exits at that open (`gap_stop` / `gap_target`),
  so its gross R is the open-to-open move, zero, and its net R is the costs.
- **One rung per invocation**; rung N reads `<work-dir>/rung<N-1>-events.json`
  (rung 1's events for rungs 2–4) and writes `<work-dir>/rung<N>-events.json`.
- **Ladder input:** a `SCREEN-PASS` row `screen-<name>` or `screen2-<name>`
  whose instrument is in `ladder.INPUT_INSTRUMENTS = ("screen-v1", "screen-v2")`
  (partner ruling 2026-11-19, widening the spec's `screen-v2`-only input; see
  `## Handoff`). A `screen-v1` input is flagged "biased null (v230 placebo)"
  in its results doc and its `ladder-v1` ledger row's DESCRIPTION.
- **Membership check** prints and records the members missing from the store
  (count and names); only a missing context series refuses.
- **The research page** keeps its default: new verdicts render neutral
  (`frontend/src/app/workspaces/research/research.ts:VERDICT_TONE` comment);
  no frontend edit.

## Parallelisation

Two independent groups (the spec's Part C and Part B) share no files; they
join at V238-17. At most 2 implementers at once (session rule).

- **Lane C1 (net basis):** V238-1 → V238-2 → V238-3. Sequential (contract):
  V238-2 calls `frictions.net_r_legs`; V238-3 threads `run_arm(r_basis=)`
  from V238-2 into `measure_arms` and the stamp.
- **Lane C2 (gate core):** V238-4 → V238-5 → V238-6. Sequential (same file
  `acceptance_additive.py`). Independent of lane C1 (no shared file or
  contract), so C1 ∥ C2.
- **Funnel CLI:** V238-7 needs V238-3 (`check_r_basis`, `R_BASIS_REFUSAL`)
  and V238-6 (`evaluate_additive`, `split_additive`, `stage0_refusal`).
  V238-8 needs V238-7 (same file `validate_component.py`).
- **Lane B1 (ladder core):** V238-9 → V238-10 (contract: `ladder` verdict
  strings are pinned against `stats.VERDICTS`). V238-11 needs V238-10
  (`LadderEvent`). V238-12 needs V238-10 only (constants); V238-11 ∥ V238-12
  (disjoint files `ladder_race.py` / `ladder_bot.py`). V238-13 needs V238-12
  (same file) and V238-10 (`LadderEvent`).
- **Lane B2 (CLI):** V238-14 needs V238-9 and V238-10. V238-15 needs V238-14
  (same file) and V238-11, V238-12, V238-13. V238-16 needs V238-15 (same
  file) and V238-9.
- **Groups C and B run in parallel** (C1/C2 ∥ B1; V238-7/8 ∥ V238-14..16).
- **Join:** V238-17 needs V238-8 and V238-16 (the docs cite final names and
  flags).

## Task ledger

| ID | Title | Part | Model | Files (C create, M modify) | Symbols for later tasks |
|---|---|---|---|---|---|
| V238-1 | Shared net-R function for arm rows | 1 | sonnet | M `swingbot/core/edge/frictions.py`, M `tests/edge/test_edge_frictions.py` | `frictions.net_r_legs(entry, stop_loss, direction, legs, *, days) -> float`; `frictions.NET_R_SIDES: dict[str, str]` |
| V238-2 | Shared net-R basis module | 1 | opus | C `swingbot/core/backtesting/arms/net_basis.py`, C `tests/backtesting/arms/test_net_basis.py` | `net_basis.R_BASES = ("net", "gross")`; `net_basis.holding_days(df, result) -> int`; `net_basis.check_basis(r_basis, *, instrument) -> None` (refuses both bases under a non-v1 instrument); `net_basis.booked_r(plan, result, df, *, r_basis) -> float` |
| V238-2b | Arm engines book on a requested R basis | 1 | opus | M `swingbot/core/backtesting/arms/engine.py`, M `swingbot/core/backtesting/arms/confluence_engine.py`, M `swingbot/core/backtesting/arms/strategy_engine.py`, C `tests/backtesting/arms/test_net_basis_engines.py` | `get_engine(engine_id, *, instrument=None, r_basis=None)`; `run_arm(ticker, df, engine_ids, horizons, signal_window, delta, *, instrument=None, r_basis=None)`; `ConfluenceEngine(instrument=None, r_basis=None)`; `StrategyEngine(instrument=None, r_basis=None)` |
| V238-3 | r_basis stamp and refusal token | 1 | sonnet | M `swingbot/core/backtesting/arms/provenance.py`, M `tests/backtesting/arms/test_provenance.py` | `provenance.R_BASIS_KEY`; `provenance.R_BASES`; `provenance.R_BASIS_REFUSAL = "refused:r-basis"` (last in `REFUSAL_TOKENS`); `build_stamp(..., r_basis=None)`; `check_r_basis(blob, *, required="net") -> str \| None` |
| V238-3b | measure_arms --r-basis producer flag | 1 | sonnet | M `scripts/backtest/measure_arms.py`, C `tests/backtest_scripts/test_measure_arms_r_basis.py` | `produce(..., r_basis=None)` (raises `ValueError` with a population knob); CLI `--r-basis {net,gross}`; `refused:r-basis-population` (exit 1, before any compute) |
| V238-4 | Additive split and clauses 1–2 | 2 | opus | C `swingbot/core/backtesting/acceptance_additive.py`, C `tests/backtesting/test_acceptance_additive.py` | `ADDITIVE_VERSION = 1`; `ADDITIVE_GATE_MISUSE = "ADDITIVE_GATE_MISUSE"`; `CLAUSES = ("own_expectancy", "win_rate_above_breakeven", "book_net_gain", "stability")`; `@dataclass(frozen=True) AdditiveSplit(added: tuple, displaced: tuple, misuse: str \| None)`; `split_additive(baseline, component) -> AdditiveSplit`; `added_bootstrap(added, statistic, *, n_resamples, seed) -> np.ndarray`; `clause_own_expectancy(added, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> ClauseResult`; `realised_breakeven(rows) -> float \| None` (fraction); `clause_win_rate_above_breakeven(added, *, n_resamples=..., seed=42) -> ClauseResult` (value and threshold in percent) |
| V238-5 | Additive clauses 3–4: book net gain and stability | 2 | opus | M `swingbot/core/backtesting/acceptance_additive.py`, C `tests/backtesting/test_acceptance_additive_book.py` | `TOLERANCE_SHARE = 0.10`; `FOLD_YEARS = ("2021", "2022", "2023")`; `FOLD_FLOOR_R = -0.10`; `FOLD_MIN_N = 30`; `FOLDS_POSITIVE = 2`; `clause_book_net_gain(baseline, component, split, *, n_resamples=..., seed=42) -> ClauseResult` (`SKIPPED` when `split.displaced` is empty); `clause_stability(folds: list[dict]) -> ClauseResult` (folds in `validate_component.load_folds` shape) |
| V238-6 | Additive Stage 0 MDE, disclosures and evaluate_additive | 2 | opus | M `swingbot/core/backtesting/acceptance_additive.py`, C `tests/backtesting/test_acceptance_additive_evaluate.py` | `STAGE_CLAUSES = {"selection": CLAUSES[:3], "walkforward": CLAUSES[3:], "validation": CLAUSES}`; `class AdditiveMisuse(ValueError)` (`.reason`); `mde_own_expectancy(*, n, sd_r, power=0.80, alpha=ALPHA) -> float \| None`; `stage0_refusal(*, n, expected_r, sd_r) -> str \| None`; `disclosures(added, baseline) -> dict` (keys `max_drawdown_r`, `longest_losing_streak`, `top5_week_share`, `signals_per_day_p95`, `signals_per_day_max`, `same_week_corr`); `render_disclosures(d) -> list[str]`; `evaluate_additive(baseline, component, *, stage, folds=None, n_resamples=..., seed=42) -> AcceptanceResult` (`cluster="week"`, `version=ADDITIVE_VERSION`; raises `AdditiveMisuse`) |
| V238-7 | Funnel CLI: --gate additive dispatch, basis refusal, Stages −1 and 0 | 3 | opus | M `scripts/backtest/validate_component.py`, C `tests/backtesting/test_validate_component_additive.py` | `--gate` choices `("win_rate", "harvest", "additive")`; `_FLAG_CONFLICTS`; `_flag_conflict(args) -> str \| None`; `_STAGES`; `_ADDITIVE_STAGES`; `_stage_runner(args)`; `_additive_basis_gate(args) -> int \| None`; `_misuse_line(reason) -> int`; `stage_additive_reachability(args)`; `stage_additive_mde(args)`; flags `--expected-own-r`, `--expected-sd-r` |
| V238-8 | Funnel CLI: additive Stages 1–3 and reports | 3 | opus | M `scripts/backtest/validate_component.py`, C `tests/backtesting/test_validate_component_additive_stages.py` | `stage_additive_selection(args)`; `stage_additive_walkforward(args)`; `stage_additive_validation(args)`; flags `--knob`, `--folds-arms`; `_write_additive(args, result, extra) -> None` |
| V238-9 | Ledger vocabulary: ladder-v1 and ladder verdicts | 4 | sonnet | M `swingbot/core/backtesting/instrument/stats.py`, M `tests/backtesting/test_instrument_stats_ledger.py`, M `tests/backtest_scripts/test_screen_avoid_mode.py`, M `tests/scripts/test_preregistration_ledger_cli.py` | `"ladder-v1"` in `stats.INSTRUMENTS` (last); `"LADDER-HOLD"`, `"LADDER-FAIL"`, `"LADDER-UNDERPOWERED"` appended to `stats.VERDICTS` |
| V238-10 | Ladder rules: ids, windows, hold rule, paired difference, refusals | 4 | opus | C `swingbot/core/backtesting/screen/ladder.py`, C `tests/backtesting/screen/test_ladder.py` | `LADDER_INSTRUMENT = "ladder-v1"`; `ladder_id(name, rung) -> str`; `RUNGS`; `RUNG_NAMES`; `STORE_START`, `EVENT_START`, `READ_END`; `HOLD_N = 300`; `HOLD`, `FAIL`, `UNDERPOWERED`; `UNAVAILABLE = "LADDER-UNAVAILABLE"`; `INPUT_INSTRUMENTS`; `NULL_VERSION = "v1"`; `@dataclass(frozen=True) LadderEvent(ticker, signal_date, entry_date, exit_date, r, gross_r, outcome, r_null=None, r_stress=None)`; `HoldResult(verdict, n, mean, lo, hi, p, delta_null)`; `hold(events, *, rung, n_resamples=10_000, seed=42) -> HoldResult`; `PairedDiff(n, mean, lo, hi, wholly_below_zero)`; `paired_difference(upper, lower, *, n_resamples=10_000, seed=42) -> PairedDiff`; `input_refusal(name, rows) -> str \| None`; `rung_refusal(name, rung, rows) -> str \| None`; `shape_refusal(idea, rung) -> str \| None`; `context_refusal(idea, store_dir) -> str \| None`; `membership_coverage(members, store_dir) -> dict`; `NEXT_STEPS`; `next_step(holds, diff_4_vs_2) -> str` |
| V238-11 | Orderable race: close-anchored levels and gap fills | 4 | opus | C `swingbot/core/backtesting/screen/ladder_race.py`, C `tests/backtesting/screen/test_ladder_race.py` | `STRESS_FACTOR = 2`; `orderable_levels(df, signal_pos, *, atr, direction) -> tuple[np.ndarray, np.ndarray]`; `race_levels(df, signal_pos, cap, *, stop, target, direction="long", slippage_bps=None, commission=None) -> race.RaceResult`; `gap_through(result) -> tuple[int, float]`; `to_events(ticker, df, result, *, stress=None) -> list[LadderEvent]` |
| V238-12 | Bot stop adapter (rung 3) with truncation test | 4 | opus | C `swingbot/core/backtesting/screen/ladder_bot.py`, C `tests/backtesting/screen/test_ladder_bot.py` | `BOT_SHAPE: dict[str, str]` (keys `stop_entry_point`, `target_entry_point`, `strategy`, `horizon_key`, `why`); `bot_stop(df, signal_pos, *, direction) -> float \| None`; `rung3_levels(df, signal_pos, *, direction) -> tuple[float \| None, float \| None]`; `clamp_would_drop(entry, stop, *, direction) -> bool` |
| V238-13 | Bot target adapter (rung 4), attrition and book survival | 4 | opus | M `swingbot/core/backtesting/screen/ladder_bot.py`, C `tests/backtesting/screen/test_ladder_bot_target.py` | `ATTRITION = ("no_level_in_band", "risk_cap")`; `rung4_levels(df, signal_pos, *, direction) -> tuple[float \| None, float \| None, str \| None]`; `book_survival(events, *, max_open) -> dict` (keys `one_per_ticker_share`, `concurrent_share`, `signals_per_day_p95`, `signals_per_day_max`) |
| V238-14 | replicate_idea CLI: refusals, run marker and rung 1 | 5 | opus | C `scripts/backtest/replicate_idea.py`, C `tests/backtest_scripts/test_replicate_idea.py`, M `tests/backtesting/instrument/test_date_literal_guard.py` | `build_parser()`; `main(argv=None) -> int`; flags `--idea`, `--rung`, `--work-dir`, `--store`, `--membership`, `--results-dir`, `--ledger`, `--dry-run`; `DEFAULT_STORE = data/market_data_pit/daily`; `@dataclass RungRun(events, counters, gap_count=0, gap_r=0.0, survival=None, clamp_share=None, attrition=None)`; `refusals(args, idea, rows) -> str \| None`; `run_rung(idea, rung, args, *, out=print) -> RungRun` (rung 1 branch); `write_events(path, events)`; `read_events(path) -> list[LadderEvent]`; `class RunMarker(directory)` with `start() -> str \| None`, `finish()`, `crash_note() -> str \| None` |
| V238-15 | replicate_idea: rungs 2–4 with per-ticker checkpoints | 5 | opus | M `scripts/backtest/replicate_idea.py`, C `tests/backtest_scripts/test_replicate_idea_rungs.py` | `run_rung` branches for rungs 2, 3, 4; `_ticker_checkpoint(work_dir, rung, ticker) -> Path` |
| V238-16 | replicate_idea: results docs, ledger row and next step | 5 | sonnet | M `scripts/backtest/replicate_idea.py`, C `tests/backtest_scripts/test_replicate_idea_publish.py` | `results_path(results_dir, name, rung, date) -> Path` (`<date>-ladder-<name>-r<N>.md`); `render_rung(idea, rung, run, hold, *, diff=None, year_2020=None, watchlist=None, stress=None, date) -> str`; `ledger_row(idea, rung, hold, path, date) -> dict`; `publish(args, idea, rung, run) -> int` |
| V238-17 | Methodology, conventions, screen skill and Codex mirror | 5 | sonnet | M `docs/claude/backtest-methodology.md`, M `docs/claude/document-conventions.md`, M `tests/hooks/test_doc_sections.py`, M `.claude/skills/screen/SKILL.md`, M `.agents/skills/screen/SKILL.md` (via `sync_codex.py`), M `AGENTS.md` | `## Additive gate` heading (after `## Harvest gate`); ladder paragraph inside `## Funnel stages` Stage −2; strategy-spec ladder-citation rule |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-19-v238-replication-ladder-additive-gate_1-net-basis.md` | V238-1..V238-3 | shared net-R function, engine booking basis, `r_basis` stamp and refusal, producer flag |
| 2 | `2026-11-19-v238-replication-ladder-additive-gate_2-additive-gate.md` | V238-4..V238-6 | `acceptance_additive.py`: split, four clauses, Stage 0 MDE, disclosures, `evaluate_additive` |
| 3 | `2026-11-19-v238-replication-ladder-additive-gate_3-additive-funnel.md` | V238-7..V238-8 | `validate_component.py --gate additive`, all five stages |
| 4 | `2026-11-19-v238-replication-ladder-additive-gate_4-ladder-core.md` | V238-9..V238-13 | ledger vocabulary, ladder rules, orderable race, bot stop and target adapters |
| 5 | `2026-11-19-v238-replication-ladder-additive-gate_5-ladder-run.md` | V238-14..V238-17 | `replicate_idea.py` (rungs 1–4, docs, ledger) and the methodology/skill docs |
