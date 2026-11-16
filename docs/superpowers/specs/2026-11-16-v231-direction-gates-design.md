# v231 — Direction gates: a LONG book, a SHORT book, and a filter gate that scores one of them

**Version:** ui 1.44.0 · bot 2.19.1
**Bump:** ui minor (a new "Direction books" panel in the Research workspace); bot none (measurement instruments and one read-only endpoint; nothing the bot scans, alerts on or posts changes)
**Edge:** none (integrity). Two instruments and one report. They decide what counts as a pass; they lift nothing by themselves.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, ux-designer
**Status:** spec written 2026-11-16 from a brainstorm with the partner; the four decisions in `## Partner decisions` were made in chat the same day. Implementation waits for v230 (see `## Constraints`).

## Why

The partner asked how to change the backtest process so that LONG and SHORT
trades can each be profitable. Reading the process against the live book
(`docs/superpowers/results/2026-11-16-book-autopsy.md`) gave three findings.

### Finding 1: neither direction makes money, and no gate asks whether it does

| Live book cell (autopsy 2026-11-16) | N | Win rate | ExpR |
|---|---|---|---|
| `direction=bearish` | 320 | 50.0% | −0.136 |
| `direction=bullish` | 747 | 42.3% | −0.067 |

Every acceptance gate judges a feature against the baseline it replaces.
When the baseline is negative, a feature can pass every clause and leave the
book losing. Nothing in `backtest-methodology.md` states a per-direction
absolute target or reports where each direction stands against it.

### Finding 2: the filter gate still makes win rate the objective

`swingbot/core/backtesting/acceptance.py` (v72, `VERSION = 2`) passes a
filter when standardised win rate rises and expectancy is not worse than
−0.01R. `CLAUDE.md` ranks pooled ExpR first and win rate as a constraint.
The short book is the gate's own failure shape: half the trades win and the
book loses 0.136R a trade. v92 (harvest) and v230 Part C (added strategies)
already put expectancy first; filters and other changes to existing rows are
the remaining population judged win-rate-first.

### Finding 3: the funnel scores both directions as one population

`ArmTrade.direction` is part of the pairing key but no clause reads it
(`stratum` is `(strategy, horizon_key)`). A short-only filter is scored on a
population that is about 70% long rows it cannot touch, which dilutes its
effect below the Stage 0 MDE; and nothing stops a "short" change from moving
long rows. The only direction logic is a disclosure in
`arms/selection.py` (`_direction_disclosure`), which gates nothing.

### What v230 already covers

v230 (same day) fixes the idea screen's null, adds the replication ladder
and gives **added strategies** an expectancy-first gate. It leaves the v72
filter gate untouched by its own non-goals, has no per-direction book check
and no market-regime report in the funnel. This spec covers exactly that
remainder and builds on v230's `r_basis` arm stamp.

## Partner decisions (2026-11-16)

1. **Profit bar: a book gate and a feature gate.** Each direction's whole
   book must show expectancy above zero after costs with the lower
   confidence bound above zero; each feature is judged only on the direction
   it touches, with expectancy lift as the objective and win rate as the
   constraint.
2. **Market regime: gate as-traded, report per regime.** The book gate
   scores the trades the bot would really take, all days together. The
   regime split is printed per direction on every result and never gates.
   A direction that pays in one regime only becomes a "trade it only when X"
   feature tested through the feature gate.
3. **Consequence: status and a promotion rule.** Each direction carries
   `PROVEN` / `UNPROVEN`. Alerts keep flowing unchanged; nothing is switched
   off. A feature is promoted to on-by-default only if it does not move its
   direction's book down.
4. **Build inside the existing funnel**, old gate kept so closed rows stay
   reproducible.

Two related decisions from the same conversation, outside this spec:
"more ideas per direction" is **parked until v230's re-screen results**;
"backtest-to-live realism" is a separate spec, brainstormed next.

## Goals

