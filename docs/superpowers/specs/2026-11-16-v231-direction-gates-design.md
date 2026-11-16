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

Live closed trades, exits 2026-07-20 to 2026-11-16, read from the autopsy
(not re-derived here). Net is the autopsy's modelled net (5 bps slippage a
fill plus commission; live rows store gross R only). Total R is N × ExpR.

| Cell | N | Win rate | Gross ExpR | Net ExpR | Net total R |
|---|---|---|---|---|---|
| `direction=bearish` | 320 | 50.0% | −0.069 | −0.136 | about −44R |
| `direction=bullish` | 747 | 42.3% | +0.004 | −0.067 | about −50R |

The window overlaps the 2026 holdout, so these rows are exploratory (v161
boundary 5) and select nothing.

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

**No closed knob returns as a direction slice.** A knob that sits in
`backtest-methodology.md` § Closed pre-registrations, or that failed or was
refused at any v72 stage, is closed under this gate in every scope. The
funnel already prints per-direction ΔExpR for every past run
(`arms/selection.py:_direction_disclosure`), so a narrower scope on an old
knob would be a scope chosen after TRAIN was read. For a new knob the scope
is frozen in the pre-registration **before** any per-direction number for
that knob exists; `validate_component.py` refuses `--gate direction` when
the stamp's `preregistration` id already has a ledger row under another gate
(`refused:knob-already-judged`).

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
| 1 | `expectancy_gain` (objective) | paired week-cluster bootstrap ΔExpR | lower bound of the two-sided 95% interval > 0 (one-sided α = 0.025) |
| 2 | `win_rate_floor` | same bootstrap, Δ standardised win rate | lower 95% bound ≥ −2.0pp (`acceptance_harvest.WIN_RATE_FLOOR_PP`) |
| 3 | `volume_floor` | scored-row count, baseline vs component | cut ≤ 25% (`VOLUME_MAX_CUT_PCT`) |
| 4 | `book_total_gain` (guard) | paired change in the scored direction's **total** net R (sum, not mean), same bootstrap | point estimate > 0; the interval is printed beside it |
| 5 | `other_direction_identical` | out-of-scope rows, baseline vs component | same keys, same `outcome`, same `r_multiple`; `SKIPPED` when scope is `both` |
| 6 | `mechanism` (subset components) | removed vs retained scored rows | removed ExpR ≤ 0 **and** removed ExpR < retained ExpR |
| 7 | `not_luck` | permutation on ΔExpR over scored rows, n = 1,000, seed 42 (null below) | p < 0.05, validation stage only; a missing p is a FAIL |

- **Clause 4 is the promotion rule** (decision 3), and a guard rather than a
  second test. For a pure subset it follows from clause 6. For a component
  that changes rows it stops a change that lifts mean ExpR while the
  direction earns less in total. v230's `book_net_gain` is the same idea for
  added rows.
- **Clauses 3 and 4 pull against each other on purpose.** In a losing
  direction the filter most likely to pass clauses 1 and 4 removes many
  rows; clause 3 caps the cut at 25%. A filter that needs to remove more
  than a quarter of a direction is a decision to switch that direction off,
  which decision 3 and the non-goals rule out. It is not a gate outcome.
- **Clause 5 is the long-side guarantee.** A leak is a FAIL whose detail
  lists the first ten differing keys. On the standard arm path each
  (ticker, horizon) is replayed independently, with no portfolio heat or
  one-position rule, so the clause catches a code change that reaches the
  other direction's plans, not displacement. Displacement through heat
  exists only live and in the heat-aware replay; it is a known limit of
  this clause, stated in every results doc, and Part B's live side is where
  it would show.
- **Clause 7's null is frozen here.** Subset component: remove the same
  number of scored rows at random within each `(strategy, horizon_key)`
  stratum; p is the share of draws whose ΔExpR is at least the observed
  one. Component that changes rows: flip the sign of each week cluster's
  paired R difference; same p. No other instrument is substituted, and
  `scripts/backtest/permutation_test.py:arm_pair_permutation` (ΔWR, refuses
  changed outcomes) is not used by this gate.
