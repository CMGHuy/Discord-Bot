# v175 — Normal bad luck: showing when a losing streak is just variance

**Version:** ui 1.27.0 · bot 2.10.0 (at writing)
**Bump:** bot minor — plan alerts gain a conditional one-line streak note and a new API endpoint serves the band; ui minor — the Analytics Overview tab gains a "Normal bad luck" panel.
**Edge:** none (integrity) — framing only. It changes no signal, gate, stop, size or badge. Any benefit is behavioural (not abandoning the edge mid-streak) and is not claimed.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, financial-advisor, veteran-trader
**Status:** spec written 2026-10-18 from a brainstorm with the partner (panel plus conditional alert line, thresholds and placement approved in chat).

## Why

Douglas (*Trading in the Zone*) argues that the trader with an edge fails
when a run of losses, which is normal for that edge, is read as proof that
the edge is gone. Every alert already shows its setup's pedigree: N, win
rate and ExpR via `badge_stats_line` (`scanning/plan_table.py:43`), plus the
v86 cohort lines. Nothing tells the trader **how long a losing run this book
should expect**, or whether the current run is inside that range.

v170 has just simplified the alerts, so the alert addition here is
conditional: a single line, shown only when a streak or drawdown is
actually in progress.

## Goals

- G1. A pure band computation: from the live book's closed-trade R values,
  the expected longest losing streak and maximum drawdown over the next 20
  and 50 trades, and where the book sits now.
- G2. A "Normal bad luck" panel on Analytics → Overview.
- G3. At most one line on a plan alert while the book is in a streak or a
  drawdown.

## Non-goals

- No instruction to the trader. The copy describes and never prescribes:
  no "stop trading", no "size down".
- No change to the throttle or kill switch (`edge/throttle.py`). Whether a
  streak should gate alerts is a separate measured question.
- No per-strategy or per-horizon bands in this spec. The band is
  book-wide, because per-cell samples are too small.
- No Dashboard placement. v172 is reshaping the Dashboard's equity chart.

## Design

### 1. Core — `swingbot/core/analytics/variance_band.py`

Pure functions, no I/O.

**Input:** the R of every closed plan, from `metrics.r_multiple` (the single
R definition), ordered by close time. A trade whose R is `None` is skipped
(as in `metrics.r_multiples`), so a manual close with no exit price drops
out. The R values are recomputed from the book on every call and never
quoted from a document (`pooled-numbers`).

**Frozen constants:**

| Constant | Value | Meaning |
|---|---|---|
| `MIN_TRADES` | 50 | Below this: `insufficient`, nothing shown |
| `HORIZONS` | (20, 50) | Simulated run lengths |
| `PATHS` | 10 000 | Bootstrap paths per horizon |
| `SEED` | fixed module constant | Reproducible bands |
| `SCRATCH_R` | 0.05 | \|R\| ≤ this is a scratch |
| `ROUGH_PCT`, `OUTSIDE_PCT` | 80, 95 | Zone cut-offs |
| `ALERT_STREAK` | 3 | Losing streak that triggers the alert line |

**Losing streak:** consecutive losses (R < −`SCRATCH_R`). A scratch neither
extends nor breaks a streak; a win (R > +`SCRATCH_R`) ends it.

**Drawdown:** the gap from the running peak of the cumulative R curve, in R.

**Bootstrap:** each path draws `h` R values with replacement from the book.
Per horizon it records the longest losing streak and the maximum drawdown,
and reports p80 and p95 of each.

**Current state:** `current_streak` (the losing streak in progress at the
latest close) and `current_drawdown` (from the all-time peak of the book's R
curve). Each is placed in a zone against the **50-trade** band:

| Zone | Condition | Copy |
|---|---|---|
| `normal` | ≤ p80 | "Normal for this edge" |
| `rough` | > p80 and ≤ p95 | "A rough patch, still inside the normal range" |
| `outside` | > p95 | "Outside the normal range: check the system, not just luck" |

**Dollars:** a drawdown in dollars is R × the book's median per-trade dollar
risk. The plan-briefer names the stored field that v170's alerts read. If
it's missing, the dollar figure is "—".

`variance_band(closed) -> Band` returns either `{status: "insufficient", n}`
or the full band.

### 2. API

`GET /api/v1/analytics/variance-band` is computed on request, behind
`require_auth`, and returns the `Band`. Its scope is the whole closed book.
It does not follow the Analytics scope bar, because a filtered book has the
wrong distribution.

### 3. Panel "Normal bad luck"

The panel goes on `analytics/tabs/overview.ts` and uses the tab's existing
`Panel`/`PanelHeader`/`PanelError` pieces.

- **Two band bars:** losing streak (in trades) and drawdown (in R, with
  dollars beside it). Each shows its normal, rough and outside segments for
  the 50-trade horizon, a "you are here" marker, and the zone copy. The
  20-trade p95 sits on a secondary line.
- **Caption:** "Simulated from your N closed trades. It shows the range of
  losing runs this edge produces by chance. Past results, not a forecast."
- **`insufficient`:** "Needs 50 closed trades (N so far)."
- **Layout:** the bars stack on phones, there is no horizontal scroll, and
  touch targets are at least 44px. Checked at mobile, tablet and desktop
  widths with Playwright (`ui-design.md`).

### 4. Alert line

Once per scan cycle, the bot computes the band from the closed book and
caches it for that cycle. A plan alert carries **one line** when either
`current_streak >= ALERT_STREAK` or the drawdown zone is `rough` or
`outside`. Otherwise it carries none.

| Condition | Line |
|---|---|
| Streak, zone normal or rough | `📉 Book: {k} losses in a row, normal for this edge (95% of simulated 50-trade runs reach {p95}).` |
| Drawdown rough | `📉 Book: down {dd}R ({$}) from peak, a rough patch, still inside the normal range.` |
| Either outside | `📉 Book: {k} losses / {dd}R down, outside the normal range. See Analytics → Overview.` |

- When the streak and drawdown lines both apply, only the more severe one is
  shown: outside > rough > streak.
- The line sits below the v170 symbol table. Embed work follows the
  `alert-surface` skill.
- An `insufficient` band never adds a line.

## Testing

- Streaks:
  - A scratch inside a run neither breaks nor extends it.
  - A win ends a run.
  - An empty book gives a streak of 0.
  - A trade with no computable R is skipped.
- Drawdown measured from the running peak on a hand-built curve.
- Bootstrap:
  - The seed makes runs reproducible.
  - An all-wins book gives a p95 streak of 0.
  - A known two-value R set gives percentiles within tolerance of the
    closed form.
- Thresholds:
  - 49 trades → `insufficient`, 50 → a band.
  - Zone boundaries exactly at p80 and p95.
- Alert line:
  - Absent below `ALERT_STREAK` in the normal zone.
  - Present at exactly 3 losses.
  - The severity order picks one line.
  - No line when the band is `insufficient`.
- API shape test.
- Frontend spec: each zone's copy, the insufficient state and the stacked
  phone layout.

Every test uses fixture data. No pooled figure comes from the dev DB.

## Risks

- **A book's R distribution drifts** (new strategies, a changed exit
  model). The band then describes the past book. The caption says so, and
  the band is recomputed every time.
- **Autocorrelated losses** (a regime turn) make an i.i.d. bootstrap
  understate streak lengths, so `outside` fires more often than 5% of the
  time. That's acceptable for a descriptive warning, and the copy points at
  the system rather than at luck. A block bootstrap is a later spec if the
  panel shows it matters.