1. State, for LONG and for SHORT, whether the book makes money after costs,
   in replay and in the live paper book, with a status anyone can read.
2. Judge a filter (or any change to existing rows) on the direction it
   touches, expectancy first.
3. Guarantee mechanically that a one-direction change leaves the other
   direction's rows identical.
4. Print the market-regime split per direction on every funnel result.

## Non-goals

- Any change to what the bot scans, plans, alerts on or posts.
- Switching a direction off, shadowing it, or gating alerts on status.
- Any change to the v72 clauses, the v92 harvest gate, v230's additive gate
  or the idea screen. v72 stays in code, callable and byte-identical.
- Re-running or re-judging any closed or open pre-registration. Rows frozen
  under v72 stay under v72, including `MA Ribbon bullish 1w` (v113-B).
- Mapping the funnel to instrument v3 (`V3_FUNNEL_REFUSAL` stays; v230's
  "What follows" item 1 owns it).
- Older bear-market history (2000–2009) for shorts: declined by the partner
  in favour of decision 2.
- A status history table. Status is computed, never stored.

## Anti-goals (a failure even if everything "works")

- A gate chosen because it passes more features. Every threshold below is
  copied from a gate already in the repo (v92, v230) or frozen here before
  any arm is read under it.
- The book gate used to pick a knob value. It describes; selection stays in
  the funnel's Stage 1.
- `PROVEN` shown on the strength of replay alone. The 2021–2023 folds are
  in-sample for every strategy that exists today.
- A per-regime number quoted as a verdict, or a regime cell used to rescue a
  failed shot.
- Long results changing because short work shipped.

## Design

Three parts. Part A and Part C are code in `swingbot/core/backtesting/`;
Part B adds a module there, one endpoint and one panel.

### Part A — the direction gate (`--gate direction`)

`swingbot/core/backtesting/acceptance_direction.py`, selected by
`validate_component.py --gate direction`, beside `harvest` and v230's
`additive`. It reuses `acceptance.py`'s bootstrap, MDE and permutation
machinery, as `acceptance_harvest.py` does.

**Which gate a new pre-registration uses**, from this spec's merge:

| The component arm… | Gate |
|---|---|
| only adds rows (apart from displacement) | `additive` (v230) |
| changes how accepted trades exit, or sizing | `harvest` (v92) |
| removes rows or changes which rows are accepted (a filter, a veto, a knob on entry) | `direction` (this spec) |

`win_rate` (v72) stays the default flag value so every existing command
reproduces its recorded verdict, but **no new pre-registration names it**.
`backtest-methodology.md` says so in a new `## Direction gate` section.

**Scope.** The pre-registration freezes `direction_scope`: `bullish`,
`bearish` or `both`. `measure_arms.py` writes it into the provenance stamp;
`check_stamp` refuses an arm file without it under this gate
(`refused:no-direction-scope`). The **scored rows** are the baseline and
component rows whose `direction` is in scope. Rows with `direction = None`
(pre-v100) are refused, never guessed.

**Clauses.** All on scored rows, all on net R (`r_basis = net`, v230; a
`gross` or missing stamp is refused).

| # | Clause | Instrument | Threshold |
|---|---|---|---|
| 1 | `expectancy_gain` (objective) | paired week-cluster bootstrap ΔExpR | lower 95% bound > 0, one-sided p < 0.05 |
| 2 | `win_rate_floor` | same bootstrap, Δ standardised win rate | lower 95% bound ≥ −2.0pp (`acceptance_harvest.WIN_RATE_FLOOR_PP`) |
| 3 | `volume_floor` | scored-row count, baseline vs component | cut ≤ 25% (`VOLUME_MAX_CUT_PCT`) |
| 4 | `book_total_gain` | paired change in the scored direction's **total** net R (sum, not mean) | point estimate > 0 |
| 5 | `other_direction_identical` | out-of-scope rows, baseline vs component | same keys, same `outcome`, same `r_multiple`; `SKIPPED` when scope is `both` |
| 6 | `mechanism` (subset components) | removed vs retained scored rows | removed ExpR ≤ 0 **and** removed ExpR < retained ExpR |
| 7 | `not_luck` | `permutation_test.py`, n = 200, on ΔExpR | p < 0.05, validation stage only; a missing p is a FAIL |