- **Scope `both`** scores clause 1 **once, on the pooled scored rows**, so
  the objective gets one test. Each direction must then separately show a
  ΔExpR point estimate ≥ 0 and pass clauses 2–4. Clause 6 runs on the pooled
  scored rows.
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
| 0 MDE | `mde_paired` with `delta_expectancy_r` on the **scored rows** at the scored N, `cluster="week"` and one-sided α = 0.025 (the test clause 1 really applies, not the module default of ticker clusters at 0.05); refused, budget intact, when the TRAIN effect is below it |
| 1 selection | clauses 1–6 on fold-train; `plateau_report()` mandatory |
| 2 walk-forward | `backtest_wf.gate` (the existing expectancy fold rule) on fold rows **rebuilt from scored rows only**: ≥ 2 of 3 folds improving, no fold below `−GATE_MAX_DEGRADATION_R`, per-fold scored N ≥ 30. Scope `both`: the rule runs on the pooled scored rows, and each direction needs N ≥ 30 in every fold |
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

**`replay_ok` can withhold a status, never support one.** The folds are
in-sample, every promoted feature was selected on them, and each refresh
after a promotion makes the replay book more flattering. The file records
how many pre-registrations have passed Stage 3 on these folds since
instrument v1's windows were set, and the panel prints that count.

**Reproducible.** The file records, besides `git_head` and the arm file's
provenance: `code_hash`, `r_basis`, universe, the data-cache snapshot date,
bootstrap seed and resample count, fold years and every threshold used.
`book_gate_report.py` refuses a dirty tree, and `--verify` recomputes the
file from its arm file and fails on any difference. The run that produces
the arm file checkpoints per fold × ticker; a restart skips finished units
and the JSON is assembled only from the checkpoint files.

**Live side.** Input: live trades from `journal_entries` joined to `trades`
(the population `scripts/ops/export_book_rows.sh` exports), manual trades
excluded. It is evaluated only at **completed month-ends**, never "now", so
a page load is not another look at the hypothesis:

- window: trades **entered** in the 180 days before the month-end and
  closed by it. Trades entered in the window and still open are counted and
  shown, not scored. (Selecting by close date would favour trades that
  resolve fast.)
- net R through the same function replay uses (Constraints).
- per direction: N, win rate, net ExpR, week-cluster interval (week of
  entry, as replay; fixed seed), and the **live MDE**: the ExpR that would
  clear "lower bound > 0" with 80% power at this N and week-cluster design
  effect.

A month-end snapshot is ok when N ≥ 100 **and** the lower 95% bound > 0.
With N < 100 it reads `INSUFFICIENT`. `live_ok` is true when the **last two
completed month-ends** are both ok. Snapshots are recomputed from the
journal on request and are deterministic; nothing is stored.

On sample size: the autopsy window above is about 120 days and holds 320
short and 747 long closed trades, so 180 days reaches N ≥ 100 per direction
at the current alert rate. The printed live MDE tells the reader whether
`PROVEN` is reachable at all at that N.

**Status.**

| `replay_ok` | `live_ok` | Status | Badge text |
|---|---|---|---|
| true | true | `PROVEN` | PROVEN |
| any | false, a snapshot `INSUFFICIENT` | `UNPROVEN` | UNPROVEN · not enough live trades |
| anything else | | `UNPROVEN` | UNPROVEN · with the failing side named |

Both directions are expected to read `UNPROVEN` on the first run. That is
the instrument reporting Finding 1, not a defect.

The 2026 live book is holdout data (v161 boundary 5). The live side
describes the book; no knob, scope or threshold is chosen from it, and a
pre-registration never cites a live cell as its evidence.

