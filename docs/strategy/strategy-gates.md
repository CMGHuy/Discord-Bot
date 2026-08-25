# Strategy — gates and filters

The measured gates that decide whether a qualifying setup is allowed to alert, plus symbol resolution.

Part of the strategy documentation — index at [strategy.md](strategy.md).

## Market regime filter

Checks a benchmark index (default SPY) against its 200-day EMA to
classify the broad market as bullish/bearish (`!regime` anytime). Feeds
into confidence scoring for alignment.

## Relative strength gate (measured, and ON)

Relative strength versus SPY had always been advisory — it fed a ranking
score and had never stopped an alert. A 2026-08 spec (v34) asked whether it
should, and the answer that came back was narrower than the question:

**Bearish setups only.** A short is dropped unless the ticker's combined
relative strength sits **at or below the 25th percentile** of the watchlist
(`RS_LAGGARD_PERCENTILE`, `swingbot/core/edge/rs_gate.py`). Requiring a short
to be a genuine relative laggard — not merely below the median — is the
condition under which the bearish arm stopped being the *worst* part of the
book. It does not make it a good one: shorts remain unprofitable on the
window that decided this release (see below).

**Bullish setups are not gated at all.** `RS_LEADER_PERCENTILE` ships at `0`,
which structurally disables that half: a percentile is never negative, so
every bullish setup passes. This is not an oversight to be tuned later. A
bullish gate measured **negative at every threshold tested** on TRAIN
(55/60/65/70/75 cost 28.6%-58.3% of alert volume for −0.16 to −3.80pp of win
rate), and it flipped sign when the lookback or the sector blend changed. The
gate is asymmetric because the data is.

**What it reads is a blend, not the bare ticker percentile.** `rs_combined` is
70% the ticker's own cross-sectional RS percentile and 30% its sector ETF's
(`rs_score()` / `sector_rs_percentile()` in `swingbot/core/edge/factors.py`,
wired into the scan by `_apply_sector_rs`). The scan side-fetches the sector
ETFs its watchlist touches for this. The blend was measured against ticker-only
RS rather than assumed better, and it won at every threshold on both arms — so
the sector wiring stayed. If a ticker's sector or its ETF is unavailable, the
blend falls back to the ticker-only percentile for that ticker alone.

**Exemptions are not passes.** The verdict is tri-state — `pass` / `block` /
`exempt`. FX, futures, indices and crypto are exempt because RS versus SPY is
not a meaningful comparison for them, and so is any scan where the RS
benchmark itself failed to compute (a scan-wide SPY/RS-cache failure). Only a
genuine `block` ever drops a scenario; "we could not run the comparison" is
never recorded as agreement.

**Known gap: a single ticker's own thin history is not exempt.** The
exemption above only fires on a scan-wide RS failure, not on a per-ticker
one. `rs_percentile()` (`edge/factors.py`) returns the synthetic median
`50.0` — not `None` — when a ticker has too little history (under ~64 bars)
for a real reading, and the gate's `rs_available` signal
(`item.rs_combined is not None`) can't see that: it is only ever `False` on
the scan-wide failure, never on this per-ticker sentinel case. So a ticker
with too little history to actually compute RS reaches the gate as an
*available* 50.0 reading, judged exactly as if it were a genuine median —
which a bearish setup at the 25 laggard threshold cannot pass (50 > 25) and
so gets blocked by a comparison that was never really run. This is disclosed
in the VALIDATION numbers (2 "synthetic-50" rows out of 2804 scenarios) —
VALIDATION measured the gate exactly as shipped, sentinel case included —
and is left as a known, documented gap rather than patched here, since
plumbing real per-ticker availability would change decision-making behavior
VALIDATION never measured.

