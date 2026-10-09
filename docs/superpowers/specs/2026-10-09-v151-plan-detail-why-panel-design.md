# v151 — Plan detail page and the shared "Why" panel

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** ui minor (new plan page + Why panel) · bot patch (embed link)
**Edge:** none (integrity) — explanation surface only. It changes no gate, no level, no exit and no alert decision; it makes the reasons already stored on every plan readable in one place.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, veteran-trader
**Status:** spec written 2026-10-09.

## Why

A Discord alert says *what* to do; the partner wants to see *why* in one
click: which methods put each level where it is, how many confidence points
each factor earned, how close the plan sat to each gate, the chart, and —
once it runs — how it is playing out. Today the reasons exist but are
scattered:

- The trade detail page (`trades/:id`, `frontend/src/app/app.routes.ts:44-51`,
  component `frontend/src/app/workspaces/trades/trade-detail.ts`) splits them
  across five tabs (`TABS`, `trade-detail.ts:38-44`): level sources under the
  Levels panel (`:210-226`), explanation / Confirmed by / Confidence / Quality
  breakdowns in the Plan tab (`:325-381`), Scale-out legs and Timeline in the
  Live tab (`:497-550`), the chart in the Chart tab (`:551-563`).
- Gate context is not shown anywhere. The plan stores it — `entry_context`
  (`swingbot/core/planning/plan_types.py:69`, keys `regime2_state`,
  `rs_pctile`, `sector_pctile`, `rs_combined` stamped at
  `swingbot/core/edge/context.py:108-109`) and `risk_features` (`:66`,
  built by `swingbot/core/scanning/risk_features.py:48-66`, incl.
  `days_to_earnings`) — but `_plan_detail`
  (`swingbot/admin/api_v1/trades.py:652-687`) never puts either on the wire.
- Discord embeds carry the plan id only as an 8-char footer
  (`swingbot/core/presentation/kinds.py:222-225`); there is no link.

## Decisions taken in the brainstorm

| Question | Decision |
|---|---|
| Where the reasoning lives | One shared **Why panel**, rendered on both the trade page and a new plan page |
| Plan page | New route `plans/:id` for **open or pending** plans (PENDING / ACTIVE / PARTIAL), built from components shared with `trades/:id` — extracted, never duplicated |
| Why panel content | Levels with their confirming methods · confidence points per factor · gate margins · chart · outcome path (legs + status timeline) |
| Confidence points | Numeric `confidence_points` from v146 when present; otherwise the existing text `confidence_breakdown`. Soft dependency — the page ships and works without v146 |
| Discord | Every plan-carrying embed (alerts, and the v152 notification messages) links to the plan page; the base URL comes from config |
| Tests | Vitest per component; pytest for every new or changed endpoint |

## Facts this design rests on

1. **`trades/:id` already resolves plan ids.** `get_trade`
   (`trades.py:727-775`) routes a 36-char dashed id to `PlanStore`
   (`_looks_like_a_plan_id`, `:640-650`) and returns the plan row joined to
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
3. **No admin base URL exists in config.** The Admin UI group holds only
   `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_PORT`
   (`swingbot/config.py:720-729`); `ADMIN_HOST` is a bare `os.getenv`
   (`swingbot/admin/app.py:376`). Production reaches the admin through an SSH
   tunnel or an optional Cloudflare tunnel (`docs/deploy/DEPLOY_HETZNER.md:244-268`).
4. **One choke point stamps every plan-carrying embed.** `apply_chrome`
   (`swingbot/core/presentation/components.py:64-82`) receives `plan_id` from
   the setup alert (`alert_embeds.py:298`), simple mirror (`:381`), strategy
   alert and mirror (`:32`, `:52`), execution tickets (`execution_embeds.py:48`),
   lifecycle embeds (`lifecycle_embeds.py:130`, `:253`, `:394`), the
   Breakdown button (`commands/views.py:170`) and `!trade` (`commands/trades.py:307`).
5. **Only the RS gate has a live threshold.** `RS_GATE` default on, bearish
   arm `RS_LAGGARD_PERCENTILE` = 25, bullish arm `RS_LEADER_PERCENTILE` = 0
   (disabled) (`config.py:363-394`, applied in `swingbot/core/edge/rs_gate.py:28`).
   Regime gating is off by default (`REGIME_GATES_ENABLED`, `config.py:941`)
   and `days_to_earnings` is `None` on every plan today
   (`risk_features.py:63-65`). Thresholds are **not** frozen on the plan.
