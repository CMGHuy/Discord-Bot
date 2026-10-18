# v174 — Intermarket shock screens: do sharp bond or dollar moves lead stocks?

**Version:** ui 1.27.0 · bot 2.10.0 (at writing)
**Bump:** none — screen tooling and two one-shot screen runs; nothing the bot or admin serves changes.
**Edge:** none (integrity) — the context hook is instrument plumbing, and the two screens are measurements. A `SCREEN-PASS` would license a later `Edge: expectancy` filter spec; this spec claims no edge.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, technical-analyst
**Status:** spec written 2026-10-18 from a brainstorm with the partner (fast-event form, both triggers and the hook approved in chat).

## Why

Murphy's intermarket chapter (developed in *Intermarket Analysis*, 2004)
claims that bonds tend to turn before stocks, and that the dollar's trend
feeds into equities through commodities and multinational earnings. The
bot reads no market except the stock itself and SPY. Nothing in
`preregistration-ledger.jsonl` tests a cross-asset input.

A **slow** intermarket regime (for example "TLT above its 50-day") cannot be
screened today. The Stage −2 matched baseline compares each event with
random bars of the **same ticker, same month and same trend state**
(`screen/null.py:58`). A regime that lasts months is shared by the event and
its baseline, so ΔExpR ≈ 0 by construction. Such a regime would fail
without having been tested. The partner chose the **fast-event** form
instead: a one-day intermarket shock, for which same-month matching is
sound.

Two gaps block even that:

1. Idea modules see one ticker's bars only (`events(df)`, `screen_idea.py:163`).
2. `data/backtest_cache_ext` holds no TLT or UUP (it holds SPY and the PIT
   S&P 500 members).

## Goals

- G1. An idea module can read named context series, point-in-time, with
  every existing idea unchanged byte for byte.
- G2. TLT and UUP daily bars for 2009-01-01..2019-12-31 sit in
  `backtest_cache_ext`. 2009 is warm-up for the 252-day z-score.
- G3. Two ideas, `bond_lead` and `dollar_drop`, are frozen here and each is
  screened **once**, with its ledger row written.

## Non-goals

- No slow-regime screen and no change to the matched baseline, the race
  shapes, the costs or the pass rule (`backtest-methodology.md` § Stage −2).
- No live use of TLT/UUP, and no filter in the scan. A pass buys a later
  spec, not a deployment.
- No re-screen under different parameters. A changed trigger is a new idea
  with a new name (`ideas/__init__.py` docstring).

## Design

### 1. Context hook

An idea module may export `CONTEXT: tuple[str, ...]`. When it does, its
signature is `events(df, context: Mapping[str, pd.DataFrame])`. An idea
without `CONTEXT` keeps `events(df)` and is called exactly as today.

- `Idea` (the registry dataclass in `ideas/__init__.py`) gains
  `context: tuple[str, ...] = ()`.
- `screen_universe` loads each context ticker **once** with the same
  `load_frame` (same window, same cache dir) and passes the frames to every
  `screen_ticker` call. A missing context file is a refusal before any
  ticker runs, never a silent no-event screen.
- **Point in time.** The idea aligns a context series onto the stock's
  dates with an exact date match:
  - A stock date with no context bar on that date is `False`, never
    forward-filled.
  - A context value at t uses context bars dated ≤ t only.
  - A shared helper `context_on(df_index, ctx_series)` does the alignment,
    so both ideas use one rule.
- **Guard.** `tests/backtesting/screen/test_ideas_registry.py` already pins
  every idea. It gains assertions that the six existing ideas have
  `context == ()` and that their `events` output is unchanged on the
  fixture frames.

### 2. Data

A one-off run of `scripts/data/fetch_backtest_data.py` with
`BACKTEST_CACHE_DIR=data/backtest_cache_ext` for `TLT` and `UUP`. The run's
command and the files' first and last dates are recorded in the plan's
results doc. `data/` is not committed; the doc is.

### 3. The two frozen ideas

Both use `RACE = "fixed"` (entry next open, 1.5 × ATR14 stop, 3 × ATR14
target), `CAP = 10`, and long only.
`SOURCE = "Murphy (2004), Intermarket Analysis"`.

Let `r5(t) = close(t) / close(t-5) - 1` on the context series, and
`z(t) = (r5(t) - mean(r5[t-252..t-1])) / std(r5[t-252..t-1])`. Both use the
**trailing** window, excluding t, with population std, and need at least 252
prior `r5` values or return `False`.

| Idea | `CONTEXT` | Event at close of t | `PARAMS` |
|---|---|---|---|
| `bond_lead` | `("TLT",)` | `z_TLT(t) >= +2.0` | `{"series": "TLT", "lookback": 5, "window": 252, "z": 2.0}` |
| `dollar_drop` | `("UUP",)` | `z_UUP(t) <= -2.0` | `{"series": "UUP", "lookback": 5, "window": 252, "z": -2.0}` |

- The event fires for every ticker that is a PIT member on t (the screen's
  existing membership mask) and has a bar on t.
- Overlapping shock days are not de-duplicated. Consecutive z ≥ 2 days are
  each an event, as with every other idea's trigger. The week-clustered
  bootstrap carries the dependence.
- `IDEA_MODULES` appends `"bond_lead", "dollar_drop"` in that order.

### 4. Running the two shots

Each idea runs once:
`python scripts/backtest/screen_idea.py --idea <name> --cache-dir data/backtest_cache_ext`.
The runs follow the `backtest-gate` skill and are dispatched to
`backtest-runner`.

- `screen_idea.py` already refuses a second shot once `screen-<name>`
  exists in the ledger.
- Each run's verdict (`SCREEN-PASS` / `SCREEN-FAIL` /
  `SCREEN-UNDERPOWERED`) and its results doc are committed as they come.
- **Expected:** a few dozen shock days in ten years, so the
  ≥ 7-of-9-years clause bites hard and a fail is the likely outcome. A
  fail is closed and gets no spec.
- A pass is recorded as the licence for a future filter spec. It is not
  wired in anywhere by this plan.

## Testing

- `context_on`:
  - An exact date match.
  - A stock date missing from the context series gives `False`.
  - A context-only date is ignored.
  - Changing a context bar dated after t never changes the event at t.
- z-score: hand-computed fixture values; fewer than 252 prior values gives
  no event; t itself is excluded from the window.
- Registry:
  - Both new ideas are pinned (CAP, RACE, PARAMS, CONTEXT, SOURCE).
  - The six existing ideas have empty context and unchanged events.
- Runner:
  - A missing context file refuses before any ticker runs.
  - Context frames load once per universe, not once per ticker.

## Parallelisation

The hook (§1) comes before the ideas (§3), because the ideas import the
helper. The data fetch (§2) is independent and can run beside §1. The two
screen runs (§4) need §1–§3 merged and run **one after the other**, never in
parallel, because they share the ledger file.