**Per-horizon RS lookback windows exist in the config and are not used.**
`HORIZONS[hk]["rs_window"]` is defined for all ten horizons, but nothing reads
it: the scan computes one RS percentile per ticker on the flat 63-day
`RS_WINDOW` and every horizon shares it. This is a **known gap, not a working
feature** — do not read the per-horizon key as live behaviour. It was measured
anyway as a candidate and came back *worse* than the flat window, so there is
no case for wiring it in without a fresh pre-registered measurement.

**What VALIDATION actually said.** The one-shot run over 2024-2025 (2804
scenarios) came back **PASS**: win rate **48.50% → 49.66%, +1.17pp**, for a
**4.07%** cut in alert volume, with expectancy rising +0.403 → +0.434. All ten
horizons moved the same way, on cuts between 2.9% and 5.4%.

Three things temper that, and they are the reason `RS_GATE` is described here
as a small improvement rather than an edge:

- **The confidence intervals overlap** ([46.3, 50.7] → [47.4, 51.9]). The
  improvement is a point estimate that is *not* statistically demonstrated.
- **It is mostly a statement about one strategy.** Only 4 of 11 strategies
  produce bearish signals at all, and **75.3%** of the bearish population is
  RSI Divergence. The gate is not strategy-neutral, whatever the pooled number
  looks like.
- **Shorts are still not profitable in that window**, merely less unprofitable:
  the bearish arm goes 23.70% → 30.00% and its expectancy −0.275 → −0.229. The
  pooled gain comes from removing the worst shorts, not from making shorts win.

Turn it off with `RS_GATE=false`. Numbers, the frozen thresholds and the
pre-registered PASS rule they were judged against:
`docs/superpowers/plans/implemented/v34-train-preregistration.md`.

## Horizon-to-horizon trend alignment (measured, and OFF)

A 2026-08 spec (v33) asked whether a setup that fights the *next horizon
up* is worth alerting -- e.g. a `2w` bullish setup while the `4w` trend is
bearish. Two checks were built and tested (`swingbot/core/market/mtf.py`),
and each horizon's trend is read from **its own** `HORIZONS` EMA pair, not
from a shared 50/200 proxy:

- **Adjacent-horizon gate** (`MTF_ADJACENT_GATE`, **default off**) -- would
  drop a scenario outright when the next horizon up trends against it.
  `9m` is *exempt*: there is no horizon above it, so it is never gated.
- **6m macro anchor** -- reads a shorter horizon's setup against the 6m
  trend ("agrees with the 6m bullish trend" / "⚠️ counter to the 6m bearish
  trend"). `6m`-`9m` are *exempt*: a horizon cannot anchor to itself or to
  something shorter.

**An exemption is not a pass.** Both checks return `exempt` / `aligned` /
`opposed` as three distinct verdicts, and only a genuine `opposed` ever
means anything: "we could not tell" is never recorded as agreement.

**Neither ships as behaviour.** The macro anchor is worth **0 points**: its
lift was measured rather than assumed, and the measurement came back at
zero. It lives in the factor registry built by the v32 merged-score
experiment described above, which is *itself* off by default
(`UNIFIED_CONFIDENCE`) -- so on the default configuration it does
not run at all, and if you turn that registry on it contributes information
to the breakdown and nothing to the score. The
adjacent gate's one-shot VALIDATION run (2024-2025, 2804 scenarios) showed
a small win-rate **regression**, −0.51pp with fully overlapping confidence
intervals, for a 6.6% cut in setups, so it stays off by default and the
scoring described above remains the live description. It is left in place as
an option you can enable, not as a recommendation. Numbers and the
pre-registered PASS rule they were judged against:
`docs/superpowers/plans/implemented/v33-train-preregistration.md`.

## Ticker symbol resolution

Common aliases (`SPX`→`^GSPC`, `XAUUSD`→`GC=F`, `EURUSD`→`EURUSD=X`, etc.)
resolve automatically. `!watchlist add` validates immediately and warns
if a symbol can't be resolved.

## Command hints

Mistype a command and the bot suggests the closest match. Get an argument
wrong and it shows correct usage instead of a raw error.