- **Clause 4 is the promotion rule** (decision 3). A filter can raise mean
  ExpR by cutting volume while the direction earns less in total; the sum
  catches that. v230's `book_net_gain` is the same idea for added rows.
- **Clause 5 is the long-side guarantee.** A leak is a FAIL whose detail
  lists the first ten differing keys. Displacement through the heat or
  one-position rules counts as a leak here: a one-direction filter that
  frees heat for the other direction has changed the other direction, and
  must be registered with scope `both`.
- **Scope `both`** scores clauses 1–4 once per direction and requires:
  clause 1 PASS in at least one direction; in the other, ΔExpR point
  estimate ≥ 0 and clauses 2–4 PASS. Clause 6 runs on the pooled scored
  rows.
- **No geometry lock.** v72's clause 3 existed because a win-rate objective
  can be passed by pulling targets nearer. With expectancy as the objective
  that trade no longer pays; a change that moves geometry on purpose belongs
  to the harvest gate.
- **Week clusters**, following v192 and v230: signals bunch on market days,
  and short signals bunch hardest on sell-off days.

**Stages** are the funnel's, unchanged in shape:

| Stage | Rule under `--gate direction` |
|---|---|
| −1 reachability | as today, plus clause 5 evaluated on the pilot: a scope leak is refused before any shot |
| 0 MDE | `mde_paired` with `delta_expectancy_r` on the **scored rows** at the scored N; refused, budget intact, when the TRAIN effect is below it |
| 1 selection | clauses 1–6 on fold-train; `plateau_report()` mandatory |
| 2 walk-forward | `backtest_wf.gate` (the existing expectancy fold rule) on scored rows: ≥ 2 of 3 folds improving, no fold below `−GATE_MAX_DEGRADATION_R`, per-fold scored N ≥ 30 |
| 3 validation | one shot, all seven clauses |

Stage 3 budget rules are unchanged: a component whose validation shot is
spent under v72 gets no second shot under this gate.

### Part B — the book gate and the direction status

`swingbot/core/backtesting/book_gate.py`. It reads rows and computes; it
never selects.

**Replay side.** Input: the baseline arm of a standard `measure_arms.py`
fold run for the configuration on `main` (`r_basis = net`, folds 2021 /
2022 / 2023). A thin script, `scripts/backtest/book_gate_report.py`, writes
`docs/superpowers/results/direction-books/book-gate.json` plus a Markdown
twin, stamped with `git_head`, `created_at` and the arm file's provenance.
The file is committed, so the admin image carries it. Per direction:

- N, win rate, net ExpR, week-cluster bootstrap 95% interval, pooled over
  the three fold-test years;
- the same per fold;
- total net R, mean cost in R, and for shorts the borrow share of cost;
- the regime table (Part C).

`replay_ok` is true when the pooled lower 95% bound > 0 **and** net ExpR > 0
in ≥ 2 of 3 folds **and** every fold has N ≥ 30.

**Live side.** Input: closed live trades from `journal_entries` joined to
`trades` (the population `scripts/ops/export_book_rows.sh` exports), over
the **trailing 180 days**, manual trades excluded, brought to the same net
basis as replay. Per direction: N, win rate, net ExpR, week-cluster
interval.

`live_ok` is true when N ≥ 100 **and** the lower 95% bound > 0. With
N < 100 the live side reads `INSUFFICIENT` and is not ok.

**Status.**

| `replay_ok` | `live_ok` | Status |
|---|---|---|
| true | true | `PROVEN` |
| anything else | | `UNPROVEN`, with the failing side named |