6. **A route the server does not know 404s on reload.** `spa.py:47-51`
   `WORKSPACES` must list `plans`, or `/plans/<id>` works by click and 404s
   from a Discord link.

## API — one changed endpoint, no new one

`GET /api/v1/trades/<id>` gains five keys on `detail`, in both
`_plan_detail` (`trades.py:652`) and `_legacy_detail` (`:690`) — one shape
for both origins, as that module already insists (`:690-696`):

| Key | Plan-backed | Legacy | Notes |
|---|---|---|---|
| `entry_context` | plan's, else trade's | trade's, else `{}` | only the four gate keys plus `htf_aligned` are sent, not the full feature dict |
| `risk_features` | plan's, else trade's | trade's, else `{}` | whole dict (small, fixed keys) |
| `cohort_label` | `plan.cohort_label` | `None` | |
| `confidence_points` | trade's, else plan's, else `None` | trade's, else `None` | v146's numeric factor→points map; passed through untouched |
| `gates` | `gate_rows(...)` | `gate_rows(...)` | list, computed server-side (below) |

The plan's copy wins for `entry_context`/`risk_features` because it is the
record frozen at the creating bar; the trade's copy is the same value logged
from it (`scan_run.py:997-998`) and is the fallback for an older plan.

**Where `confidence_points` is stored is v146's decision.** This spec only
reads the key `confidence_points` from the trade doc, then the plan doc.
v146's spec is not in the repo at writing; the plan's first task confirms the
key name and shape against it and changes only the read site if they differ.

### `gate_rows` — `swingbot/core/presentation/why_view.py` (new, pure)

`gate_rows(direction, entry_context, risk_features, cohort_label) -> list[dict]`,
no I/O beyond reading `config` attributes. One row per gate:

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
| RS | `rs_combined`, else `rs_pctile` | bearish: `RS_LAGGARD_PERCENTILE`, margin = threshold − value; bullish: `RS_LEADER_PERCENTILE`, margin = value − threshold | `RS_GATE` and the arm's threshold is live (bullish leader > 0) |
| Regime | `regime2_state` | none | `REGIME_GATES_ENABLED`; `note` = `cohort_label` |
| Earnings | `risk_features.days_to_earnings` | none | False while the value is `None`; `note` = "not recorded on this plan" |

`parts` for RS: `rs_pctile` (ticker), `sector_pctile` (sector). Missing
values are `None`, never a sentinel; the frontend renders them as "—".

The threshold is today's config. The panel says so in one muted line
("margins against current thresholds"), because a plan issued before a
threshold change would otherwise read as having been gated by a value it
never met.

## Frontend

### Extracted shared components — `frontend/src/app/workspaces/trades/why/`

| Component | Extracted from | Inputs |
|---|---|---|
| `why-panel.ts` (`sb-why-panel`) | `trade-detail.ts:210-226` (sources) and `:325-381` (explanation, Confirmed by, Confidence, Quality) | the store's derived signals, passed as plain inputs; `[sections]` |
| `outcome-path.ts` (`sb-outcome-path`) | `:497-550` (Scale-out legs, Timeline) | `legs`, `timeline` |
| `plan-chart.ts` (`sb-plan-chart`) | `:551-563` and `chartCaption`/`chartEmpty` (`:1133-1150`) | reads `ChartStore` from its injector |

The extraction is behaviour-preserving for the trade page: same panels, same
text, same order within each tab; its existing `trade-detail.spec.ts`
assertions keep passing unchanged except for selectors that move into a child.

**Why panel sections**, in order (`sections` input selects which render):

1. **Levels & methods** — one row per level (Entry/Trigger, Stop, Target 1,
   Target 2) with its price and the methods that confirmed it
   (`targetSources`, `stopSources`, `target2Sources`, store `:269-271`);
   `confirmed_by` strategies (`:261-262`) beneath; `acceptance_level` when set.
   The trade page's Levels panel drops its `.sources` block — the Why panel
   is now the one place sources render.
2. **Confidence** — when `confidence_points` is a non-empty record: factor,
   signed points, the matching `confidence_breakdown` note if one shares the
   key, and a total row. Otherwise the existing text rows
   (`toConfidenceFactors`, store `:118-127`). Quality breakdown (already
   numeric) follows unchanged.
3. **Gate margins** — one row per `gates` entry: label, value, threshold,
   signed margin coloured pos/neg, a muted "off" chip when `applies` is
   false, `parts` inline. The "current thresholds" line beneath.
