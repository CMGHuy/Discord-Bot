# v239 — Bear-regime engine (shadow): correction vs bear, would-veto longs, pullback watch

**Version:** ui 1.45.0 · bot 2.19.5
**Bump:** bot minor, ui minor (every alert gains a regime line the partner reads before placing orders; a new dashboard banner on bomeo-capital.com)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** veteran-trader, quant-engineer, ux-designer

## Why

From the 11-13 close to the 11-20 close SPY fell **8.6%**. It closed below its
SMA200 from 11-18 on and finished 11-20 at its low, while VIX went 19.3 → 37.6.
In the window 11-16..11-23 the live main ledger closed **74 LONG trades: WR
14.9%, ExpR −0.39R, −29.1R**. It closed 26 SHORT trades at +0.15R (+3.9R). The
bot issued **73 bullish plans out of 101**, all from the confluence source.
Only 2 of 90 watchlist names rose that week. Figures and the query:
`docs/superpowers/results/2026-11-20-bear-market-slate.md`, addendum 2026-11-23.

The partner's goal, 2026-11-23:

1. Identify a bear market or a sharp downtrend, and stop issuing LONG trades.
2. Tell a fake decline from a real one. If it is fake, prepare for the
   pullback buy. If it is real, issue SHORT trades.

The bot has two regime signals today, and neither does this.

- `swingbot/core/scanning/regime.py` (SPY vs EMA200) is slow. It read
  "Bullish" on 11-12 and only feeds `score_confidence`. It never gates.
- The v209 shock detector (`MARKET_SHOCK_MODE`, shadow) measures **intraday
  breadth crashes** and walks a NORMAL → SHOCK → RECOVERY machine. This week was
  a grind, not a single crash day: **73 of the 74 closed longs carry
  `entry_context.shock_state = NORMAL`**. A daily trend regime is the missing
  layer.

The repo's rules decide how the actions arrive. A live long veto needs a
screen pass (`backtest-methodology.md` § Stage −2, avoid mode); `REGIME_ALLOW`
(v17) was closed negative. Single-name shorts are a closed route in every
form tried so far (slate §3). So, partner ruling 2026-11-23: **shadow first,
gate per screen.** This spec builds the classifier and runs it live in
shadow. It labels every alert, shows the state on Discord and the site, and
records what it *would* do. Each action goes live only through a follow-on
spec that cites its own screen row. The three actions are frozen as slate
rows B7 (bear-state short), B8 (correction-release long) and B9 (regime long
veto) in the slate doc above.

## What changes

| Area | Change |
|---|---|
| `swingbot/core/market/bear_regime.py` (new) | Pure classifier: completed daily SPY + ^VIX frames → `RegimeDay` |
| Postgres | New table `market_regime_days` (Alembic revision), one row per labelled session |
| Scan pass | Computes or reads today's `RegimeDay` once per pass and stamps every new plan's `entry_context` |
| Notify queue | One ops-channel notice per confirmed state transition (v197/v210 queue) |
| Discord alerts | One regime line on every alert embed, simple and full |
| Admin API | `GET /api/v1/market/regime` (current day plus last 60 sessions) |
| Frontend | Dashboard regime banner; a regime chip on plan cards |
| Config | `BEAR_REGIME_MODE` (`off` / `shadow` / `live`; `live` behaves exactly like `shadow` in v239) |
| Reports | `scripts/reports/regime_shadow_report.py`: live would-veto vs the rest |
| Research | `scripts/research/regime_base_rates.py` + a results doc: SPY state base rates, 1993 → 2026-11-20 |

Nothing blocks, sizes, scores, re-orders or drops a plan. `off` is a byte-identical kill switch.

## The classifier

### Indexing