Both directions are expected to read `UNPROVEN` on the first run. That is
the instrument reporting Finding 1, not a defect.

**Staleness.** The replay file is stale when the commit it was stamped at
is older than the latest release that carries `Bump: bot` work touching
plans or exits. The panel shows the stamp date and `git_head`; refreshing
the file is a step in `/close-out` for any plan whose pre-registration
passed Stage 3 (a promoted feature changes the book).

**Serving.** `GET /analytics/direction-books` (next to
`GET /analytics/registry` in `swingbot/admin/api_v1/analytics.py`) returns
the replay file's per-direction block, the live block computed on request
from the journal, and the status. No table, no migration, no write path.

**Panel.** "Direction books" in the Research workspace
(`frontend/src/app/workspaces/research/`), above "Strategy registry". Two
cards, LONG and SHORT:

```
┌ LONG ─────────────────────── UNPROVEN ┐
│ Replay 2021–23   N 1,840   ExpR −0.02 │
│                  95% [−0.07, +0.03]   │
│                  folds  + − −         │
│ Live 180 days    N 412     ExpR −0.07 │
│                  95% [−0.20, +0.07]   │
│ Fails: replay bound, live bound       │
│ ▸ By market regime                    │
│ Replay as of 2026-11-20 · a1b2c3d     │
└───────────────────────────────────────┘
```

(Numbers illustrative.) Designed for the three widths together
(`docs/claude/ui-design.md`): cards side by side from tablet up, stacked on
phone; the regime table is four rows by four columns (regime, N, win rate,
ExpR) and fits a phone without horizontal scroll; "By market regime" is a
disclosure with a 44px touch target; status is a text badge, never colour
alone. Empty states: no replay file ("No replay book yet"), live
`INSUFFICIENT` ("N 37 of 100 needed"). A one-line caption states that
replay folds are in-sample and that only the live side is untouched
evidence.

### Part C — the regime split

`ArmTrade` gains an optional `regime: str | None = None`, filled by
`arm_trade_from_plan` from `plan.entry_context["regime2_state"]`
(`asof_context.build_asof` already puts it there on replay; live trades
carry it in `risk_features`). It is **not** part of `key` or `stratum`, so
pairing and every existing statistic are unchanged, and old arm files load
as before.

Labels are the four the bot already uses (`edge/regime2.py:REGIMES`):
`bull_quiet`, `bull_volatile`, `bear_quiet`, `bear_volatile`. The partner
spoke of up / down / sideways markets; the existing classifier is used
instead of inventing a third trend state, so replay and live split the same
way as the autopsy.

One renderer, `regime_table(rows)`, prints per direction and regime: N, win
rate, net ExpR, and `thin` beside any cell with N < 30. It is called by the
direction gate's results doc (baseline and component side by side), by the
book gate, and by the panel. Every rendering carries the line
"disclosure only; no cell is a verdict".

## Constraints

- **v230 first.** This spec depends on v230's `r_basis` stamp and net-R arm
  rows, and both specs edit `validate_component.py`, `measure_arms.py` and
  `arms/provenance.py`. The plan is written after v230 is merged, from the
  code as it then stands.
- **Net means the same thing everywhere.** Slippage and commission as
  v230's net arms book them; shorts additionally pay
  `frictions.borrow_r` (`BORROW_RATE_ANNUAL = 0.005`), longs never. The live
  side uses the same cost settings (`scripts/reports/autopsy/rows.py:
  friction_settings` shows where they are read today).
- **Long side unchanged.** No long plan, alert, replay row or v72 verdict
  changes. Pinned by a byte-identical test on a v72 run before and after.
- **v72 reproducibility.** `acceptance.py`'s clauses and `VERSION` are not
  edited; adding `ArmTrade.regime` must leave every existing acceptance test
  green without modification.
