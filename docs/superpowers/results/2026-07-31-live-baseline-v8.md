# Live baseline — frozen 2026-07-31 (plan v8, Task V7)

**This is the fixed reference every v8 change is measured against.** Nothing
downstream (V8's weekly cohort report, V27's shadow week, V29's monitoring,
V34's forward watch) may compare against a moving book — re-measuring the
"before" after the fact is how a change gets credited with drift it did not
cause.

- **Measured:** 2026-07-31, from the live deployment at `/opt/swing-bot/data`.
- **Method:** `swingbot/core/analytics/metrics.py` — `r_multiple`,
  `win_rate`, `expectancy_r`, `profit_factor`. Same definitions the admin UI
  renders; no ad-hoc stat math.
- **Percent returns** are `(exit − entry)/entry × 100`, sign-flipped for
  bearish trades. Win rate is over win+loss only; expectancy over all closed.
- **Archive:** `trades.json`, `journal.json`, `plans.json` copied verbatim to
  `/opt/swing-bot/archive/2026-07-31-pre-v8/` so the pre-change book is
  recoverable byte-for-byte. Deliberately placed *outside* `data/` so nothing
  in the running bot's read path changed. MD5s, verified equal to the live
  files at copy time:

      d5640f6c1d5b77b8560db683b58d5e0d  trades.json
      bc0371da97bd539b0141298c9539fac0  journal.json
      ca3bcfcfee9be9517531092f390b6d2d  plans.json

## Exact record counts

| File | Records |
|---|---|
| `trades.json` | **499** (495 closed, 4 open) |
| — by status | 269 win / 218 loss / 8 scratch-or-manual |
| `journal.json` | **351** entries (342 with `mfe_r`, 9 missing, **0 negative**) |
| `plans.json` | **130** plans |
| Trade span | 2026-07-06T12:01Z → 2026-07-31T20:31Z (26 calendar days) |

The 9 missing `mfe_r` are the accounted-for residue of Task V3: 3 journal
entries with no matching trade record (tracked as **V45**) and 6 same-day
trades whose window has no daily bar yet in a once-per-day cache. Zero
negative `mfe_r` — V3's clamp holds on the live file.

## Headline

| Metric | Value |
|---|---|
| Closed trades | **495** (269 win / 218 loss / 8 scratch) |
| Win rate | **55.24%** |
| Avg win | **+1.42%** |
| Avg loss | **−2.47%** |
| Payoff ratio | **0.574** |
| Breakeven WR required | **63.52%** — actual 55.24%, an **−8.3 pt** deficit |
| Cumulative PnL | **−157.9%** (avg **−0.32%**/trade) |
| Expectancy | **−0.127 R** |
| Profit factor | **0.686** |
| Median win / median loss | **+0.87%** / **−2.29%** |
| Wins reaching ≥2% | **48 / 269 (17.8%)** |

## Designed geometry — the structural cause, re-measured

Across all 499 records, from each record's own entry/stop/target:

| | Value |
|---|---|
| Median designed target distance | **0.844%** |
| Median designed stop distance | **2.200%** |
| Median designed R:R | **0.350** |

A win banks ~0.35R while a loss costs the full 1R **by construction**. The
median winner *cannot arithmetically* reach 2%. Journal exit efficiency
agrees: median **0.218** over 321 scored entries, against a median available
excursion of **0.874 R** (342 entries) — the favourable move was there and
was not taken.

## Cohorts

### Engine path

| Cohort | n | WR | avg win | avg loss | total | exp R |
|---|---|---|---|---|---|---|
| legacy (`source=None`, no `plan_id`) | 158 | 26.9% | +4.05% | −2.34% | **−97.0%** | −0.226 |
| v2 (`source=confluence`, has `plan_id`) | 337 | 68.6% | +0.93% | −2.61% | **−60.9%** | −0.082 |

### v2 tiers

| Cohort | n | WR | avg win | avg loss | total | exp R |
|---|---|---|---|---|---|---|
| tier A | 36 | 67.6% | +1.03% | −2.37% | −2.6% | −0.027 |
| tier B | 115 | 78.1% | +0.98% | −2.93% | **+14.2%** | +0.060 |
| tier C | 186 | 62.8% | +0.88% | −2.54% | **−72.5%** | −0.180 |

### Badge

| Cohort | n | WR | total | exp R |
|---|---|---|---|---|
| WEAK | 324 | 68.3% | −62.7% | −0.088 |
| none (legacy) | 158 | 26.9% | −97.0% | −0.226 |
| VALIDATED | 13 | 75.0% | +1.8% | +0.064 |

Only **13** closed trades carry a VALIDATED badge — too few to conclude
anything from, and a reminder that the badge registry goes stale the moment
V9 unfreezes rr (risk 5).

### Worst strategies by total damage

| Strategy | n | WR | avg win | avg loss | total | exp R |
|---|---|---|---|---|---|---|
| S/R Confluence (legacy) | 156 | 26.0% | +4.10% | −2.34% | **−103.0%** | −0.248 |
| Volume Profile HVN | 38 | 57.9% | +0.77% | −2.64% | −25.3% | −0.261 |
| Fib 23.6% | 15 | 46.7% | +0.71% | −3.54% | −23.4% | −0.667 |
| Trendline (4x touch) | 16 | 56.3% | +0.67% | −2.98% | −14.9% | −0.424 |

**One legacy strategy is 65% of all damage** (−103.0% of −157.9%). It is
also cleanly separable: all 156 of its closed trades have **no `plan_id`**,
and only 2 other closed trades are legacy — so V13's cut removes this cohort
and essentially nothing else.

Profitable strategies for contrast: FVG (bearish) 54 trades / 79.2% / +13.0%,
FVG (bullish) 45 / 83.7% / +11.8%, VWAP 17 / 75.0% / +2.4%.

### Direction and horizon

Direction is not a factor: bullish 272 / 55.6% / −78.3%, bearish 223 / 54.8%
/ −79.6%. Horizon spread runs from 4w (80 trades, 48.7%, −22.7%) and 3m (66,
47.0%, **−47.1%**) at the bad end to 9m (22, 72.7%, +4.4%) and 2m (73,
57.5%, −7.4%) at the good — no horizon is profitable enough to carry the
book, and the worst are the short ones.

## Scale-out never reached the trade log

| | Count |
|---|---|
| Closed trades with ≥1 leg | **35 / 495** |
| Closed trades with 2 legs | **9** |
| Runners that reached TP2 | **1** |
| Closes attributed to `auto (price monitor)` | **242** |

This is the live confirmation of Task V4: `close_if_live_price_hit` — the
"auto (price monitor)" reason on 242 of 495 closes — was full-closing v2
trades at TP1 before the plan manager could bank a partial. Leg reasons
across the 35: `tp1` 17, `loss` 12, `tp1_runner_be` 8, `scratch` 6,
`tp1_runner_tp2` **1**.

**These 495 closes are pre-fix and cannot improve retroactively.** V4 Step 3
re-measures the leg rate on trades closed *after* the fix; this table is the
"before" it compares against.

## Drift against the numbers in the plan text

The plan's "Why this plan exists" section was measured earlier the same day,
against 485 records / 479 closed. The book kept trading (the bot is
deliberately not being restarted for this plan), so the frozen numbers above
differ slightly. Recorded rather than reconciled — the drift is real trading,
not a methodology change:

| Metric | Plan text (485 rec) | Frozen (499 rec) |
|---|---|---|
| Closed | 479 | 495 |
| Win rate | 55.6% | 55.24% |
| Avg win / loss | +1.44% / −2.47% | +1.42% / −2.47% |
| Cumulative | −142.5% | −157.9% |
| Legacy cohort | 154 / 26.0% / −103.0% | 158 / 26.9% / −97.0% |
| tier A | 31 / 74.2% | 36 / 67.6% |
| tier B | 107 / 78.5% | 115 / 78.1% |
| tier C | 181 / 63.5% | 186 / 62.8% |

Note tier A's win rate fell 6.6 pts on 5 new trades — a reminder that
**n=36 is not a measurement**, it is a small sample that moves several points
per trade. Every downstream comparison must carry N and a Wilson bound, per
the methodology doc.

**From here on, "baseline" means this file, not a fresh read of
`trades.json`.**