The label is **for** trading session `D`, the first NYSE session after the last
completed one. Every input is a completed daily bar. Let `s` be the last
completed session before `D` (the bar index of the input frame's last row).
Every rule below indexes from `s`: `C[s]` is the last completed SPY close,
`C[s−1]` the one before it. Nothing reads a bar dated `D` or later.

- **Live cut.** The live frame from `get_daily_data`
  (`swingbot/core/marketdata/data.py:39`) can end in today's partial bar
  (v209 spec, "Track 1"). The engine passes every frame through the existing
  `completed_frame(df, now)` (`swingbot/core/scanning/strategy_pass.py:33`)
  before classifying. A test feeds a frame that ends in a partial bar and
  asserts the label equals the label of the same frame cut by hand.
- **Calendar.** `D` and `s` come from the NYSE session calendar the refresher
  already uses (`swingbot/refresher/benchmarks.py:65`,
  `last_completed_session`). A Saturday or Sunday scan, a holiday, a half-day
  session, and a scan after the close but before the refresher ran each map to
  one defined `(s, D)` pair, with one test per case. A half-day session counts
  as completed after its early close.
- **Replay convention.** The slate's "CORRECTION from 10-22" means
  `D = 2026-10-22`, i.e. labelled from `s = 2026-10-21`'s close. The replay
  fixture uses this convention.

### Rules

`C` is the SPY close. `SMA50`, `SMA200` are simple means of `C`. `H` is the
SPY high. `V` is the ^VIX close. All are evaluated at `s` unless lagged.

| Output | Rule |
|---|---|
| `BEAR` | `C[s] < SMA200[s]` **and** `SMA200[s] < SMA200[s−20]`; **or** `SMA50[s] < SMA200[s]` **and** `C[s] < SMA200[s]` |
| `CORRECTION` | not `BEAR`, and `C[s] < SMA50[s]` **and** `SMA50[s] < SMA50[s−5]` **and** `SMA200[s] > SMA200[s−20]` |
| `NORMAL` | neither |
| `UNKNOWN` | fewer than 220 SPY bars; **or** any NaN or non-finite value among the closes feeding `SMA200[s−20..s]`, or in `C[s]`/`H[s−1]`; **or** the SPY frame's last bar is not session `s` (stale) |
| `stress` | `V[s] ≥ 25`. `None` when no ^VIX bar is dated exactly `s`, or `V[s]` is NaN |
| `pullback_trigger` | state is `CORRECTION` **and** `V[s] ≤ 0.85 × max(V[s−4..s])` **and** `C[s] > H[s−1]`. `False` when any of the five VIX bars is missing or NaN, and the row records `pullback_reason = "vix_gap"` |

- `BEAR` wins over `CORRECTION`. `CORRECTION` is the "fake" candidate (a dip
  while the long trend still rises), and `BEAR` is the "real" one (the long
  trend itself has turned). The label is a guess until the episode resolves.
  The base-rate study measures how good a guess it is.
- ^VIX bars are aligned to SPY bars by exact session date. A VIX bar is
  never forward-filled.
- Closes are **adjusted** (dividends and splits) in both the live path and
  the study, the same series the scan's daily frames carry. The row records
  `provider` and `last_bar_date`, so a later revision is explainable (see
  Parity).
- Constants live in module-level `Final`s, not `.env`. Changing one is a new
  idea under the frozen slate rows, not a tuning knob.
- **The day label is raw.** No hysteresis is applied to `state`, so B7–B9
  screen exactly these rules. Smoothing applies only to what a person reads:
  the transition notice, the banner's "since" count and study episodes (see
  Confirmed transitions).
- **This week replayed:** CORRECTION from `D = 10-22`, `stress` on
  `D = 11-17..11-20`, never BEAR (SMA200 731.7 still rising). The plan pins
  this replay as a test, from a fixture of real SPY/^VIX closes.

### Confirmed transitions

A state change is **confirmed** when the new state (or the new `stress` value)
holds on two consecutive labelled sessions. A run shorter than two sessions is
flicker. It is stored in the day rows as it happened, never notified, and in
the study it is merged into the surrounding episode. A run that reaches two
sessions becomes the episode and starts its "since" count on its first day.

### Shadow action, a pure function of the day and the plan direction