- No-lookahead: `regime2_state` at entry uses SPY bars up to the signal bar
  only, as `asof_context` already guarantees.
- Every new or changed function stays under cyclomatic complexity 15.
- `docs/claude/backtest-methodology.md` gains `## Direction gate` and
  `## Book gate`; `AGENTS.md` mirrors the change in the same commit.

## Testing

- Direction gate: one test per clause for PASS, FAIL and the boundary;
  scope `both` rule; refusal on a missing scope stamp, on `direction = None`
  rows, on `gross` arms; a scope leak (one long row differs) fails clause 5
  and names the key; empty scored population is refused, not passed.
- A golden test: one small synthetic arm pair scored under `win_rate` and
  under `direction`, both verdicts pinned.
- Book gate: `replay_ok` and `live_ok` truth tables at each boundary
  (N = 29/30, N = 99/100, bound at 0); a direction with no rows; a fold
  missing; manual trades excluded.
- Regime: `ArmTrade` without `regime` loads; `regime` absent from `key`;
  `regime_table` with an empty regime and with a thin cell.
- Endpoint: shape, no replay file, live `INSUFFICIENT`, auth.
- Frontend: both cards at phone, tablet and desktop widths; each empty
  state; the disclosure toggles; the badge has text.
- New tests join the existing backtesting and admin suites
  (`tests/suites.toml`); a suite past `max_tests` is split by feature.

## Plans

One plan, written after v230 merges, expected in two parts: Parts A and C
(gate, stamp, regime field, methodology text), then Part B (book gate,
report script, endpoint, panel). The first book-gate run is a plan task,
dispatched to `backtest-runner`, checkpointed per ticker.

## Left to the builder

- Whether clause helpers shared with `acceptance_harvest.py` are imported or
  lifted into a small common module.
- The exact JSON shape of `book-gate.json` and the endpoint payload.
- How the live side reaches net R (confirm whether `r_realized` is already
  net; subtract only what is missing).
- The Markdown layout of the results docs.

## Claude's calls, for the partner to check

1. **A sibling module, not an edit to `acceptance.py`.** The partner chose
   "a versioned gate in the funnel". `acceptance.VERSION` already exists and
   is 2, and harvest and additive are sibling modules behind `--gate`; the
   direction gate follows that pattern. Same funnel, same script, old gate
   untouched.
2. **v72 is retired for new pre-registrations**, kept for reproduction.
3. **Geometry lock dropped** from the filter gate, for the reason given in
   Part A.
4. **Thresholds are borrowed, not invented:** −2.0pp win-rate floor (v92),
   25% volume cut (v72), week clusters and total-R clause (v230), the
   existing expectancy fold rule (`backtest_wf.gate`).
5. **Live window: trailing 180 days, N ≥ 100.** The autopsy's whole book is
   320 short and 747 long trades; 180 days keeps the reading on the bot as
   it is now and still reaches N ≥ 100 per direction.
6. **No status table.** In chat I said the status would live in Postgres. A
   committed replay file plus a live computation needs no schema change and
   cannot go out of step with the journal.
7. **Four regime labels, not up / down / sideways**, to match the classifier
   and the autopsy.
8. **Displacement counts as a scope leak** (clause 5).
9. **Panel roles:** quant-researcher, quant-engineer, ux-designer.

## What follows

1. The backtest-to-live realism spec (brainstormed next).
2. New per-direction ideas and exit shapes, after v230's re-screen results.
3. If a direction pays in one regime only: a regime-switch feature for that
   direction, pre-registered under `--gate direction`.

## Parallelisation

- Part A and Part C share `ArmTrade` and the results renderer: sequential,
  C's field first (A's results doc calls `regime_table`).
- Part B's module and report script need A's net-R refusal and C's table:
  after both.
- Endpoint and panel are sequential (the panel consumes the endpoint), and
  parallel to nothing else: a group of one each.
- The first book-gate run needs only Part B's script and can run while the
  panel is built.