4. **Why this trade** — the `explanation` prose, unchanged.

Chart and outcome path are their own shared components (above) rather than
Why-panel sections, so each page places them where its layout wants them.

**Store** (`trade-detail.store.ts`): new computeds `confidencePoints`,
`gates`, `entryContext`, `riskFeatures`, each defensive in the file's
existing style (`isRecord`/`asNumber`). `detailAbsent` (`:364-375`) is
unchanged — an old trade with no detail still gets the "logged before" note.
**Models** (`frontend/src/app/api/models.ts:173-211`): `TradeDetailFields`
gains the five keys, plus `GateRow`.

### Trade page

Plan tab: Levels / Per share / If it gets there / Sizing / Opened panels as
now, then `<sb-why-panel>` with all four sections in place of `:325-381`.
Live tab: `<sb-outcome-path>`. Chart tab: `<sb-plan-chart>`. Nothing else on
the page changes; actions stay on the trade page only.

### Plan page — `frontend/src/app/workspaces/plans/`

`plan-detail.routes.ts` mirrors `trade-detail.routes.ts`: providers
`[TradeDetailStore, ChartStore]`, the same `resolveRoute` →
`store.setId(id, false); store.resolve()`, events `onEvents('trades', 'journal')`.
`app.routes.ts` gains `plans/:id` (`canMatch: [authGuard]`, title
`Plan detail`, subtitle `Why this plan, and how it is going`) beside
`trades/:id`.

`plan-detail.ts` (`sb-plan-detail`) is one scrolling page, no tabs:

1. Header — ticker, direction, status indicator, strategy · horizon, badge,
   `Lv` chip, created date; for PENDING the trigger and bars to expiry
   (`bars_to_expiry` on the row).
2. A compact levels line (Entry/Trigger · Stop · T1 · T2 · R:R).
3. `<sb-why-panel>` — all four sections.
4. `<sb-plan-chart>`.
5. `<sb-outcome-path>` — for PENDING, the timeline alone (no legs yet).
6. A link "Open the full trade record" → `/trades/:id`.

**Redirects** (`router.navigate([...], { replaceUrl: true })`, so Back is not a loop):

| Case | Goes to |
|---|---|
| status CLOSED or CANCELLED | `/trades/:id` — a Discord link outlives the plan's open life and must still land |
| id is not plan-shaped (legacy trade id) | `/trades/:id` |
| 404 | the page's own error state (`sb-async`), not a redirect |

**Server routing:** `swingbot/admin/spa.py:47` `WORKSPACES` gains `"plans"`.
No existing `/plans` rule exists in the admin app, so both rules register.

## Discord link

**Config:** new field `ADMIN_PUBLIC_URL` in the Admin UI group of
`swingbot/config.py` (beside `ADMIN_PORT`, `:727`), `type="text"`,
`default=""`, hot-reloadable (the bot reads it at embed-build time; SIGHUP
picks it up). Help text: the base URL *as reached from the device you click
Discord on* — e.g. the Cloudflare tunnel hostname; empty = no link. Added to
`.env.example` beside `ADMIN_PORT`.

**Rendering:** `apply_chrome` (`components.py:64`) sets `embed.url` to
`plan_link(plan_id)` when that returns a value. `plan_link(plan_id) -> str | None`
lives in `components.py`: `None` when `plan_id` is falsy or
`ADMIN_PUBLIC_URL` is empty or does not start with `http://`/`https://`
(logged once at WARNING per process, not per embed); otherwise
`f"{base.rstrip('/')}/plans/{plan_id}"`. The title becomes the link; footer,
push line and field order are untouched.

Why the title URL and not a link button on `PlanActionView`
(`commands/views.py:46`): the view times out after 180 s and `on_timeout`
disables every child (`commands/views.py:68-76`), so a link button would go dead on every
alert within three minutes; and only the setup alert carries the view, while
`apply_chrome` reaches every plan-carrying embed listed in fact 4 at once.

**v152 notification messages** get the link by the same contract: any
message built through `apply_chrome(..., plan_id=...)` links. v152's spec is
not in the repo at writing; if its messages bypass `apply_chrome`, v152 calls
`plan_link` itself. This spec adds nothing to v152's files.

**Production:** setting `ADMIN_PUBLIC_URL` on the VM is a `.env` change and
follows `mirror-prod`. The value is the partner's call (which hostname is
reachable from the phone); the plan asks for it rather than guessing, and the
feature is inert until it is set.