| State | LONG plan | SHORT plan |
|---|---|---|
| `BEAR` | `would_veto` | `aligned` |
| `CORRECTION` + `stress` | `would_veto` | `aligned` |
| `CORRECTION`, no stress | `caution` | `aligned` |
| `NORMAL` / `UNKNOWN` | `none` | `none` |

On a `pullback_trigger` day the LONG action is **`pullback_watch`**, and it
wins over `would_veto`. That day is, by construction, the panic easing inside
a correction, which is exactly what B8 measures. Telling the partner "would
not issue" and "pullback watch" on the same day would contradict itself. No
plan is created from the trigger in v239. B8 decides that.

## Data and storage

- **Inputs.** SPY and ^VIX daily via `get_daily_data`
  (`swingbot/core/marketdata/data.py:39`), the same router path the scan's
  `MARKET_REGIME_TICKER` frame comes from
  (`swingbot/core/scanning/compression_context.py:99-112`), then
  `completed_frame`. The plan's first task confirms ^VIX resolves through it
  on the router (yfinance or Alpaca). If it does not, the plan adds a ^VIX
  route to that path, never to `BENCHMARK_SYMBOLS` (which drives the
  benchmark page). The study reads the backtest cache. Parity covers the gap
  between the two.
- **`market_regime_days`.** Columns: `session_date` (PK, = `D`), `last_bar_date`
  (= `s`), `state`, `stress`, `pullback_trigger`, `pullback_reason`,
  `spy_close`, `sma50`, `sma200`, `sma50_lag5`, `sma200_lag20`, `spy_high_prev`,
  `vix_close`, `vix_max5`, `provider`, `computed_at`. Alembic revision
  `v239_001_market_regime`, following `schema-evolution.md`.
- **Write once, race-free.** The first scan pass that finds no row for `D`
  computes the day and runs `INSERT … ON CONFLICT (session_date) DO NOTHING`.
  Only the process whose insert succeeded enqueues a notice. Every later pass,
  in any process, reads the row. A row is never updated.
- **Gaps.** If the VM missed sessions, the engine labels only `D`; it never
  backfills. The transition check compares against the most recent stored
  row whatever its age. If that row is older than 5 sessions, the notice says
  "after a gap of N sessions" so a stale comparison is visible.
- **`entry_context`** gains `bear_regime` (state string) and `regime_action`
  (table above) on every new plan while the mode is not `off`. The key is
  additive. Old records lack it and are never upcast (`schema-evolution.md`).
- **Transition notice.** On a *confirmed* transition (or a `pullback_trigger`
  day) one event goes to the ops channel through the v197 notify queue, at
  most one per session. It carries a plain status embed in the v210 style:
  - Headline in the shared vocabulary (Surfaces), e.g. "Regime: Correction →
    Bear".
  - The numbers line, in the shared number form.
  - The open-long count and the count of **unfilled bullish plans** issued
    under the old state, listed one per line (ticker, entry). Someone with
    resting orders can then decide on them.
  - Footer: "Shadow: no long blocked, no short issued, no plan cancelled."

## Surfaces

### One vocabulary, one number form

| State | Short label (chip, banner title) | Plain words |
|---|---|---|
| `BEAR` | `Bear` | trend has turned down |
| `CORRECTION` + stress | `Correction · Stress` | dip in an uptrend, high volatility |
| `CORRECTION` | `Correction` | dip in an uptrend |
| pullback day | `Pullback watch` | panic easing inside a correction |
| `UNKNOWN` | `No reading` | — |

Numbers always use one form: SPY as a signed % from each average, then VIX as
a level, e.g. `SPY −5.7% vs SMA200 · −9.3% vs SMA50 · VIX 37.6`. The banner,
the notice and the API's display fields all use it. No glyphs (⚠ etc.) in any
surface, so plain-text channels render the same.

### Discord alert line

This is one line on full and simple embeds, every direction, while the mode is
not `off` and the state is `BEAR` or `CORRECTION`. It sits **directly under
the plan table, above the chart image and the disclaimer**. It is **at most 80
characters**, a cap each state × direction case asserts in the embed tests.

