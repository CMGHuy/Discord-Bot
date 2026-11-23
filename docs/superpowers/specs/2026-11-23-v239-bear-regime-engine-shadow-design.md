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

- `scanning/regime.py` (SPY vs EMA200) is slow. It read "Bullish" on 11-12
  and only feeds `score_confidence`. It never gates.
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
| `swingbot/core/market/bear_regime.py` (new) | Pure classifier: daily SPY + ^VIX frames → `RegimeDay` |
| Postgres | New table `market_regime_days` (Alembic revision), one row per session |
| Scan pass | Computes or reads today's `RegimeDay` once per pass and stamps every new plan's `entry_context` |
| Notify queue | One ops-channel notice per state transition (v197/v210 queue) |
| Discord alerts | One regime line on every alert embed, simple and full |
| Admin API | `GET /api/v1/market/regime` (current day plus last 60 sessions) |
| Frontend | Dashboard regime banner; a regime chip on plan cards |
| Config | `BEAR_REGIME_MODE` (`off` / `shadow` / `live`; `live` behaves exactly like `shadow` in v239) |
| Reports | `scripts/reports/regime_shadow_report.py`: live would-veto vs the rest |
| Research | `scripts/research/regime_base_rates.py` + a results doc: SPY 1993→now state base rates |

Nothing blocks, sizes, scores, re-orders or drops a plan. `off` is a byte-identical kill switch.

## The classifier

Everything is computed from **completed daily bars only**. The day-`t` label
uses closes through session `t−1`. Live, that is the last completed session
before the scan's issue time. It is never today's partial bar
(`no-lookahead` skill).

Let `C` be the SPY close. `SMA50`, `SMA200` are simple means of `C`.
`V` is the ^VIX close.

| Output | Rule |
|---|---|
| `BEAR` | `C < SMA200` **and** `SMA200[t] < SMA200[t−20]`; **or** `SMA50 < SMA200` **and** `C < SMA200` |
| `CORRECTION` | not `BEAR`, and `C < SMA50` **and** `SMA50[t] < SMA50[t−5]` **and** `SMA200[t] > SMA200[t−20]` |
| `NORMAL` | neither |
| `stress` (bool or `None`) | `V ≥ 25`; `None` when the ^VIX bar is missing or older than the SPY bar |
| `pullback_trigger` (bool) | state is `CORRECTION` **and** `V ≤ 0.85 × max(V[t−4..t])` **and** `C > SPY high[t−1]` |

- `BEAR` wins over `CORRECTION`. `CORRECTION` is the "fake" candidate (a dip
  while the long trend still rises), and `BEAR` is the "real" one (the long
  trend itself has turned). The label is a guess until the episode resolves.
  The base-rate study measures how good a guess it is.
- Constants live in module-level `Final`s, not `.env`. Changing one is a new
  idea under the frozen slate rows, not a tuning knob.
- With fewer than 220 SPY bars, every field is `None` and the state is
  `UNKNOWN`. This never raises.
- **This week replayed:** CORRECTION from 10-22, `stress` on 11-17..11-20,
  never BEAR (SMA200 731.7 is still rising). The plan pins this replay as a
  test, from a fixture of real SPY/^VIX closes.

### Shadow action, a pure function of the day and the plan direction

| State | LONG plan | SHORT plan |
|---|---|---|
| `BEAR` | `would_veto` | `aligned` |
| `CORRECTION` + `stress` | `would_veto` | `aligned` |
| `CORRECTION`, no stress | `caution` | `aligned` |
| `NORMAL` / `UNKNOWN` | `none` | `none` |

`pullback_trigger` days add `pullback_watch` to the day row and to the
notice. No plan is created from it in v239: B8 decides that.

## Data and storage

- **Inputs.** SPY daily bars come from the same daily fetch path the scan
  already uses for `MARKET_REGIME_TICKER` (`compression_context.py:112` reads
  it). ^VIX daily comes from that same path. The plan-briefer confirms the
  exact function and that ^VIX daily resolves through it. If it does not, the
  plan adds ^VIX to that fetch, not to `BENCHMARK_SYMBOLS`, which drives the
  benchmark page.
- **`market_regime_days`.** `session_date` (PK, the `t` the label is *for*),
  `state`, `stress`, `pullback_trigger`, `spy_close`, `sma50`, `sma200`,
  `sma50_lag5`, `sma200_lag20`, `vix_close`, `computed_at`. Alembic revision
  `v239_001_market_regime`, following `schema-evolution.md`. Rows are written
  once per session, on the first scan pass after the prior session completes.
  A later pass on the same session reads the row and never rewrites it
  (append-only history; the live/backtest parity check reads it).
- **`entry_context`** gains `bear_regime` (state string) and `regime_action`
  (table above) on every new plan while the mode is not `off`. The key is
  additive. Old records lack it and are never upcast (`schema-evolution.md`).
- **Transition notice.** When today's state, or its `stress` flag, differs
  from the previous row, one event goes to the ops channel through the v197
  notify queue. It carries a plain status embed in the v210 style: headline
  ("Regime: CORRECTION → BEAR"), the numbers line (SPY, SMA50, SMA200, VIX),
  the open-long count, and the footer "Shadow: no long blocked, no short
  issued." A `pullback_trigger` day sends one "pullback watch" notice. Limit:
  one notice per session.

## Surfaces

