# v151 — Plan detail page and the shared "Why" panel

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** ui minor (new plan page + Why panel) · bot patch (embed link)
**Edge:** none (integrity) — explanation surface only. It changes no gate, no level, no exit and no alert decision; it makes the reasons already stored on every plan readable in one place.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, veteran-trader
**Status:** spec written 2026-10-09; panel review applied.

**Why `ui minor`.** `working-conventions.md` § The three levels: a minor is a
component "materially different to the person using it". A new workspace
page plus the Why panel replacing the reasoning on every trade page means
the partner looks at *why* anew — that bar, not a new control. The bot half
(a title link) is a patch.

## Why

A Discord alert says *what* to do; the partner wants to see *why* in one
click: which methods put each level where it is, how many confidence points
each factor earned, how close the plan sat to each gate, the chart, and —
once it runs — how it is playing out. Today the reasons exist but are
scattered:

- The trade detail page (`trades/:id`, `frontend/src/app/app.routes.ts:44-51`,
  component `frontend/src/app/workspaces/trades/trade-detail.ts`) splits them
  across five tabs (`TABS`, `trade-detail.ts:38-44`): level sources under the
  Levels panel (`:210-225`), explanation / Confirmed by / Confidence / Quality
  breakdowns in the Plan tab (`:325-381`), Scale-out legs and Timeline in the
  Live tab (`:497-550`), the chart in the Chart tab (`:551-563`).
- Gate context is not shown anywhere. The plan stores it — `entry_context`
  (`swingbot/core/planning/plan_types.py:69`, keys `regime2_state`,
  `rs_pctile`, `sector_pctile`, `rs_combined` stamped at
  `swingbot/core/edge/context.py:108-109`, gap keys at `:106-107`) and
  `risk_features` (`plan_types.py:66`, built by
  `swingbot/core/scanning/risk_features.py:48-66`, incl. `days_to_earnings`)
  — but `_plan_detail` (`swingbot/admin/api_v1/trades.py:658`) never puts
  either on the wire.
- Discord embeds carry the plan id only as an 8-char footer
  (`swingbot/core/presentation/kinds.py:222-225`); there is no link.

## Decisions taken in the brainstorm

| Question | Decision |
|---|---|
| Where the reasoning lives | One shared **Why panel**, rendered on both the trade page and a new plan page |
| Plan page | New route `plans/:id` for **open or pending** plans (PENDING / ACTIVE / PARTIAL), built from components shared with `trades/:id` — extracted, never duplicated |
| Why panel content | Levels with their confirming methods · confidence points per factor · gate margins · calendar in the holding window · chart · outcome path (legs + status timeline) |
| Confidence points | v146's numeric `confidence_points` plus its `confidence_unevaluated` list when present; otherwise the existing text `confidence_breakdown`. The page ships and works on records written before v146 |
| Discord | Every plan-carrying embed (alerts, and the v152 notification messages) links to the plan page; the base URL comes from config |
| Not an order surface | The page shows levels order-ready for reading; it places, edits and cancels nothing (the bot is paper-only) |
| Tests | Vitest per component; pytest for every new or changed endpoint |

## Facts this design rests on

1. **`trades/:id` already resolves plan ids.** `get_trade`
   (`trades.py:735-774`) routes a 36-char dashed id to `PlanStore`
   (`_looks_like_a_plan_id`, `:646`) and returns the plan row joined to
   its trade. The trade page already renders a PENDING plan (the Trigger row,
   `trade-detail.ts:187-192`). So the plan page needs **no new GET
   endpoint** — it reuses `GET /api/v1/trades/:id` and `TradeDetailStore`
   (`frontend/src/app/stores/trade-detail.store.ts`, `load()` at `:544`).
2. **A pending plan already has a trade row.** The scan logs a placeholder
   trade for every persisted v2 plan (`swingbot/core/scanning/scan_run.py:965-999`,
   `_persist_plan_v2` then `log_trade(...)`) carrying `confidence_breakdown`,
   `target_sources`, `stop_sources`, `target2_sources`, `confirmed_by`,
   `entry_context` and `risk_features`. The plan doc itself has **no**
   `*_sources` fields; its own equivalents are `quality_breakdown`,
   `badge_stats`, `cohort_label`/`cohort_stats` (`plan_types.py:62-63`),
   `entry_context`, `risk_features` and `acceptance_level` (`:126`).