| Case | Line |
|---|---|
| LONG `would_veto` | `Regime: Bear (shadow) — engine would skip this long` |
| LONG `would_veto`, stress | `Regime: Correction · Stress (shadow) — would skip long` |
| LONG `caution` | `Regime: Correction — dip in an uptrend` |
| LONG `pullback_watch` | `Regime: Pullback watch — panic easing in a correction` |
| SHORT `aligned` | `Regime: Bear — with the tape; squeeze risk on rebounds` |

The shadow wording says what the engine *would* do and gives no order
instruction. The bot never advises on a placed order, and the plan remains a
valid plan. The `alert-surface` skill's traps apply: wire the line in both
builders (`build_embed`, `build_strategy_alert_embed`/`_simple_embed` in
`alert_embeds.py`) and pin each with a test.

### Dashboard banner (bomeo-capital.com)

- **States.**
  - Hidden on `NORMAL`, `mode = off`, while loading, and on a fetch error. A
    fetch error logs to the console and shows nothing, never a stale label.
  - On `UNKNOWN` it shows a muted single line, "Regime: no reading", and
    never the prior day's label.
  - Otherwise it shows the short label, "since N sessions" (confirmed-episode
    count) and the number form.
  - On a pullback day it adds a `Pullback watch` chip.
- **Control.** The collapsed banner is a real `<button>` with `aria-expanded`
  and keyboard activation. Its accessible name carries the label and the
  numbers, e.g. "Regime Correction, stress, 6 sessions; SPY −5.7% vs SMA200".
  Expanding shows the number line and one sentence of plain words.
- **Neighbours, per width.** The v209 shock pill is phone-only
  (`frontend/src/app/shell/shock-pill.ts`, hidden from 640 px). Wider screens
  carry SHOCK/RECOVERY in the tape strip.
  - **Phone (<640 px):** banner directly under the top bar, below the shock
    pill. The two read as "intraday: Shock" / "trend: Correction". The banner
    prefixes "Trend:" so a SHOCK pill above a Correction banner reads as two
    signals, not a contradiction.
  - **Tablet/desktop:** a full-width strip directly under the tape strip,
    same "Trend:" prefix.
  - Touch target ≥ 44 px at every width.

### Plan-card chip

- Reads the plan's own stamped `regime_action`, never today's state, so an old
  card keeps the regime it was issued under.
- `would skip` (red, with a `×` text prefix), `caution` (amber, `!` prefix),
  `pullback watch` (blue, `↺` prefix), `aligned` (neutral, no prefix). Colour
  is never the only cue.
- A legacy card without the key, or with action `none`, shows **no chip**.
- Placement: on the card's meta row after the direction badge. It wraps onto
  its own line on a phone and is never truncated.

### API

`GET /api/v1/market/regime` returns `{mode, today: RegimeDay|null, history:
RegimeDay[≤60], episode: {label, since_sessions}|null}`, with `display` strings
in the shared vocabulary and number form. It follows the existing `api_v1`
auth. An empty table gives `today: null, history: []`.

## Parity

A parity test replays `bear_regime.classify` on the backtest cache for every
stored `market_regime_days` row in a fixture export, and compares states.

- **Tolerance.** A replayed `state` must equal the stored one, except on a
  **boundary day**: one where any compared quantity
  (`C − SMA200`, `C − SMA50`, `SMA200[s] − SMA200[s−20]`,
  `SMA50[s] − SMA50[s−5]`, `SMA50 − SMA200`, `V − 25`) is within 0.1% of the
  right-hand side. A boundary day mismatch is reported, not failed.
- **Explaining a mismatch.** The row's `provider` and `last_bar_date` say which
  input it saw. A non-boundary mismatch fails the test and prints both input
  closes.
- **No rewrite.** Stored rows are what the partner saw. A revised close never
  rewrites a row.

## Evidence the shadow produces

