# v174 — Intermarket shock screens: do sharp bond or dollar moves precede stock gains?

**Version:** ui 1.27.0 · bot 2.10.0 (at writing)
**Bump:** none — screen tooling and two one-shot screen runs; nothing the bot or admin serves changes.
**Edge:** none (integrity) — the context hook is instrument plumbing, and the two screens are measurements. A `SCREEN-PASS` would license a later `Edge: expectancy` filter spec; this spec claims no edge.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, technical-analyst
**Status:** spec written 2026-10-18 from a brainstorm with the partner (fast-event form, both triggers and the hook approved in chat); revised the same day after the panel, and the partner chose to keep both ideas under honest labels (see `## Panel review`).

## Why

Murphy's intermarket work (*Intermarket Analysis*, 2004) claims that bonds
tend to turn before stocks, and that the dollar's trend feeds into equities.
The bot reads no market except the stock itself and SPY. Nothing in
`preregistration-ledger.jsonl` tests a cross-asset input.

A **slow** intermarket regime (for example "TLT above its 50-day") cannot be
screened today. The Stage −2 matched baseline compares each event with
random bars of the **same ticker, same month and same trend state**
(`screen/null.py:58`). A regime that lasts months is shared by the event and
its baseline, so ΔExpR ≈ 0 by construction. The partner chose a
**fast-event** form instead: a sharp 5-day move in a context series.

Two gaps block even that:

1. Idea modules see one ticker's bars only (`events(df)`, `screen_idea.py:163`).
2. `data/backtest_cache_ext` holds no TLT or UUP.

### What the two shots can and cannot say

The panel was clear, and the partner agreed, that these are **proxies**,
not Murphy's claim itself:

- **`bond_spike_rebound` is not "bonds lead stocks."** In 2010–19 a 5-day
  TLT z ≥ +2 rally was mostly a flight-to-quality day (Aug 2011, Aug 2015,
  Jan 2016, Feb 2018), which practitioners read as risk-off. Going long
  stocks the next day therefore tests **a rebound after a risk-off bond
  spike**: close to mean reversion after a market-wide selloff, a family
  where `uptrend_pullback` already holds a SCREEN-PASS. The idea is named
  for what it tests. The bearish Murphy reading (falling bonds → weak
  stocks) cannot be screened, because the races are long-only.
- **`dollar_drop` is closer to Murphy** (a falling dollar is bullish for
  equities), but it is a lagged proxy for a trend claim. A dollar drop
  often accompanies a risk-on rally already under way.
- **Only one horizon is tested.** A 10-bar fixed race measures immediate
  drift, while Murphy's lead runs over weeks to months.
- **A fail closes exactly the frozen definition** (series, 5-day z, the
  ±2.0 threshold, long-only, the fixed 10-bar race) and nothing broader:
  not intermarket analysis, not a slow-regime test, not a bearish or
  longer-horizon variant. The ledger row and the results doc carry that
  wording.

### Feasibility, counted before freezing

The panel asked for these counts. They come from TLT/UUP adjusted closes
only (no stock outcome read), with a 2009 warm-up:

| Idea | Shock days 2010–19 | Episodes (runs > 5 sessions apart) | Years 2011–19 with an event |
|---|---|---|---|
| `bond_spike_rebound` | 68 | 24 | 8 of 9 (none in 2017) |
| `dollar_drop` | 57 | 28 | 9 of 9 |

Both can satisfy the ≥ 7-of-9-years clause, but `bond_spike_rebound` can
afford only one weak year, and 2012 and 2013 rest on a single episode each.
**Each screen is in effect a test of ~25 episodes, not ~30 000 events.** One
shock day fires every member (~500), so the `N ≥ 300` clause cannot catch
the small sample. A fail is the likely outcome and is no refutation of
Murphy.

## Goals

- G1. An idea module can read named context series, point-in-time, with
  every existing idea unchanged byte for byte on the real call path.
- G2. TLT and UUP adjusted daily bars for 2009-01-01..2019-12-31 sit in
  `backtest_cache_ext`, and are fetched once, before either shot.
- G3. Two ideas, `bond_spike_rebound` and `dollar_drop`, are frozen here
  and each is screened **once**, with its ledger row and a results doc
  reporting the diagnostics in §5.

## Non-goals

- No change to the matched baseline, the race shapes, the costs or the pass
  rule (`backtest-methodology.md` § Stage −2). The §5 diagnostics are
  printed and **never gate**.
- No slow-regime screen and no bearish screen.
- No live use of TLT/UUP, and no filter in the scan. A pass buys a later
  spec, not a deployment.
- No re-screen under other parameters. A changed trigger is a new idea with
  a new name (`ideas/__init__.py` docstring).

## Design

### 1. Context hook