3. **v146 fixes the confidence contract.** v146 writes `confidence_points`
   (factor → integer points) and `confidence_unevaluated` (the factors whose
   line was a neutral fallback, e.g. `regime unavailable (+7)`) next to
   `confidence_breakdown` on the trade via `log_trade`, and both onto
   `TradePlanV2` (`docs/superpowers/specs/2026-10-09-v146-expectancy-attribution-design.md:93-108`);
   it names v151 as the consumer of both (`:354-355`). Non-factor keys
   (`Quality score`, `Level adjustment`, …) never appear in `points` (`:89-91`).
4. **No admin base URL exists in config.** The Admin UI group holds only
   `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_PORT`
   (`swingbot/config.py:720-729`) and is commented as affecting the admin
   container, not the bot (`:720`); `ADMIN_HOST` is a bare `os.getenv`
   (`swingbot/admin/app.py:376`). Production reaches the admin through an SSH
   tunnel or an optional Cloudflare tunnel (`docs/deploy/DEPLOY_HETZNER.md:244-268`).
5. **One choke point stamps every plan-carrying embed.** `apply_chrome`
   (`swingbot/core/presentation/components.py:64-82`) receives `plan_id` from
   the strategy alert and its mirror (`swingbot/core/scanning/alert_embeds.py:32`,
   `alert_embeds.py:52`), the setup alert (`alert_embeds.py:298`), the simple
   mirror (`alert_embeds.py:381`), execution tickets (`execution_embeds.py:48`),
   lifecycle embeds (`lifecycle_embeds.py:130`, `:253`, `:394`), the
   Breakdown button (`commands/views.py:170`) and `!trade` (`commands/trades.py:307`).
   No module under `swingbot/core/presentation/` imports `swingbot.config`;
   every one of those caller modules already does (`alert_embeds.py:7`,
   `execution_embeds.py:10`, `lifecycle_embeds.py:9`, `views.py:18`,
   `commands/trades.py:8`).
6. **Only the RS gate has a live threshold.** `RS_GATE` default on, bearish
   arm `RS_LAGGARD_PERCENTILE` = 25, bullish arm `RS_LEADER_PERCENTILE` = 0
   (disabled) (`config.py:363-394`, applied in `swingbot/core/edge/rs_gate.py:28`).
   Regime gating is off by default (`REGIME_GATES_ENABLED`, `config.py:941`)
   and `days_to_earnings` is `None` on every plan today
   (`risk_features.py:63-65`). Thresholds are **not** frozen on the plan.
7. **A route the server does not know 404s on reload.** `spa.py:47-51`
   `WORKSPACES` must list `plans`, or `/plans/<id>` works by click and 404s
   from a Discord link.
8. **Expiry and time exit are bar counts on the plan.** `expiry_bars`
   (`plan_types.py:33`) bounds a PENDING plan, surfaced as `bars_to_expiry`
   (`swingbot/core/presentation/plan_view.py:61-63`). `hold_cap_bars`
   (`plan_types.py:86`) is the time-exit bar count; today only the v119
   compression short uses it, closing on its tenth session
   (`swingbot/core/planning/time_exit.py:47-52`,
   `swingbot/core/planning/exit_sim.py:211-224`). `entry_type` is
   `stop_entry` / `market` / `limit` (`plan_types.py:30`).
9. **OPEX dates are pure calendar; earnings and macro are not.**
   `monthly_expiration` / `opex_tier` (`swingbot/core/market/opex.py:84-111`)
   need no I/O. Earnings dates need a live Yahoo call
   (`swingbot/core/market/events.py:55`, `:184`); the only non-blocking read,
   `peek_cached_earnings_datetime` (`events.py:116-129`), reads a per-process
   cache the admin container never warms. No macro-calendar module exists.

## API — one changed endpoint, no new one

`GET /api/v1/trades/<id>` gains these keys on `detail`, in both
`_plan_detail` (`trades.py:658`) and `_legacy_detail` (`:696`) — one shape
for both origins, as that module already insists (`:699-701`):