- **`regime_shadow_report.py`** joins closed main-ledger trades with their
  `entry_context.regime_action`. It prints N, WR, ExpR and sum R for
  `would_veto` vs `caution` vs `pullback_watch` vs `none` (LONG) and `aligned`
  vs `none` (SHORT). Below N = 30 a row prints "too few". It is **live
  monitoring, not a screen.** No figure from it licenses a gate: the B9 screen
  does (`pooled-numbers` skill).
- **Base-rate study.** Script `scripts/research/regime_base_rates.py`, results
  doc `docs/superpowers/results/2026-11-23-v239-regime-base-rates.md`.
  - **Window:** first labelled session (1993-01-29 + 220 SPY bars) through
    **2026-11-20**, fixed. Data: SPY and ^VIX daily, adjusted, from one fetch
    into the backtest cache. The script refuses to run if the cache files'
    SHA-256 differs from the hashes it recorded at its first run. Command,
    end date and hashes go into the results doc. Checkpointed per year
    (CLAUDE.md § Long runs).
  - **Episodes:** confirmed runs per the rule above.
  - **Reports:**
    - Episodes per state: count, median and IQR duration.
    - **CORRECTION → BEAR conversion rate**, and how many sessions the switch
      took, with each named episode's outcome: 2000, 2008, 2022 (expected to
      convert) and 2010, 2011, 2018, 2020 (to be checked).
    - SPY forward 5/20/60-session returns from each episode's first day and
      from `pullback_trigger` days.
    - The same table split by `stress`.
  - It describes SPY, not a strategy. It moves no gate.

## Config

`BEAR_REGIME_MODE`: a `select` in the config schema, new section "Bear Regime",
default `shadow`. `off` means no fetch, no row, no stamp, no line, no notice,
banner hidden. `live` is identical to `shadow` until a screened follow-on
spec, and its help text says so. An unknown value falls back to `off`,
mirroring `MARKET_SHOCK_MODE` (`swingbot/config.py:1593`).

## Rollback

Set `BEAR_REGIME_MODE=off` (SIGHUP hot reload). The table stays; dropping it is
a separate downgrade revision and is never needed for rollback.

## Non-goals

- Blocking any long, issuing any new short, cancelling a plan, or creating a
  pullback plan. B9, B7 and B8 decide those, through screen v2 (slate order
  step 6).
- VIX term structure (B1, needs ^VIX3M). Breadth (v209 already owns it).
- Changing `regime.py`, `score_confidence` or the v209 machine.
- Tuning the classifier constants on live results.

## Risks

- **The label lags.** SMA200 slope turns late. 2022 would have read
  CORRECTION for weeks before BEAR. The base-rate study quantifies the lag.
  The banner never says "safe".
- **Data gaps.** A missing ^VIX bar gives `stress = None`. The line then omits
  stress and never assumes calm. A stale SPY bar or a NaN gives `UNKNOWN`,
  never the prior day's label.
- **Alert-line noise.** In a long CORRECTION every long alert carries the
  line. That is the point: the partner trades from these alerts.
- **Shorts read as encouraged.** `aligned` describes the tape, not the trade.
  The SHORT line carries a squeeze caveat. Borrow and fees stay the
  partner's call, as they are today.
- **Shadow drift from the screen.** B9 must use these exact raw rules. See
  Parity.

## Testing

- **Classifier:**
  - each rule boundary and BEAR-over-CORRECTION precedence
  - `UNKNOWN` under 220 bars, on an injected NaN, and on a stale SPY frame
  - `stress = None` on a missing or misdated VIX bar
  - `pullback_trigger` only in CORRECTION, `False` with `vix_gap` on a VIX
    hole, and `C[s] > H[s−1]` firing on a crafted series
  - the `D = 10-22 .. 11-20` replay fixture
  - no-lookahead: appending a bar after `s` never changes the label for `D`
  - a frame ending in a partial bar equals the hand-cut frame
- **Calendar:** weekend, holiday, half-day and after-close-before-refresher
  cases.
- **Store:** insert-once under two concurrent writers (exactly one notice),
  read-back, migration up/down, a gap of more than 5 sessions in the notice
  text.
