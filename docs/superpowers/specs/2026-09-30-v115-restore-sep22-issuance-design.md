# v115 — Restore pre-09-23 issuance: clamp wide stops to 2%, floor back to 2.0

**Version:** bot 1.11.1 (at writing)
**Bump:** bot minor (the alert stream visibly changes)
**Edge:** volume

## Why this

The partner wants the bot to issue trades the way it did before 2026-09-23
(baseline `d64c03d2`), keeping everything shipped since for Alpaca (v106),
Discord messages (v110), the frontend and backend logging (v111).

Production posted nothing 2026-09-25..30. Cause (`known-traps.md` § Stop floor
and 2% cap): `f01e87e2` rejects any plan whose stop is beyond the 2% hard cap,
while scenario admission still requires a stop >= `MIN_STOP_DISTANCE_PCT`.
At floor 2.0 only a stop of exactly 2.0% survives. Production was put on
floor 1.0 and `SIGNAL_CONFIRMATION_SCANS=1` on 2026-09-30 as stopgaps.

Restoring only the two env values would return to "posts nothing", so the
always-on changes must be switchable too. The v114 spec (band 1.0-2.0) is the
measured alternative and is **not** superseded by this one; it is a different
behaviour from the pre-09-23 path.

## Decision (partner-approved 2026-09-30, revised same day)

Flags, default = pre-09-23 issuance; no `git revert` (conflicts with v111,
v113, `1eb9a194` in `analyze.py` / `scan_run.py`). Revision: the partner
keeps `SIGNAL_CONFIRMATION_SCANS=1` and does **not** want the pre-09-28
post-then-cancel behaviour. A setup whose natural stop is wider than 2% is
still issued, with its stop moved to exactly 2% from the entry.

| # | Change | Flag (default) | Source |
|---|---|---|---|
| 1 | `SIGNAL_CONFIRMATION_SCANS` | stays `1` (no change) | `755a61ca` |
| 2 | `MIN_STOP_DISTANCE_PCT` | `2.0` in `.env.example` and production `.env` (code default already 2.0 — verify) | `9a3a8757` |
| 3 | Clamp the stop to `HARD_MAX_PLANNED_LOSS_PCT` from the trigger in `build_confluence_plan`, before target selection | `CLAMP_STOP_TO_HARD_CAP` = `true` | new; supersedes the reject of `f01e87e2` |
| 4 | Futures/FX/index exemption from the dollar-volume floor | `LIQUIDITY_EXEMPT_NON_EQUITY` = `false` | `4a649b36` |

The `f01e87e2` reject in `attach_plan_v2` stays as a safety net; after the
clamp it can only fire on a float edge. `a356c7f2` (lifecycle ceiling at the
2% cap) stays: it agrees with the clamp. `1eb9a194` stays.

Left untouched (masked / default-off / inert / out of scope): v92, v102, v103,
v104 stop scope and masked shorts, v108, v113, v109 spot metals, the ET-date
fix, Alpaca, v110 embeds, v111 logging, UI.

## Behaviour

- `build_confluence_plan`: when `CLAMP_STOP_TO_HARD_CAP` is on and
  `planned_loss_pct(entry, scenario.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT`,
  the stop becomes `entry -/+ entry * cap/100` (long/short). Target selection
  (`select_structural_target`), TP2 and the plan all use the clamped stop, so
  `MIN_RISK_REWARD_RATIO` is checked against the tighter risk. If no target
  pays it the existing `no_qualifying_target` rejection applies. A stop
  already within 2% is untouched.
- Only the confluence builder clamps. Strategy-source plans already cap.
- Scenario building and the admission gate (`MIN_STOP_DISTANCE_PCT`,
  `MAX_STOP_LOSS_PCT`) are untouched, so the scan funnel counts are unchanged
  and the floor of 2.0 admits every scenario with a stop of 2.0% or more.
- The plan may carry a stop that is not at a structural level; embeds show
  the stop as-is. Replay / backtest parity for confluence plans is **not**
  claimed: the clamp applies to whatever calls `build_confluence_plan`; if
  the backtest harness does, parity is kept, otherwise this is a known
  live-vs-backtest gap to record in `known-traps.md`.
- `universe.liquidity_reason(df, symbol=ticker)` ignores the symbol unless
  flag 4 is on, so SI=F / GC=F etc. are again subject to the dollar-volume
  floor.

## Production

Edit production `.env` **in place** (nano or `cat new > .env`, never `sed -i`;
`known-traps.md` § bind-mounted .env), set `MIN_STOP_DISTANCE_PCT=2.0` (leave
`SIGNAL_CONFIRMATION_SCANS=1`; the new flags default to the intended behaviour), SIGHUP/recreate, verify with
`docker compose exec -T bot grep <KEY> /app/.env`. Mirror: `.env.example`,
`config.py`, `known-traps.md` (amend the 2026-09-30 note), commit.

## Testing

- Clamp: long and short scenario with a 4% stop -> plan stop is exactly 2%
  from the trigger, tp1 pays the min R:R against that stop; a scenario whose
  only target fails R:R at 2% returns `None`; a 1.5% stop is unchanged; flag
  off restores the unclamped stop.
- `attach_plan_v2` issues (not rejects) a scenario with a 4% stop.
- `liquidity_reason` with a futures symbol: flag off returns the dollar-volume
  reason, on returns `None`.
- Config schema test for the two new fields; `.env.example` parity.
- Existing `f01e87e2` tests that build wide-stop plans are updated for the
  clamp (they now expect an issued 2% plan).
- Complexity < 15 on every touched function.

## Out of scope

Validating the clamp against a backtest (an unmeasured live change, `Edge:
volume`); choosing between this and v114's band. Both are open to the partner
after live data.