| Key | Plan-backed | Legacy | Notes |
|---|---|---|---|
| `entry_context` | plan's, else trade's | trade's, else `{}` | only the four gate keys, `htf_aligned`, `gap_p90_pct`, `gap_fragile` are sent, not the full feature dict |
| `risk_features` | plan's, else trade's | trade's, else `{}` | whole dict (small, fixed keys) |
| `cohort_label` | `plan.cohort_label` | `None` | |
| `confidence_points` | trade's, else plan's, else `None` | trade's, else `None` | v146's factor → points map; passed through untouched |
| `confidence_unevaluated` | trade's, else plan's, else `[]` | trade's, else `[]` | v146's list of fallback factors; passed through untouched |
| `gates` | `gate_rows(...)` | `gate_rows(...)` | list, computed server-side (below) |
| `sessions_since_created` | NYSE sessions from `created_at` to today | same, from the trade's open date | `nyse_calendar().sessions_between` (`swingbot/core/market/session.py:192`); `None` outside coverage |
| `expires_on` | session `created_at` + `expiry_bars` | `None` | ISO date; PENDING only, else `None` |
| `time_exit_on` | session fill day + `hold_cap_bars` − 1 | `None` | ISO date; `None` when `hold_cap_bars` is `None` or not yet filled |
| `calendar` | `calendar_rows(...)` | `[]` | monthly OPEX dates inside the holding window (below) |

The plan's copy wins for `entry_context`/`risk_features` because it is the
record frozen at the creating bar; the trade's copy is the same value logged
from it (`scan_run.py:997`) and is the fallback for an older plan.

The key names are v146's (fact 3); this spec reads them, never computes them.
A record written before v146 has neither key: `None` / `[]` on the wire.

### `gate_rows` — `swingbot/core/presentation/why_view.py` (new, pure)

`gate_rows(direction, entry_context, risk_features, cohort_label, thresholds) -> list[dict]`,
no I/O and **no `swingbot.config` import**. `thresholds` is a small frozen
dataclass `GateThresholds(rs_gate: bool, rs_laggard_pct: float,
rs_leader_pct: float, regime_gates: bool)` defined in `why_view.py`; the
caller (`trades.py`, admin layer) builds it from `config` per request, so
`core/presentation` keeps its no-config property (fact 5) and the tests pass
thresholds directly instead of patching config. One row per gate:

```
{"key": "rs" | "regime" | "earnings",
 "label": str,
 "value": float | str | None,
 "threshold": float | None,     # current config, not the value at issuance
 "margin": float | None,        # signed: > 0 = cleared by this much, < 0 = failed by
 "applies": bool,               # False = gate off / arm disabled / exempt; row still shown
 "parts": [{"label", "value"}], # components, e.g. RS ticker + sector pctile
 "note": str | None}
```

Table-driven: one small builder per gate, a tuple of builders iterated —
each under complexity 15.

| Gate | value | threshold / margin | applies |
|---|---|---|---|
| RS | `rs_combined`, else `rs_pctile` | bearish: `rs_laggard_pct`, margin = threshold − value; bullish: `rs_leader_pct`, margin = value − threshold | `rs_gate` and the arm's threshold is live (bullish leader > 0) |
| Regime | `regime2_state` | none | `regime_gates`; `note` = `cohort_label` |
| Earnings | `risk_features.days_to_earnings` | none | False while the value is `None`; `note` = "not recorded on this plan" |

`parts` for RS: `rs_pctile` (ticker), `sector_pctile` (sector). Missing
values are `None`, never a sentinel; the frontend renders them as "—".

### `calendar_rows` — same module, pure

`calendar_rows(start: date, end: date) -> list[dict]` returns
`{"date", "kind": "opex_monthly", "label": "Monthly OPEX"}` for each
`monthly_expiration` (`opex.py:84`) in `[start, end]`. Window: `created_at`
to `time_exit_on` if set, else `expires_on` (PENDING), else `created_at` +
the horizon's `max_holding_days` (`swingbot/core/market/strategy_types.py:64`
and siblings) in calendar days. Weekly OPEX is left out (every Friday — noise).
Dates past `opex.py:73`'s coverage year return no row. `opex.py` reads config
only in its policy layer (from `:115`); `calendar_rows` calls nothing there.