- **Transitions:** single-session flicker stores but never notifies; a
  two-session run notifies once; a pullback day notifies.
- **Mode `off`, byte-identical:** `entry_context`, embed bytes for both
  builders, and no `market_regime_days` write and no fetch during a scan
  pass.
- **Embeds:** every state × direction line in full and simple embeds,
  ≤ 80 characters, placed under the plan table.
- **API:** shape, empty table, `mode = off`, auth.
- **Frontend (unit):**
  - the banner in each state (hidden on NORMAL, off, loading and error;
    "no reading" on UNKNOWN)
  - the banner's keyboard toggle and `aria-expanded`
  - the chip for each action, legacy cards without a chip, and the text
    prefixes
- **Layout:** banner and chip checked at phone, tablet and desktop with
  `node frontend/scripts/layout-audit.mjs` (Playwright only), incl. phone
  wrapping of the chip and the pill + banner stack.
- **Reports:** shadow report on fixture trades incl. the N = 30 floor; the
  base-rate script on a synthetic series with known episodes and flicker,
  and its hash refusal.

## Code reconciliation (plan brief, 2026-11-23)

The plan brief (`.superpowers/briefs/2026-11-23-v239-bear-regime-engine-shadow.md`)
checked every named symbol. Where it disagrees with the text above, this
section wins.

1. **^VIX source.** `is_alpaca_eligible("^VIX")` is False, so `get_daily_data`
   serves ^VIX from yfinance only (`auto_adjust=True`). SPY goes Alpaca
   first. No `data.py` change is needed. `provider` is recorded per symbol:
   `spy_provider`, `vix_provider`.
2. **Calendar.** `completed_frame` is weekday-only. The live `(s, D)` pair
   comes from the half-day-aware `session` helpers (`is_nyse_regular_session`,
   `last_regular_close`, `is_early_close`; calendar 2018–2030), applied on
   top of `completed_frame`. The 1993 study derives sessions from the SPY bar
   index, not the calendar.
3. **Study data.** No local cache holds SPY from 1993 or ^VIX through
   2026-11-20. The pinned `_ext` cache is never refetched. A first plan task
   fetches SPY and ^VIX daily, 1993-01-01 → 2026-11-20, into a new
   `data/backtest_cache_regime/`, records the hashes, and creates
   `scripts/research/`.
4. **Table contract.** `market_regime_days` also carries `doc` (JSONB) and
   `updated_at`, per `schema.contract_violations`. It needs `register()`, a
   `PROMOTION_REASONS` entry, and a row in
   `tests/db/test_unknown_field_round_trip.py`. Alembic `down_revision` is
   the current head at implementation time (`v228_001` when briefed).
5. **Notify kind.** A new kind `bear_regime` joins `lifecycle_events.KINDS`
   and its validator, with a dispatch beside `market_shock` in
   `lifecycle_notifications`.
6. **Embed builders.** The line goes on every *alert* builder:
   - `build_embed`: a field appended to `sections["plan"]`, above the image
     and the disclaimer footer.
   - `build_simple_alert` and `_legacy_simple_alert`.
   - `build_strategy_alert_embed`: after the Ledger field.
   - `build_strategy_simple_embed`: in the description, because it has no
     fields.

   The execution ticket (`build_ticket_embed`) is out of scope. One more
   line, missing above: SHORT `aligned` in CORRECTION reads
   `Regime: Correction — short in a dip; uptrend intact`. Legacy
   `build_embed` (complexity E) and `_sync_run_scan` (F) each get one
   unconditional helper call, no new branch.
7. **Stamping.**
   - `regime_action` is derived in `stamp_entry_context`, where the plan
     direction is in scope, beside `shock_asof`
     (`swingbot/core/planning/params.py:221`).
   - `attach_plan_v2` gets no branch.
   - `trade_why.WIRE_CONTEXT_KEYS` gains `bear_regime` and `regime_action`,
     so the SPA receives them.