An idea module may export `CONTEXT: tuple[str, ...]`. When it does, its
signature is `events(df, context: Mapping[str, pd.DataFrame])`. An idea
without `CONTEXT` keeps `events(df)` and is called with exactly one
argument, as today.

- `Idea` (the registry dataclass in `ideas/__init__.py`) gains
  `context: tuple[str, ...] = ()`.
- `screen_ticker` gains a keyword-only `context: Mapping | None = None`.
  The call dispatch is table-driven on `bool(idea.context)` so
  `screen_ticker` stays under complexity 15 (`code-complexity.md`).
- `screen_universe` loads each context ticker **once** and passes the
  frames to every `screen_ticker` call.
- **Context window.** A context frame is loaded from `CONTEXT_START =
  "2009-01-01"` to the screen's `WINDOW_END`. This is its own start, not
  the stock `WINDOW_START`, so 5 + 252 bars of warm-up exist before
  `EVENT_START` (2011-01-01). The results doc records both starts.
- **Load checks: refuse before any ticker runs, and before any ledger
  write, if any of these fail.**
  - The file is missing.
  - The index is not sorted, not unique, or not tz-naive and normalised
    like `load_frame`'s output (`screen_idea.py:60`).
  - The file is missing any SPY session between `CONTEXT_START` and
    `WINDOW_END`. This contiguity check guards `r5`'s row offset, and it
    also catches thin early UUP bars.
  - Defined z-scores cover fewer than 95% of SPY sessions in the event
    window (2011-01-01..2019-12-31).
- **Point in time.** One shared helper, `context_on(df_index, series)`,
  aligns a context series onto the stock's dates by exact date:
  - A stock date with no context value is `False`, never forward-filled.
  - A value at t depends only on context bars dated ≤ t.

### 2. Data

A one-off run of `scripts/data/fetch_backtest_data.py` with
`BACKTEST_CACHE_DIR=data/backtest_cache_ext` for `TLT` and `UUP`.

- Closes are **adjusted** (`yf.download(auto_adjust=True)`, the script's
  existing call at `fetch_backtest_data.py:99`), so TLT's monthly
  distributions do not enter `r5`.
- The results doc records the fetch date, row counts, first and last
  dates, and a SHA-256 of each CSV.
- **No refetch between the two shots.** Adjusted history is restated at
  fetch time, so the second shot must read the same bytes as the first. A
  hash mismatch at the second run is a refusal.

### 3. The two frozen ideas

Both use `RACE = "fixed"` (entry next open, 1.5 × ATR14 stop, 3 × ATR14
target), `CAP = 10`, and long only.
`SOURCE = "Murphy (2004), Intermarket Analysis — shock proxy, see v174 § What the two shots can and cannot say"`.

On the context series:
- `r5(t) = close(t) / close(t-5) - 1`, with the row offset made sound by
  the contiguity check.
- `z(t) = (r5(t) - mean(W)) / std(W)`, where `W = r5[t-252..t-1]`. The
  window is **trailing** and excludes t; std is the population std.
- z is `False` (no event) when W has fewer than 252 values, any value in W
  or `r5(t)` is NaN, or `std(W) == 0`. The gate ends in `.fillna(False)`.

| Idea | `CONTEXT` | Event at close of t | `PARAMS` |
|---|---|---|---|
| `bond_spike_rebound` | `("TLT",)` | `z_TLT(t) >= +2.0` | `{"series": "TLT", "lookback": 5, "window": 252, "z": 2.0, "side": "long"}` |
| `dollar_drop` | `("UUP",)` | `z_UUP(t) <= -2.0` | `{"series": "UUP", "lookback": 5, "window": 252, "z": -2.0, "side": "long"}` |

- The event fires for every PIT member with a bar on t.
- Consecutive trigger days are each an event. A 5-day return makes them
  come in runs.
- `IDEA_MODULES` appends `"bond_spike_rebound", "dollar_drop"` in that
  order.

### 4. Running the two shots

Each idea runs once:
`python scripts/backtest/screen_idea.py --idea <name> --cache-dir data/backtest_cache_ext`.

- The runs follow the `backtest-gate` skill and go to `backtest-runner`.
- They run **one after the other**, since they share the ledger file.
- `screen_idea.py` already refuses a second shot once `screen-<name>`
  exists.
- Each verdict and results doc is committed as it comes.
- A pass is the licence for a future filter spec only.

### 5. Diagnostics in each results doc (printed, never gating)

1. **Effective sample:** shock days, episodes, distinct ISO weeks, and
   events per year, beside the ticker-event N. A note says the
   week-clustered percentile bootstrap undercovers with this few clusters,
   so the lower bound is looser than nominal.
2. **Null overlap:** ΔExpR recomputed with the null pool restricted to bars
   at least `CAP` sessions from any shock day. This shows how far
   pre-shock and post-shock null races moved the official figure.
