# Q-INV inverse-instrument horizon measurement — pre-registration

## Question and window

Q-INV asks which horizons clear the stated rule on real PSQ, SH, RWM and DOG
data. The measurement uses TRAIN only, 2020-01-01 through 2023-12-31.
VALIDATION (2024-01-01 through 2025-12-31) is not spent under any outcome.

## Frozen arithmetic

Every run uses the existing bullish entries with `exit_model="v2"`, scale-out
enabled, TP2 mode `levels`, and frictions enabled. No parameter is changed
between instruments, horizons, or folds.

The inverse carry model is linear rather than compounded. Each fund has a
published 0.95% net expense ratio (ProShares fund fact sheets, accessed
2026-09-24). The full 2018-06-01..2025-12-30 close-to-close residual,
`-(inverse return + benchmark return) * 252`, was PSQ −398.0, SH −444.9,
RWM −365.1 and DOG −424.9 bps/year against QQQ, SPY, IWM and DIA respectively.
Because all measured residuals are favourable rather than a cost, they are
clipped to zero; the carry deduction is therefore the 95 bps expense ratio
for each fund. This prevents a data-period-specific performance credit from
entering the live arithmetic.

## Selection rule

> A horizon subset clears only with **WR ≥ 50%**, **ExpR > 0**, **decided N ≥ 30**,
> **scratch+timeout share ≤ 50%**, and **at least two anchored fold years with
> N ≥ 15 and positive ExpR**. An instrument that fails alone does not ride in on
> the basket's pooled number: the basket ships only if **every** instrument
> clears on its own **and** the pooled figures clear. If nothing clears, the
> component closes and **no instrument ships** — no threshold is loosened, and
> **no second grid is run on the same question.**

Anchored fold tests are calendar years 2021, 2022 and 2023, following the
existing 2018-06 warmup / 2020 TRAIN convention.