## Frontend

### Extracted shared components — `frontend/src/app/workspaces/trades/why/`

| Component | Extracted from | Inputs |
|---|---|---|
| `why-panel.ts` (`sb-why-panel`) | `trade-detail.ts:210-225` (sources) and `:325-381` (explanation, Confirmed by, Confidence, Quality) | the store's derived signals, passed as plain inputs; `[sections]`, `[status]` |
| `levels-block.ts` (`sb-levels-block`) | the Levels panel, `:161-226` | entry type, trigger, entry, stop, T1, T2, R:R, `acceptance_level` |
| `if-it-gets-there.ts` (`sb-if-it-gets-there`) | the "If it gets there" panel, `:253` onward | the store's existing signals for it |
| `sizing-panel.ts` (`sb-sizing-panel`) | the Sizing panel, `:274` onward | the store's existing signals, plus gap p90 |
| `outcome-path.ts` (`sb-outcome-path`) | `:497-550` (Scale-out legs, Timeline) | `legs`, `timeline` |
| `plan-chart.ts` (`sb-plan-chart`) | `:551-563` and `chartCaption`/`chartEmpty` (`:1133-1150`) | reads `ChartStore` from its injector |

The extraction is behaviour-preserving for the trade page: same panels, same
text, same order within each tab; its existing `trade-detail.spec.ts`
assertions keep passing unchanged except for selectors that move into a child.

**Levels block — order-ready.** One block reads the way an order ticket
would: entry type in words (`stop_entry` → "Buy stop" / "Sell stop",
`limit` → "Buy limit" / "Sell limit", `market` → "At market", by direction),
the trigger, stop, T1, T2 and R:R, in that order. A muted line under it:
"Paper plan — this page places no orders." The bot is paper-only; nothing on
this page submits, edits or cancels.

**Sizing panel — gap risk.** Reused unchanged, plus one row "Gap risk (p90)"
from `entry_context.gap_p90_pct` with a "fragile" chip when `gap_fragile` is
true (the stop sits inside gap noise, `context.py:106-107`); "—" when absent.
No max-chase figure exists anywhere in the codebase, so none is shown.

**Why panel sections**, in order (`sections` input selects which render):

1. **Levels & methods** — one row per level (Entry/Trigger, Stop, Target 1,
   Target 2) with its price and the methods that confirmed it
   (`targetSources`, `stopSources`, `target2Sources`, store `:269-271`);
   `confirmed_by` strategies (`:261-262`) beneath; `acceptance_level` when set.
   The trade page's Levels panel drops its `.sources` block — the Why panel
   is now the one place sources render.
2. **Confidence** — when `confidence_points` is a non-empty record: factor,
   signed points, the matching `confidence_breakdown` note if one shares the
   key, and a total row. A factor listed in `confidence_unevaluated` carries
   an "unevaluated" chip (tooltip "no data — neutral points awarded") and its
   points render muted, so a fallback never reads as a real reading; the
   total still sums them (it must reconcile with the quality score, fact 3).
   Otherwise the existing text rows (`toConfidenceFactors`, store `:118-127`).
   Quality breakdown (already numeric) follows unchanged.