## Edge cases

| Case | Handling |
|---|---|
| PENDING plan | Why panel full (sources come via the placeholder trade row); outcome path shows the timeline only |
| Plan with no trade row | `*_sources`, `confidence_breakdown`, `confirmed_by` empty → those sub-rows hidden; gates still render from the plan's own `entry_context` |
| `confidence_points` absent (pre-v146, or v146 not merged) | text breakdown, exactly as today |
| `confidence_points` present but `confidence_breakdown` missing a key | points row with no note |
| `entry_context` empty (pre-v87 plans) | gate rows with `value: null`, rendered "—"; never hidden, so "not recorded" is visible |
| FX / futures / index (RS-exempt) | RS row `applies: false`, note "exempt" when `rs_combined` is null |
| `ADMIN_PUBLIC_URL` unset or malformed | no `embed.url`; embeds byte-identical to today apart from that |
| Plan closes while the page is open | the store reloads on the `trades` event (route data); the redirect check runs on every load |

## Testing

**pytest**
- `tests/admin/test_api_v1_trades.py`: detail of a plan-backed row carries
  the five keys; plan `entry_context` wins over the trade's; legacy row has
  the same keys (`cohort_label: None`); `confidence_points` absent → `None`,
  present → passed through; `gates` present on both origins.
- `tests/presentation/test_why_view.py` (new): RS bearish pass and fail
  margins, bullish arm disabled at 0, `RS_GATE` off, `rs_combined` missing →
  falls back to `rs_pctile`, all-missing → `None` values; regime row carries
  cohort note; earnings `None` → `applies: false`.
- `tests/presentation/test_components.py`: `apply_chrome` sets `embed.url`
  with a valid base; no url when unset, malformed, or `plan_id` is None;
  trailing slash handled; footer unchanged.
- `tests/admin/test_spa_serving.py`: `/plans/<uuid>` reloads into the SPA
  (add to the `:80` parametrization and the workspace list).
- Config: the new field loads, defaults empty, hot-reloads.

**Vitest** (one spec per component)
- `why-panel.spec.ts`: each section renders from a fixture; points vs text
  fallback; gate margin sign classes; "off" chip; `sections` input hides sections.
- `outcome-path.spec.ts`: legs (realized preferred over live), timeline, pending (timeline only).
- `plan-chart.spec.ts`: caption, empty, retry.
- `plan-detail.spec.ts`: renders an ACTIVE plan; redirects CLOSED, CANCELLED
  and a legacy id to `/trades/:id` with `replaceUrl`; 404 shows the error state.
- `trade-detail.spec.ts`: existing suite green; the Plan tab now hosts
  `sb-why-panel`; sources no longer render twice.
- `app.routes.spec.ts`: `plans/:id` matches behind `authGuard`.

Every new or changed function under cyclomatic complexity 15
(`radon cc -s -n C`); `get_trade` and both detail builders must not get worse.

## Parallelisation

- **Sequential first:** `why_view.py` + its tests, then the endpoint change
  in `trades.py` (it calls `gate_rows`), then `models.ts` + store computeds
  (they mirror the endpoint's shape).
- **Group A (parallel, after the store):** `why-panel.ts`, `outcome-path.ts`,
  `plan-chart.ts` — one new file each, each consuming only store signals.
- **Group B (parallel with everything above — disjoint files, no contract
  dependency on the API):** `ADMIN_PUBLIC_URL` config field + `.env.example`;
  `plan_link` + `apply_chrome` in `components.py` (consumes only the config
  field — sequence it after the field inside Group B); `spa.py` `"plans"`.
- **Sequential after Group A:** `trade-detail.ts` refactor onto the three
  components (one file, consumes all three). Then `plan-detail.ts` +
  routes + `app.routes.ts` (consumes the same three and the store).
- **Last:** `python scripts/dev/testrun.py full` and `cd frontend && npm test`, once each.
- **Production, after merge and deploy:** set `ADMIN_PUBLIC_URL` on the VM
  with the partner's value, mirrored per `mirror-prod`.

## Out of scope

- Re-pointing existing list links (Trades, Dashboard, Calendar, Risk) from
  `/trades/:id` to `/plans/:id` — the plan page is reached from Discord and
  the trade page's own link back.
- Actions (cancel, close, note) on the plan page — the trade page keeps them.
- Computing `confidence_points` or `days_to_earnings` — v146's.
- Freezing gate thresholds onto the plan at issuance.
- Any change to what an alert contains beyond the title link.