8. **Frontend placement.**
   - The "dashboard banner" lives in the **app shell** (`shell.html`), so it
     shows on every route, under the top bar on a phone and under
     `.tape-strip` from 640 px.
   - The "plan-card chip" goes on the direction/tag rows of `trade-detail.ts`
     and `plan-detail.ts`, not `trades/plan-card.ts` (the order panel).
9. **Tests and access.**
   - `tests/scanning` (1111/1200) and `tests/scripts` (1163/1200) are near
     their caps, so new tests go in a new `tests/regime/` directory, which
     joins one suite in `tests/suites.toml`.
   - The new viewer GET adds an `access_expectations.py` row.

## Panel review

Spec review, 2026-11-23, on c344f1f9. Every finding was applied in this
revision.

- veteran-trader 1: `C > H[t−1]` can never fire, because `C` is already
  `t−1`. **Applied:** all rules index from `s`, and the trigger is
  `C[s] > H[s−1]` with a firing test.
- veteran-trader 2 / quant-engineer: the VIX max window included bar `t`.
  **Applied:** `max(V[s−4..s])`.
- veteran-trader 3: a pullback day contradicts a would-veto line.
  **Applied:** `pullback_watch` wins over `would_veto`.
- veteran-trader 4: the shadow line gives no instruction. **Applied:** the
  wording says what the engine would do. The bot never advises on placed
  orders, and the spec says so.
- veteran-trader 5: the notice ignores resting entries from the old state.
  **Applied:** the notice lists unfilled bullish plans issued under the old
  state.
- veteran-trader 6: `aligned` encourages shorts. **Applied:** squeeze caveat
  on the SHORT line, and a Risks entry.
- quant-engineer 1 (BLOCKING): the partial bar is not removed live.
  **Applied:** `completed_frame` cut, plus a partial-bar test.
- quant-engineer 2 (BLOCKING): write-once rows vs a replay with revised
  adjusted closes. **Applied:** `provider`/`last_bar_date` stored, adjusted
  closes on both sides, boundary-day tolerance, no rewrite.
- quant-engineer 3 (BLOCKING): no NaN rule. **Applied:** a NaN or non-finite
  input gives `UNKNOWN`, with a test.
- quant-engineer 4: VIX alignment and gaps. **Applied:** exact session-date
  match, no forward fill, `vix_gap` reason.
- quant-engineer 5: weekend, holiday and half-day mapping. **Applied:**
  `(s, D)` from `last_completed_session`, one test per case, and the replay
  convention stated.
- quant-engineer 6: write and notice race; gaps. **Applied:** `ON CONFLICT DO
  NOTHING`, notice only from the winning insert, no backfill, gap text.
- quant-engineer 7: no hysteresis. **Applied:** raw day label (screen parity),
  with two-session confirmation for notices, the banner count and study
  episodes.
- quant-engineer 8: study reproducibility. **Applied:** fixed end
  2026-11-20, hashes, command, refusal on hash change.
- quant-engineer 9: fetch path unconfirmed. **Applied:** named `get_daily_data`
  + `completed_frame` with full paths; ^VIX routing is confirmed in task 1.
- quant-engineer 10: `off` is pinned only on `entry_context`. **Applied:**
  embeds, DB writes and fetches pinned too.
- ux-designer 1: disclosure semantics. **Applied:** `<button>`,
  `aria-expanded`, accessible name, keyboard test.
- ux-designer 2: the pill is phone-only. **Applied:** per-width neighbours and
  a "Trend:" prefix.
- ux-designer 3: incomplete banner states. **Applied:** loading, error, off,
  UNKNOWN and null are all defined and tested.
- ux-designer 4: chip legacy case, colour-only cue, layout audit.
  **Applied:** no chip on legacy cards, text prefixes, placement, layout
  audit.
- ux-designer 5: no length number. **Applied:** an 80-character cap per line,
  asserted, and the placement stated.
- ux-designer 6: vocabulary and glyphs. **Applied:** one vocabulary table, no
  glyphs.
- ux-designer 7: number form. **Applied:** one signed-% form everywhere.
