# v115 — Restore the pre-2026-09-23 trade issuance path behind flags

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

## Decision (partner-approved 2026-09-30)

Flags, default = pre-09-23 behaviour; no `git revert` (conflicts with v111,
v113, `1eb9a194` in `analyze.py` / `scan_run.py`).

| # | Change | Flag (default) | Source commit |
|---|---|---|---|
| 1 | `SIGNAL_CONFIRMATION_SCANS` | value `2` in `config.py` default and `.env.example` | `755a61ca` |
| 2 | `MIN_STOP_DISTANCE_PCT` | value `2.0` in `.env.example` (code default already 2.0 — verify) | `9a3a8757` |
| 3 | Reject plans with stop beyond the 2% cap at plan build | `ENFORCE_HARD_CAP_AT_BUILD` = `false` | `f01e87e2` |
| 4 | Futures/FX/index exemption from the dollar-volume floor | `LIQUIDITY_EXEMPT_NON_EQUITY` = `false` | `4a649b36` |
| 5 | Lifecycle widening bounded by the 2% cap instead of horizon `max_risk_pct` | follows flag 3: flag off -> horizon `max_risk_pct`; only matters when `LEVEL_LIFECYCLE_STOPS_ENABLED` | `a356c7f2` |

Left untouched (masked / default-off / inert / out of scope): v92, v102, v103,
v104 stop scope and masked shorts, v108, v113, v109 spot metals, the ET-date
fix, Alpaca, v110 embeds, v111 logging, UI.

`1eb9a194` (re-alert after a plan-build rejection) stays: it only fires on a
rejection, which flag 3 off makes unreachable for the cap reason.

## Behaviour with flags at defaults

- `attach_plan_v2` no longer sets `plan_v2_rejected="risk_cap"`; the
  funnel text keeps its wording (it already lists both causes).
- `universe.liquidity_reason(df, symbol=ticker)` ignores the symbol unless
  flag 4 is on, so SI=F/GC=F etc. are again subject to the floor.
- `lifecycle.apply_level_lifecycle` uses `HORIZONS[h]["max_risk_pct"]` as the
  ceiling when flag 3 is off; `stop_ceiling(...)` otherwise.
- PlanManager's own `cancelled_risk_cap` on fill is unchanged, so a plan wider
  than 2% is posted and cancelled on fill exactly as on 2026-09-22. That is
  the accepted cost of this request.

## Production

Edit production `.env` **in place** (nano or `cat new > .env`, never `sed -i`;
`known-traps.md` § bind-mounted .env), set the two values, add nothing else
(new flags default to the old behaviour), SIGHUP/recreate, verify with
`docker compose exec -T bot grep <KEY> /app/.env`. Mirror: `.env.example`,
`config.py`, `known-traps.md` (amend the 2026-09-30 note), commit.

## Testing

- Golden test: with all flags at defaults, a plan with a 2.5% stop is issued
  by `attach_plan_v2`; with `ENFORCE_HARD_CAP_AT_BUILD=true` it is rejected.
- `liquidity_reason` with a futures symbol and the flag off returns the
  dollar-volume reason; on returns `None`.
- Lifecycle ceiling test for both flag states.
- Existing `f01e87e2` / `4a649b36` / `a356c7f2` tests re-parameterised to set
  the flag on, so the new behaviour stays covered.
- `config` schema test for the two new fields; `.env.example` parity.
- Complexity < 15 on every touched function.

## Out of scope

Validating the pre-09-23 path against any backtest; choosing between this and
v114. Both are open to the partner after a week of live data.