**Staleness.** The replay file is stale when the commit it was stamped at
is older than the latest release that carries `Bump: bot` work touching
plans or exits. The panel shows the stamp date and `git_head`; refreshing
the file is a step in `/close-out` for any plan whose pre-registration
passed Stage 3 (a promoted feature changes the book).

**Serving.** `GET /analytics/direction-books` (next to
`GET /analytics/registry` in `swingbot/admin/api_v1/analytics.py`) returns
the replay file's per-direction block, the live block (the last two
month-end snapshots, their window bounds and as-of dates), the status and a
`stale` flag. No table, no migration, no write path.

**Panel.** "Direction books" in the Research workspace
(`frontend/src/app/workspaces/research/`), as the first panel, above
"Strategy registry" (the status of each direction is the context for the
registry below it; the page's `h1` and disclaimer are unchanged). Two
cards, LONG and SHORT. Each card is a labelled list, one label above its
figures, so nothing depends on a fixed character width:

```
LONG book                    [UNPROVEN · replay and live below zero]

Replay, 2021–2023 (in-sample; can only withhold a status)
  N 1,840 · net ExpR −0.020 R · 95% −0.070 to +0.030
  2021 +   2022 −   2023 −

Live, 180 days to 2026-10-31
  N 412 (9 still open) · net ExpR −0.070 R · 95% −0.200 to +0.070
  Detectable at this N: +0.150 R
  Previous month-end: not ok

▸ By market regime
Replay as of 2026-11-10 · a1b2c3d · STALE: refresh after the last release
```

(Numbers illustrative.) Rules, per `docs/claude/ui-design.md`:

- **Layout by container, not viewport.** The two cards sit side by side
  when the panel is at least 36rem wide and stack below that (`@container`),
  so the rail and the docked live column cannot squeeze them. Inside a card
  the figure row wraps. No horizontal scroll at 390, 768 or 1440; the layout
  audit exits 0 at all three and the route is in `ROUTES`
  (`layout-audit-lib.mjs`).
- **Own async state.** The panel has its own `sb-async` and its own store
  call, outside the ledger's wrapper. Loading skeleton; error with retry;
  a failure or a missing replay file never blanks the registry or the
  ledger, and theirs never hides this panel.
- **Empty states say what to do:** no replay file ("No replay book yet. Run
  `book_gate_report.py`."); live `INSUFFICIENT` ("N 37 of 100 needed");
  a regime with no rows shows "none" in its row.
- **Staleness is text.** A `STALE` chip beside the replay stamp with what
  to do, using `sb-async`'s `staleAsOf` pattern. The live block carries its
  own as-of date (the month-end).
- **Status and folds are legible without colour.** The badge is text and
  names the reason. Folds read "2021 +", never bare glyphs. The card has an
  `aria-label` ("LONG book, UNPROVEN"); the disclosure is a button with
  `aria-expanded`, keyboard reachable, 44px target.
- **Numbers.** `.num` / `--font-num`; ExpR with three decimals through the
  same `figure(x, 3)` the ledger uses, signed, unit "R"; intervals as "a to
  b"; a null is "—". The panel caption reads "Figures in R, net of costs,
  pre-tax", because the registry below shows gross.
- **Regime table** inside the disclosure: a four-row `dl` grid (regime, N,
  win rate, net ExpR), no pager; a thin cell carries the word "thin".
- **The in-sample caption sits under the replay heading**, wraps and is
  never truncated.

Whether the word `PROVEN` overstates a bootstrap interval to a reader is a
`financial-advisor` question, raised at pre-close-out.

### Part C — the regime split

`ArmTrade` gains an optional `regime: str | None = None`. It is **not** part
of `key` or `stratum`, so pairing and every existing statistic are
unchanged, and old arm files load as before (`ArmTrade(**row)`).

**One labelling function for replay and live.** The label is
`regime2.regime_series(spy_df)` (price only) read at the trade's **signal
bar date**: the last completed daily bar at or before the signal. It is
joined onto rows after they are built, by date:

- replay: in `measure_arms.py`, after the engines return, from the SPY
  frame the run already loads. The arm engines are not changed. (The arm
  path calls `replay_scenarios` without an as-of map, so
  `entry_context["regime2_state"]` is empty there; passing one in would
  change engine signatures for a disclosure.)
- live: the book gate labels each journal trade the same way from its
  plan's creation date. It does **not** read the stored
  `risk_features.regime2_state`, because live `classify` breaks near-ties
  with breadth and replay has no breadth history. The live block reports
  how many trades' stored label differs from the price-only one.

A row whose date has no SPY bar is `unknown` and gets its own table row.
`book_gate_report.py` refuses when more than 5% of a direction's rows are
`unknown`.

Labels are the four the bot already uses (`edge/regime2.py:REGIMES`):
`bull_quiet`, `bull_volatile`, `bear_quiet`, `bear_volatile`. The partner
spoke of up / down / sideways markets; the existing classifier is used
instead of inventing a third trend state.

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
- **Net means the same thing everywhere: one function.** Replay rows and
  live journal rows reach net R through the same function, the one v230's
  net arms use. Slippage and commission as it books them; shorts
  additionally pay `frictions.borrow_r` (`BORROW_RATE_ANNUAL = 0.005`) over
  the days held, longs never. Net R is computed where the plan and its exit
  are known (the engine for replay, the journal row for live), so `ArmTrade`
  needs no price or holding-day fields. Live rows store gross R
  (`journal.py`, `metrics.r_multiple`), so the live side always applies the
  function; `book-gate.json` and the endpoint record the basis of each
  side. A parity test replays a fixed sample of closed live trades through
  the function and pins the result. If v230 lands without borrow in its net
  function, this spec adds it there, for shorts only.
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
- Direction gate, added by review: `refused:knob-already-judged`; clause 7's
  two nulls on a seeded fixture; Stage 0 uses week clusters at α = 0.025;
  Stage 2 fold rows built from scored rows only.
- Book gate: `replay_ok` and `live_ok` truth tables at each boundary
  (N = 29/30, N = 99/100, bound at 0); one ok month-end is not `live_ok`;
  window by entry date with an open trade counted and unscored; a direction
  with no rows; a fold missing; manual trades excluded; `--verify` on an
  altered file; a dirty tree refused; repeat calls give the same interval.
- Net parity: the fixed sample of live trades through the shared net
  function; a short pays borrow, a long does not.
- Regime: an old-format arm file and the v68 golden fixture load and score
  unchanged; `regime` absent from `key`; replay and live give the same
  label for the same date; a tie-band date where the stored live label
  differs is counted; `unknown` above 5% refused; `regime_table` with an
  empty regime and with a thin cell.
- Endpoint: shape, no replay file, live `INSUFFICIENT`, stale flag, auth.
- Frontend, extending `research.spec.ts` (its store mocks gain a third
  call): the two cards with **different** statuses; loading, error with
  retry, no replay file, `INSUFFICIENT`, stale; a panel failure leaves the
  registry and ledger rendered and the reverse; keyboard toggle and
  `aria-expanded` on the disclosure; 44px target; fold labels carry years;
  the layout audit at 390, 768 and 1440.
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
- The Markdown layout of the results docs.
- The formula behind the printed live MDE, provided it uses the week-cluster
  design effect and 80% power.

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
5. **Live window: 180 days by entry date, N ≥ 100, read at month-ends, two
   in a row for `PROVEN`.** The month-end rule came from review: a status
   recomputed on every page load would cross the line by chance sooner or
   later.
6. **No status table.** In chat I said the status would live in Postgres. A
   committed replay file plus a live computation needs no schema change and
   cannot go out of step with the journal.
7. **Four regime labels, not up / down / sideways**, to match the classifier
   and the autopsy.
8. **Clause 5 cannot see heat displacement** on the standard arm path; it is
   stated as a limit rather than built around.
9. **Panel roles:** quant-researcher, quant-engineer, ux-designer.
10. **No old knob comes back under this gate**, in any scope (from review).
    This is stricter than "closed rows stay closed": a knob that merely
    failed an early v72 stage is also out.
11. **Regime labels are joined by date with the price-only classifier** on
    both sides, so replay and live tables cannot disagree; the stored live
    label is only compared, never used.

## Panel review (2026-11-16)

quant-researcher (1 blocking, 11 advisory):

- BLOCKING: a closed or v72-judged knob could return as a one-direction
  slice, scope picked after TRAIN -- applied: "No closed knob returns",
  `refused:knob-already-judged`.
- Scope `both` gave clause 1 two chances -- applied: clause 1 once on the
  pooled scored rows.
- Clause 7 named an instrument that does not exist for ΔExpR on filter
  arms -- applied: both nulls frozen in Part A.
- Clause 1's "p < 0.05" was redundant and Stage 0's MDE used another alpha
  and cluster -- applied: one-sided 0.025, week clusters, both stages.
- Clause 4 a point estimate presented as a rule -- applied: named a guard,
  interval printed.
- Clauses 3 and 4 pull against each other -- applied: stated as intended.
- `live_ok` recomputed on every request -- applied: month-end snapshots,
  two in a row.
- No power statement for `live_ok` -- applied: live MDE printed; N basis
  cited from the autopsy window. A trailing-180-day count from
  `journal_entries` -- rejected: not derived in this spec; the first
  book-gate run prints it.
- Close-date window favours fast trades -- applied: window by entry date,
  open trades counted.
- Replay folds drift optimistic with each promotion -- applied: "can
  withhold, never support", promotion count recorded.
- Stage 2 population undefined per direction -- applied.
- Finding 1 table without window, basis or total R -- applied.

quant-engineer (3 blocking, 6 advisory):

- BLOCKING: `regime2_state` is empty on the arm path -- applied: label
  joined by date in `measure_arms.py`, engines untouched, `unknown` cap.
- BLOCKING: live `classify` uses breadth, replay does not -- applied: both
  sides use the price-only series; differences counted.
- BLOCKING: live and replay net bases only asserted equal -- applied: one
  net function, parity test, basis recorded.
- New field and stale fixtures or hashes -- applied: old-format and golden
  fixture tests; `code_hash` recorded.
- Clause 5's displacement case cannot fire on the arm path -- applied:
  text corrected, limit stated.
- `book-gate.json` not reproducible from its stamp -- applied: recorded
  fields, `--verify`, dirty tree refused.
- Checkpoint unit unspecified -- applied: fold × ticker.
- Live side non-deterministic -- applied: month-end as-of, fixed seed,
  week of entry.
- Label timing between replay and live -- applied: signal bar date on both
  sides, same-date test.

ux-designer (3 blocking, 7 advisory):

- BLOCKING: fixed-width card would clip on a phone -- applied: labelled
  list, container query, layout audit.
- BLOCKING: panel inside the ledger's `sb-async` could be hidden by, or
  blank, its neighbours -- applied: own async state and store call.
- BLOCKING: fold glyphs and card unlabelled -- applied: year labels,
  `aria-label`, `aria-expanded`.
- Hand-built regime table -- applied: `dl` grid, "thin" as text, "none".
- Number formatting -- applied.
- Staleness had no display; mock date in the future -- applied.
- `UNPROVEN` could not tell "no" from "not enough data"; caption placement
  -- applied: badge text names the reason; caption under the replay
  heading. The wording of `PROVEN` itself -- deferred to `financial-advisor`
  at pre-close-out.
- Thin frontend testing line -- applied.
- Viewport breakpoint for side-by-side cards -- applied: 36rem container.
- Panel placed above the registry -- applied: confirmed and stated.

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