3. **Gate margins (vs today's thresholds)** — that is the section heading.
   One row per `gates` entry: label, value, threshold, signed margin, a muted
   "off" chip (tooltip "off in current config") when `applies` is false,
   `parts` inline. Margin colour:
   - pos/neg on PENDING / ACTIVE / PARTIAL plans created ≤ 5 sessions ago;
   - **neutral** on CLOSED / CANCELLED plans and on an expired PENDING
     (`bars_to_expiry` = 0) — today's threshold says nothing about a plan
     that is over;
   - neutral plus an "indicative" chip when `sessions_since_created` > 5 —
     the threshold may have moved since issuance.
   A caveat line sits beneath the rows, **always visible, never collapsible**:
   "Margins are measured against today's thresholds, not the ones in force
   when this plan was issued."
4. **Calendar in the holding window** — one row per `calendar` entry (date,
   label); "None in the window" when empty. Earnings and macro dates are not
   shown (fact 9; see Out of scope); the existing Earnings gate row still
   says "not recorded on this plan".
5. **Why this trade** — the `explanation` prose, unchanged.

Chart and outcome path are their own shared components (above) rather than
Why-panel sections, so each page places them where its layout wants them.

**Store** (`trade-detail.store.ts`): new computeds `confidencePoints`,
`confidenceUnevaluated`, `gates`, `calendar`, `entryContext`,
`riskFeatures`, `sessionsSinceCreated`, `expiresOn`, `timeExitOn`, each
defensive in the file's existing style (`isRecord`/`asNumber`).
`detailAbsent` (`:364-375`) is unchanged — an old trade with no detail still
gets the "logged before" note.
**Models** (`frontend/src/app/api/models.ts:173-211`): `TradeDetailFields`
gains every key in the API table (`confidence_unevaluated: string[]`
included), plus `GateRow` and `CalendarRow`.

### Trade page

Plan tab: `<sb-levels-block>`, Per share, `<sb-if-it-gets-there>`,
`<sb-sizing-panel>`, Opened, then `<sb-why-panel>` with all five sections in
place of `:325-381`. Live tab: `<sb-outcome-path>`. Chart tab:
`<sb-plan-chart>`. Actions stay on the trade page only.

**Arrival banner.** When the trade page is reached by the plan page's
redirect (below), the redirect passes `state: { from: 'plan' }`; the trade
page shows one info banner at the top — "This plan has expired" /
"…was cancelled" / "…is closed" by status — so a Discord link that lands on
the trade record says why it did. A direct visit shows no banner.

### Plan page — `frontend/src/app/workspaces/plans/`

`plan-detail.routes.ts` mirrors `trade-detail.routes.ts`: providers
`[TradeDetailStore, ChartStore]`, the same `resolveRoute` →
`store.setId(id, false); store.resolve()`, events `onEvents('trades', 'journal')`.
`app.routes.ts` gains `plans/:id` (`canMatch: [authGuard]`, title
`Plan detail`, subtitle `Why this plan, and how it is going`) beside
`trades/:id`.

`plan-detail.ts` (`sb-plan-detail`) is one scrolling page, no tabs:

1. Header — ticker, direction, status indicator, strategy · horizon, badge,
   `Lv` chip, created date. Timing line: for PENDING "expires
   `<expires_on>` (`<bars_to_expiry>` bars left)"; when `hold_cap_bars` is
   set, "time exit after `<hold_cap_bars>` sessions" plus `time_exit_on` once
   filled. Dates render as the session date with "at the close (ET)" —
   expiry and time exit both resolve on a daily bar.
2. `<sb-levels-block>` (order-ready, above).
3. For PENDING only: `<sb-if-it-gets-there>` and `<sb-sizing-panel>` — the
   trade page's panels, reused, so the gap and sizing picture is there before
   the trigger fires. ACTIVE / PARTIAL plans keep them on the trade record.
4. `<sb-why-panel>` — all five sections.
5. `<sb-plan-chart>`.
6. `<sb-outcome-path>` — for PENDING, the timeline alone (no legs yet).
7. A link "Open the full trade record" → `/trades/:id`.

**Redirects** (`router.navigate([...], { replaceUrl: true, state: { from: 'plan' } })`,
so Back is not a loop):

| Case | Goes to |
|---|---|
| status CLOSED or CANCELLED, or PENDING with `bars_to_expiry` = 0 | `/trades/:id` with the arrival banner — a Discord link outlives the plan's open life and must still land |
| id is not plan-shaped (legacy trade id) | `/trades/:id`, no banner (`state` omitted) |
| 404 | the page's own error state (`sb-async`), not a redirect |

**Server routing:** `swingbot/admin/spa.py:47` `WORKSPACES` gains `"plans"`.
No existing `/plans` rule exists in the admin app, so both rules register.

## Discord link

**Config:** new field `ADMIN_PUBLIC_URL` in the **Discord Alerts** group of
`swingbot/config.py` (`:739`, beside `ALERT_EMBED_LAYOUT`) — not the Admin UI
group, whose fields configure the admin container (fact 4); the bot reads
this one. `type="text"`, `default=""`, `hot_reloadable=True`. Help text: "Read
by the bot each time it builds an alert embed — SIGHUP applies a change, no
restart. The admin UI's base URL as reached from the device you open Discord
on (e.g. the Cloudflare tunnel hostname); empty = no link." Added to
`.env.example` in the Discord Alerts block.

**Rendering — config stays out of `core/presentation`.**
`plan_link(plan_id: str | None, base: str) -> str | None` lives in
`components.py` and is pure apart from one log line. `apply_chrome`
(`components.py:64`) gains `link_base: str | None = None` and sets
`embed.url = plan_link(plan_id, link_base)` when that returns a value. Each
plan-carrying caller in fact 5 passes `link_base=config.ADMIN_PUBLIC_URL`
(all already import `config`); command replies that pass no `plan_id` are
untouched. No edge from `core/presentation` to `swingbot.config` is added.

**Validation** in `plan_link`, with `urllib.parse.urlsplit`: the base is
accepted only when it has no whitespace, `scheme` is `http` or `https`, and
`netloc` is non-empty. Anything else → `None` and one WARNING per distinct
bad value per process (a module-level set of values already warned about),
never per embed. Valid → `f"{base.rstrip('/')}/plans/{plan_id}"`. The title
becomes the link; footer, push line and field order are untouched.

**Blast radius — why validation is not optional.** Discord rejects the whole
message with HTTP 400 when an embed's `url` is malformed. Every plan-carrying
send in the alert channel goes through `apply_chrome`, so one bad value would
silence every setup alert, mirror, execution ticket and lifecycle embed until
fixed — not degrade one link. Validation turns that into "no link".

**Reachability — partner decision.** The link only works if
`ADMIN_PUBLIC_URL` resolves from the device the partner reads Discord on.
With the admin reachable only through an SSH tunnel (fact 4), a tapped link
on a phone goes nowhere — the feature is inert there. Exposing the admin
(e.g. the Cloudflare tunnel) is the partner's call; this spec does not make
it, and the plan asks for the value rather than guessing.

Why the title URL and not a link button on `PlanActionView`
(`commands/views.py:46`): the view times out after 180 s and `on_timeout`
disables every child (`commands/views.py:68-76`), so a link button would go
dead on every alert within three minutes; and only the setup alert carries
the view, while `apply_chrome` reaches every plan-carrying embed in fact 5.

**v152 notification messages.** v152's contract is fixed: its D1 message is
a `PushEmbed` built with `apply_chrome(..., plan_id=plan.plan_id)` "for the
v151 plan link" (v152 spec `:134`), it adds no second URL key (`:76-80`), and
its link needs v151 merged first (`:389-390`). With the signature above,
v152's builder (`swingbot/commands/scanning/follow_notify.py`, bot layer)
also passes `link_base=config.ADMIN_PUBLIC_URL` — one keyword, recorded here
so v152's plan picks it up. This spec edits none of v152's files.

**Rollback.** The link: set `ADMIN_PUBLIC_URL=` (empty) in the VM's `.env`
and SIGHUP the bot — no deploy, embeds lose the URL on the next build. The UI
half: redeploy the previous image; `scripts/ops/rollback_to.sh` is the
full-stack fallback (it restores Postgres and `.env` to a timestamp and
starts scanning paused, so it is a last resort, not the first move).

**Production:** setting it on the VM is a `.env` change under `mirror-prod`.

## Edge cases

| Case | Handling |
|---|---|
| PENDING plan | Why panel full (sources come via the placeholder trade row); If-it-gets-there and Sizing shown; outcome path shows the timeline only |
| Plan with no trade row | `*_sources`, `confidence_breakdown`, `confirmed_by` empty → those sub-rows hidden; gates still render from the plan's own `entry_context` |
| `confidence_points` absent (record before v146) | text breakdown, exactly as today; no "unevaluated" chips |
| Factor in `confidence_unevaluated` | "unevaluated" chip, muted points, still in the total |
| `confidence_points` present but `confidence_breakdown` missing a key | points row with no note |
| `entry_context` empty (pre-v87 plans) | gate rows with `value: null`, rendered "—"; never hidden, so "not recorded" is visible |
| FX / futures / index (RS-exempt) | RS row `applies: false`, note "exempt" when `rs_combined` is null |
| CLOSED / CANCELLED / expired | margins neutral; the plan page redirects with the arrival banner |
| `ADMIN_PUBLIC_URL` unset or malformed | no `embed.url`; embeds byte-identical to today apart from that; malformed logs one WARNING per value |
| Plan closes while the page is open | the store reloads on the `trades` event (route data); the redirect check runs on every load |

## Testing

**pytest**
- `tests/admin/test_api_v1_trades.py`: detail of a plan-backed row carries
  every new key; plan `entry_context` wins over the trade's; legacy row has
  the same keys (`cohort_label: None`, `calendar: []`); `confidence_points`
  absent → `None`, present → passed through; `confidence_unevaluated` absent
  → `[]`, present → passed through; `gates` present on both origins;
  `expires_on` / `time_exit_on` from a fixed calendar fixture.
- `tests/presentation/test_why_view.py` (new): RS bearish pass and fail
  margins, bullish arm disabled at 0, `rs_gate` off, `rs_combined` missing →
  falls back to `rs_pctile`, all-missing → `None` values; regime row carries
  cohort note; earnings `None` → `applies: false` — all with `GateThresholds`
  passed in, no config patching. `calendar_rows`: a window spanning one
  monthly OPEX, a holiday-shifted Thursday, an empty window, past coverage.
  A test asserts `why_view` and `components` import no `swingbot.config`.
- `tests/presentation/test_components.py`: `apply_chrome(link_base=...)`
  sets `embed.url` with a valid base; no url when `link_base` is None or
  empty, scheme not http(s) (`ftp://x`, `javascript:x`), no netloc
  (`https://`), whitespace inside, or `plan_id` is None; trailing slash
  handled; footer unchanged; one WARNING per distinct bad value across two
  calls.
- One caller test per embed module (alert, execution, lifecycle, views,
  `!trade`) that a set `ADMIN_PUBLIC_URL` reaches `embed.url`.
- `tests/admin/test_spa_serving.py`: `/plans/<uuid>` reloads into the SPA
  (add to the `:80` parametrization and the workspace list).
- Config: the new field loads in the Discord Alerts group, defaults empty,
  is `hot_reloadable`, and a SIGHUP reload changes the built URL.

**Vitest** (one spec per component)
- `why-panel.spec.ts`: each section renders from a fixture; points vs text
  fallback; "unevaluated" chip on a listed factor; heading "Gate margins (vs
  today's thresholds)"; margin sign classes on a fresh ACTIVE plan; neutral
  on CLOSED, CANCELLED, expired and > 5 sessions; "indicative" chip; "off"
  chip with its tooltip; caveat line present with no toggle; calendar rows
  and the empty line; `sections` input hides sections.
- `levels-block.spec.ts`: each entry type × direction worded; paper line present.
- `sizing-panel.spec.ts`: gap row and fragile chip; "—" when absent.
- `outcome-path.spec.ts`: legs (realized preferred over live), timeline, pending (timeline only).
- `plan-chart.spec.ts`: caption, empty, retry.
- `plan-detail.spec.ts`: renders an ACTIVE plan; PENDING shows expiry line,
  If-it-gets-there and Sizing; redirects CLOSED, CANCELLED, expired and a
  legacy id to `/trades/:id` with `replaceUrl` (banner state only for the
  first three); 404 shows the error state.
- `trade-detail.spec.ts`: existing suite green; the Plan tab now hosts
  `sb-why-panel`; sources no longer render twice; arrival banner per status
  with `from: 'plan'` state, none without it.
- `app.routes.spec.ts`: `plans/:id` matches behind `authGuard`.

Every new or changed function under cyclomatic complexity 15
(`radon cc -s -n C`); `get_trade` and both detail builders must not get worse.

## Parallelisation

- **Sequential first:** `why_view.py` (`gate_rows`, `calendar_rows`) + its
  tests, then the endpoint change in `trades.py` (it calls both and builds
  `GateThresholds`), then `models.ts` + store computeds (they mirror the
  endpoint's shape).
- **Group A (parallel, after the store):** `why-panel.ts`, `levels-block.ts`,
  `if-it-gets-there.ts`, `sizing-panel.ts`, `outcome-path.ts`,
  `plan-chart.ts` — one new file each, each consuming only store signals.
- **Group B (parallel with everything above — disjoint files, no contract
  dependency on the API):** `ADMIN_PUBLIC_URL` config field + `.env.example`;
  `plan_link` + `apply_chrome(link_base=)` in `components.py`; then the
  caller kwarg in the five embed modules (one task, after `components.py`);
  `spa.py` `"plans"`.
- **Sequential after Group A:** `trade-detail.ts` refactor onto the shared
  components plus the arrival banner (one file). Then `plan-detail.ts` +
  routes + `app.routes.ts` (consumes the same components and the store).
- **Last:** `python scripts/dev/testrun.py full` and `cd frontend && npm test`, once each.
- **Production, after merge and deploy:** set `ADMIN_PUBLIC_URL` on the VM
  with the partner's value, mirrored per `mirror-prod`.

## Out of scope

- Re-pointing existing list links (Trades, Dashboard, Calendar, Risk) from
  `/trades/:id` to `/plans/:id` — the plan page is reached from Discord and
  the trade page's own link back.
- Actions (cancel, close, note) on the plan page — the trade page keeps them.
  The page is never an order surface.
- Computing `confidence_points`, `confidence_unevaluated`, `days_to_earnings`.
- Freezing gate thresholds onto the plan at issuance.
- **Earnings and macro dates in the holding window** — handed to a future
  fundamental-analyst spec. Earnings need a live Yahoo fetch on the request
  path or a cache the admin container does not have (fact 9); no macro
  calendar exists. Only monthly OPEX, pure calendar, ships here.
- Any change to what an alert contains beyond the title link.

## Panel review

- staff-engineer: pin v146's contract — `confidence_unevaluated` added to detail keys and `models.ts`, "unevaluated" chip per fallback row, "v146 not in repo" text dropped -- applied
- staff-engineer: validate `ADMIN_PUBLIC_URL` with `urllib.parse` (http/https, netloc, no whitespace), one warning per bad value, blast radius of a malformed embed URL stated -- applied
- staff-engineer: rollback = empty `ADMIN_PUBLIC_URL` + SIGHUP; previous image, then `rollback_to.sh` as last resort, for the UI half -- applied
- staff-engineer: `ADMIN_PUBLIC_URL` in the bot-side Discord Alerts group, `hot_reloadable=True`, help says the bot reads it at embed-build time -- applied
- staff-engineer: no `swingbot.config` import into `core/presentation` — `plan_link(plan_id, base)`, `apply_chrome(link_base=)`, `gate_rows(..., thresholds)` fed by callers; no remaining edge -- applied
- staff-engineer: v152 conditional replaced by its confirmed `apply_chrome(..., plan_id=...)` contract, plus the `link_base` keyword its builder passes -- applied
- staff-engineer: fact on `apply_chrome` callers names `alert_embeds.py` for `:32`, `:52` -- applied
- staff-engineer: keep `ui minor`, justified against working-conventions.md § The three levels (new workspace page + Why panel on every trade page) -- applied (justified)
- financial-advisor: section heading "Gate margins (vs today's thresholds)"; margins neutral on CLOSED / CANCELLED / expired plans -- applied
- financial-advisor: caveat line always visible, never collapsible -- applied
- financial-advisor: "off" chip tooltip "off in current config" -- applied
- veteran-trader: order-ready levels block (entry type, trigger, stop, T1/T2, R:R) and an explicit "places no orders" line -- applied
- veteran-trader: expiry as session date at the close plus the `hold_cap_bars` time-exit count -- applied
- veteran-trader: margins on plans older than 5 sessions labelled "indicative" -- applied
- veteran-trader: calendar dates in the holding window — monthly OPEX shipped (pure calendar in `opex.py`); earnings/macro to a future fundamental-analyst spec (network-bound / no module) -- applied
- veteran-trader: plan page reuses the trade page's "If it gets there" and Sizing panels for PENDING plans (gap p90 row added to Sizing; no max-chase quantity exists) -- applied
- veteran-trader: Discord link works only where `ADMIN_PUBLIC_URL` resolves from the reading device; tunnel-only admin = inert link on a phone; partner decision -- applied
- veteran-trader: redirected expired/cancelled/closed plans show an arrival banner on the trade page -- applied