3. **Selloff confound:** SPY's own `r5` on shock days, and ΔExpR split by
   SPY `r5 < 0` vs `≥ 0`. A pass carried by the `< 0` half is a
   mean-reversion effect, not an intermarket one.
4. **Concentration:** ΔExpR contribution per shock episode, sorted, so a
   verdict carried by one or two episodes (for example August 2011) says
   so.
5. **Multiple comparisons:** the ledger BH q-value (`ledger_qvalues` /
   `bh_qvalues`, `instrument/stats.py`), with the family being these two
   ideas plus all prior screen rows.
6. **Scope sentence**, copied into the ledger row's note: the
   frozen-definition wording from § What the two shots can and cannot say.

## Testing

- `context_on`:
  - An exact date match.
  - A stock date missing from the context gives `False`.
  - A context-only date is ignored.
  - Changing a context bar dated after t never changes the event at t.
- z:
  - Hand-computed fixture values.
  - t is excluded from W.
  - Fewer than 252 values, NaN inside W, a NaN `r5(t)` and `std(W) == 0`
    each give `False`.
- Load checks, each refusing before any ticker or ledger write:
  - A missing file.
  - A tz-aware index.
  - An unsorted index.
  - A missing SPY session.
  - Defined-z coverage below 95%.
- Data: the second-shot hash mismatch refuses.
- Registry:
  - Both new ideas are pinned (CAP, RACE, PARAMS, CONTEXT, SOURCE).
  - The six existing ideas have `context == ()`.
- Real call path: `screen_ticker` for each existing idea gives an identical
  `TickerScreen` before and after the change, and their `events` receive
  exactly one argument.
- Runner: context frames load once per universe, not once per ticker.
- Diagnostics: each of §5's six outputs appears in a results doc built
  from a fixture universe.

## Parallelisation

- §1 (hook) comes before §3 (ideas), because the ideas import
  `context_on`.
- §2 (data) is independent and runs beside §1.
- §5 (diagnostics) needs §1 only.
- The two shots (§4) need §1–§3 and §5 merged, and run serially, because
  they share the ledger.

## Panel review

2026-10-18. The three roles ran serially on commit `d91cd4f4`.

- quant-engineer [BLOCKING]: context loaded with the stock window, so the
  2009 warm-up was never read -- applied: its own `CONTEXT_START`, recorded
  in the results doc.
- quant-engineer [BLOCKING]: adjusted vs raw closes not pinned, and a
  refetch could restate history -- applied: adjusted pinned, fetch
  date/rows/SHA-256 recorded, and a refetch between shots refuses.
- quant-engineer [BLOCKING]: unguarded z denominator -- applied: NaN or
  std 0 gives `False`, with `.fillna(False)` and tests.
- quant-engineer: the r5 row offset across file gaps -- applied: a
  contiguity check against SPY sessions.
- quant-engineer: byte-identity tested on fixtures only -- applied: a
  real-call-path `TickerScreen` parity test and table-driven dispatch.
- quant-engineer: the `screen_ticker` seam was unnamed, with a tz-mismatch
  risk -- applied: a keyword-only `context` parameter and
  normalisation checks.
- quant-engineer: a file present but yielding no z still spends a shot --
  applied: a 95% defined-z coverage refusal.
- technical-analyst + quant-researcher: a TLT spike is risk-off, and long
  after it is a selloff rebound, not Murphy's lead -- applied: renamed
  `bond_spike_rebound`, with an honest scope section. The partner chose to
  keep both ideas over dropping this one.
- technical-analyst: the long-only direction is a limitation -- applied:
  stated, with the bearish form named as untestable.
- technical-analyst: `dollar_drop` is a lagged proxy, and early UUP bars
  may be thin -- applied: scope wording and the contiguity check.
- technical-analyst + quant-researcher: a fail over-claims -- applied: a
  fail closes the frozen definition only, and the scope sentence goes into
  the ledger note.
- technical-analyst + quant-researcher: record the feasibility and the
  odds -- applied: the feasibility table and "a fail is the likely
  outcome".
- quant-researcher: null-pool overlap with the shock window -- applied as
  a printed diagnostic. The baseline itself is unchanged (Non-goals).
- quant-researcher: effective N is shock days or episodes, so
  UNDERPOWERED can never fire -- applied: stated in Why, printed in §5.1.
- quant-researcher: few week clusters undercover -- applied: the
  distinct-week count and an undercoverage note are printed.
- quant-researcher: the SPY selloff confound -- applied: the §5.3 split.
- quant-researcher: the BH family is unstated -- applied: §5.5.
- quant-researcher: per-episode concentration -- applied: §5.4.
- quant-researcher: point-in-time alignment belongs to quant-engineer --
  no change; covered by that role's findings.