- **Discord alert line**, on full and simple embeds, every direction, while
  the mode is not `off` and the state is not `NORMAL`/`UNKNOWN`:
  - LONG + `would_veto`: `⚠ Bear regime (shadow): BEAR — the regime engine would not issue this long.`
    In CORRECTION + stress the state word is `CORRECTION · STRESS`.
  - LONG + `caution`: `Regime: CORRECTION (SMA200 still rising) — dip inside an uptrend.`
  - SHORT: `Regime: BEAR — short is with the tape.` (or the CORRECTION form).
  - It is one line, under the plan table and above the disclaimer, and it is
    never truncated away. The `alert-surface` skill's traps apply: wire it in
    both embed builders and pin each with a test.
- **Dashboard banner** on bomeo-capital.com. It is hidden on `NORMAL`. It
  shows state, `stress`, how many sessions the state has lasted, the
  SPY-vs-SMA50/SMA200 distances and VIX. On `pullback_trigger` days it adds a
  "Pullback watch" chip. It sits beside the existing v209 shock pill and
  never replaces it: the pill is intraday crash, the banner is daily trend.
  Phone: one wrapped line under the shell header, with the numbers behind a
  tap. Tablet/desktop: a full-width strip. Touch target ≥ 44 px. Checked at
  three widths (`ui-design.md`).
- **Plan cards** get a small chip: `would veto` (red), `caution` (amber),
  `aligned` (neutral). The chip reads the plan's own stamped `regime_action`,
  not today's state, so an old card keeps the regime it was issued under.
- **API.** `GET /api/v1/market/regime` returns `{today: RegimeDay|null,
  history: RegimeDay[≤60], mode}`. It follows the existing `api_v1` auth.

## Evidence the shadow produces

- **`regime_shadow_report.py`** joins closed main-ledger trades with their
  `entry_context.regime_action`. It prints N, WR, ExpR and sum R for
  `would_veto` vs `caution` vs `none` (LONG) and `aligned` vs `none` (SHORT),
  with a stated N floor below which it prints "too few". It is **live
  monitoring, not a screen.** No figure from it licenses a gate: the B9 screen
  does (`pooled-numbers` skill).
- **Base-rate study** (`regime_base_rates.py`, results doc
  `docs/superpowers/results/2026-11-23-v239-regime-base-rates.md`). It runs
  over SPY + ^VIX daily from 1993 to the last completed session (one fetch
  into the backtest cache, checkpointed per year per CLAUDE.md § Long runs),
  and reports:
  - Episodes per state: count, median and IQR duration.
  - **CORRECTION → BEAR conversion rate**, and how many sessions the switch
    took. Named episodes: 2000, 2008, 2022 converted; 2010, 2011, 2018, 2020
    the plan checks.
  - SPY forward 5/20/60-session returns from each state's first day and from
    `pullback_trigger` days.
  - The same table split by `stress`.

  This tells the partner how much the "fake" label deserves to be trusted. It
  is a description of SPY, not a strategy result, and it moves no gate.

## Config

`BEAR_REGIME_MODE`: a `select` in the config schema, section "Market Shock" or
a new "Bear Regime" section, default `shadow`. `off` means no row, no stamp,
no line, no notice, banner hidden. `live` is identical to `shadow` until a
screened follow-on spec, and its help text says so. An unknown value falls
back to `off`, mirroring `MARKET_SHOCK_MODE` (`config.py:1593`).

## Rollback

Set `BEAR_REGIME_MODE=off` (SIGHUP hot reload). The table stays; dropping it is
a separate downgrade revision and is never needed for rollback.

## Non-goals

- Blocking any long, issuing any new short, or creating a pullback plan. B9,
  B7 and B8 decide those, through screen v2 (slate order step 6).
- VIX term structure (B1, needs ^VIX3M). Breadth (v209 already owns it).
- Changing `regime.py`, `score_confidence` or the v209 machine.
- Tuning the classifier constants on live results.

## Risks

- **The label lags.** SMA200 slope turns late. 2022 would have read
  CORRECTION for weeks before BEAR. The base-rate study quantifies the lag.
  The banner says "Correction (dip in uptrend)", never "safe".
- **Data gaps.** A missing ^VIX bar gives `stress=None`. The line then omits
  stress and never assumes calm. A stale SPY bar gives `UNKNOWN`, never the
  prior day's label.
- **Alert-line noise.** In a long CORRECTION every long alert carries the
  line. That is the point: the partner trades from these alerts.
- **Shadow drift from the screen.** B9 must use these exact state rules. A
  parity test replays `bear_regime.classify` on the backtest cache and
  compares it with stored `market_regime_days` rows for the same sessions.

## Testing

- Pure classifier: each rule boundary, BEAR-over-CORRECTION precedence,
  `UNKNOWN` under 220 bars, `stress=None` on a missing or stale VIX,
  `pullback_trigger` only in CORRECTION, the 10-22..11-20 replay fixture, and
  a no-lookahead test (appending a future bar never changes day `t`).
- Store: write-once per session, read-back, migration up/down.
- Scan wiring: the stamp is present in shadow and absent in off; `off`
  leaves `entry_context` byte-identical.
- Embeds: every state × direction line in both builders; the length budget
  stays intact.
- Notice: transition-only, one per session, pullback-watch event.
- API: shape, empty table, auth.
- Frontend: banner per state including hidden on NORMAL, chip per action,
  and three-width layout specs.
- Reports: the shadow report on fixture trades incl. the N floor; the
  base-rate script on a small synthetic series with known episodes.
