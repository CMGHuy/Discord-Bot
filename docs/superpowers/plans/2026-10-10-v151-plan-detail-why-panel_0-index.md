# v151 Plan detail page and the shared "Why" panel: Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V151-4` or `grep -n "^### Task V151-4:" -A 400 docs/superpowers/plans/2026-10-10-v151-plan-detail-why-panel_*.md`.

**Bump:** ui minor · bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v151-plan-detail-why-panel-design.md`](../specs/2026-10-09-v151-plan-detail-why-panel-design.md)

**Goal:** Make the reasons stored on every plan readable in one click. A shared **Why panel** (levels with their confirming methods, confidence points, gate margins against today's thresholds, monthly OPEX in the holding window, the explanation) renders on the trade page and on a new `plans/:id` page for open plans. Every plan-carrying Discord embed links its title to that page.

**Architecture:** One endpoint changes: `GET /api/v1/trades/<id>` gains about a dozen `detail` keys, built by a new admin helper module (`swingbot/admin/trade_why.py`) from two pure functions in a new `swingbot/core/presentation/why_view.py` (`gate_rows`, `calendar_rows`) and one new `SessionCalendar.session_after` method. `core/presentation` still imports no `swingbot.config`: the admin layer builds `GateThresholds`, and embed callers pass `link_base=config.ADMIN_PUBLIC_URL` into `apply_chrome`, which validates it through a pure `plan_link`. On the SPA side, six child components are extracted from `trade-detail.ts` into `workspaces/trades/why/`. They take plain inputs except `sb-plan-chart`, which injects `ChartStore`. The trade page and the new plan page both compose them over the same route-scoped `TradeDetailStore`.

**Tech Stack:** Python 3.11, Flask, discord.py, pytest; Angular 21 (zoneless, signals), `@ngrx/signals`, Vitest.

## Global Constraints

- **Explanation surface only.** No gate, level, exit or alert decision changes. Nothing on the plan page places, edits or cancels an order. The Levels block always carries the muted line `Paper plan — this page places no orders.`
- **No `swingbot.config` import anywhere under `swingbot/core/presentation/`.** `gate_rows` takes `GateThresholds`. `apply_chrome` takes `link_base`. A test (V151-2) asserts this for `why_view.py` and `components.py`.
- **v146 keys are passed through, never computed.** `confidence_points` → `None` when absent. `confidence_unevaluated` → `[]` when absent. The page must work on every record written before v146 (v146 is not on `main` yet). Do not backfill stored plans or trades (`schema-evolution.md`: API-only keys, no read-time upcasting of stored records).
- **One detail shape for both origins.** Every new key exists on `_plan_detail` and `_legacy_detail` alike.
- **Empty is a measured answer** (`known-traps.md`). An empty `gates` value renders "—". An empty `calendar` renders `None in the window`. Gate rows are never hidden.
- Section heading verbatim: `Gate margins (vs today's thresholds)`. Caveat line verbatim, always visible, never collapsible: `Margins are measured against today's thresholds, not the ones in force when this plan was issued.`
- "off" chip tooltip verbatim: `off in current config`. "unevaluated" chip tooltip verbatim: `no data — neutral points awarded`.
- `ADMIN_PUBLIC_URL` validation: accepted only if it contains no whitespace, the scheme is `http` or `https`, and the netloc is non-empty (`urllib.parse.urlsplit`). Anything else yields no `embed.url` and one WARNING per distinct bad value per process. With `link_base` None or empty, `apply_chrome`'s output is byte-identical to today's.
- Every Python function you write or change ends at cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>`). `get_trade`, `_plan_detail` and `_legacy_detail` must not get worse: the new keys arrive as one `**` merge from a helper.
- No in-page `<h1>`; `sb-panel` for cards; any file in `workspaces/<dir>/` that uses `sb-async` also sets `[staleAsOf]` (`workspace-consistency.spec.ts`). A file using `sb-async` never contains the literal class name `skeleton` (`async-coverage.spec.ts`).
- Per-task verification is the narrow run: `python scripts/dev/testrun.py file <test>`, or `npm --prefix frontend test -- --include <spec> --watch=false`. **Never `cd` in Bash** (it breaks the guardrail hooks). Both full suites run once, in V151-17.
- Stage files by name. The working tree carries unrelated modified `.agents/` and `.codex/` files: never `git add -A` / `git add .`.
- **Do not bump `VERSION.json` in any task.** `/close-out` applies `ui minor · bot patch` and regenerates `version_history.json`.

## Decisions fixed by this index

These settle the gaps the brief flagged. Every part writer and implementer treats them as the contract.

1. **`SessionCalendar.session_after(d, n) -> date | None`** (new, V151-1, `swingbot/core/market/session.py`). Returns the session `n` sessions after the session on or before `d`, so `n = 0` is that session itself. Returns `None` when `n < 0` or when either end falls outside coverage. Uses: `expires_on = session_after(created_day, expiry_bars)`, because `pending_expired` fires at `bars_since_created > expiry_bars`, so the last live bar is `created + expiry_bars`. `time_exit_on = session_after(fill_day, hold_cap_bars - 1)`, which matches `tenth_session` (`days[9]` for 10).
2. **Fill day** comes from `swingbot.core.planning.time_exit.fill_day_from_history(plan["status_history"])` (exists, `time_exit.py:62`). Its `ValueError` means "not filled yet", so `time_exit_on` is `None`.
3. **Date parsing.** `created_at` may be an ISO date or a tz-aware datetime string (test fixtures use `"2026-08-01T10:00:00+00:00"`). `_session_day(stamp) -> date | None` in `trade_why.py` parses both, converts aware values to `US_MARKET_TZ`, and returns `None` on garbage.
4. **The admin helper lives in `swingbot/admin/trade_why.py`**, not inside `trades.py` (already 1086 lines) and not under `api_v1/` (that package holds route modules). `_plan_detail` returns `{..., **plan_why_fields(plan, trade)}` and `_legacy_detail` returns `{..., **legacy_why_fields(t)}`. Each adds one line and no branch.
5. **Two extra pass-through detail keys the spec's UI needs but its API table omits:** `hold_cap_bars` (plan's, legacy `None`) for the "time exit after N sessions" line, and `acceptance_level` (plan's, legacy `None`) for the Levels block and the Why panel. Both are read straight off the plan dict.
6. **Detail-endpoint tests go in `tests/admin/test_api_v1_trade_detail.py`.** The spec names `test_api_v1_trades.py`, which only supplies the `_plan` / `_trade` helpers.
7. **The third lifecycle `apply_chrome` call is `lifecycle_embeds.py:407`**, not `:394`.
8. **The Why panel keeps the labels `Target confirmed by` / `Stop confirmed by` / `Target 2 confirmed by`, and the headings `Confirmed by`, `Confidence breakdown` and `Quality breakdown`.** `trade-detail.spec.ts` asserts them. The Levels panel drops its `.sources` block, so sources render exactly once.
9. **`sb-plan-chart` calls `ChartStore.setTarget(ticker, tradeId)` from its own inputs.** `trade-detail.ts` keeps its existing `setTarget` effect. `setTarget` is idempotent (`chart.store.ts:127`), so the chart still preloads on the trade page and the plan page needs no effect of its own.
10. **Arrival banner state.** The plan page navigates with `{ replaceUrl: true, state: { from: 'plan' } }`. The trade page reads `history.state?.from === 'plan'` once at construction, as `protected readonly arrivedFromPlan: boolean`. A direct visit therefore shows no banner.
11. **Routing registrations.** `spa.py` `WORKSPACES` gains `"plans"`. `app.routes.spec.ts`'s readiness `expected` list gains `'plans/:id'`. `async-coverage.spec.ts`'s `FETCHING` gains `'workspaces/plans/plan-detail.ts'`.
12. **RS row semantics** (spec § `gate_rows`, made exact). `value = rs_combined if not None else rs_pctile`. When `value` is `None`: `applies = False`, `margin = None`, `note = "exempt"`. When `rs_gate` is false: `applies = False`, `margin = None`, `note = "RS gate off"`. When the bullish arm has `rs_leader_pct <= 0`: `applies = False`, `margin = None`, `note = "bullish arm disabled"`. `threshold` is always the configured number for the direction's arm. Regime and earnings rows always carry `threshold = None` and `margin = None`.

## Wire contract (fixed here; V151-3 produces it, V151-8 consumes it)

New keys on `detail`, both origins:

| Key | Python type | TypeScript (`TradeDetailFields`) |
|---|---|---|
| `entry_context` | `dict` filtered to `WIRE_CONTEXT_KEYS = ("regime2_state", "rs_pctile", "sector_pctile", "rs_combined", "htf_aligned", "gap_p90_pct", "gap_fragile")` | `Record<string, unknown>` |
| `risk_features` | `dict` | `Record<string, unknown>` |
| `cohort_label` | `str \| None` | `string \| null` |
| `confidence_points` | `dict \| None` | `Record<string, number> \| null` |
| `confidence_unevaluated` | `list` | `string[]` |
| `gates` | `list[dict]` (`gate_rows`) | `GateRow[]` |
| `sessions_since_created` | `int \| None` | `number \| null` |
| `expires_on` | ISO `str \| None` | `string \| null` |
| `time_exit_on` | ISO `str \| None` | `string \| null` |
| `calendar` | `list[dict]` (`calendar_rows`) | `CalendarRow[]` |
| `hold_cap_bars` | `int \| None` | `number \| null` |
| `acceptance_level` | `float \| None` | `number \| null` |

```ts
// frontend/src/app/api/models.ts (V151-8)
export type GateKey = 'rs' | 'regime' | 'earnings';
export interface GatePart { label: string; value: number | string | null; }
export interface GateRow {
  key: GateKey; label: string; value: number | string | null;
  threshold: number | null; margin: number | null; applies: boolean;
  parts: GatePart[]; note: string | null;
}
export interface CalendarRow { date: string; kind: 'opex_monthly'; label: string; }
```

Gate labels (Python, V151-2): RS `"Relative strength"`, parts `"Ticker RS pctile"` (`rs_pctile`) and `"Sector RS pctile"` (`sector_pctile`); Regime `"Regime"`, parts `[]`; Earnings `"Days to earnings"`, parts `[]`. Calendar row: `{"date": "<ISO>", "kind": "opex_monthly", "label": "Monthly OPEX"}`.

## Parts

| Part | File | Tasks | Content |
|---|---|---|---|
| 0 | `_0-index` (this file) | none | Header, constraints, decisions, wire contract, ledger, parallelisation |
| 1 | [`_1-api-and-discord-link`](2026-10-10-v151-plan-detail-why-panel_1-api-and-discord-link.md) | V151-1 .. V151-7 | `session_after`, `why_view.py`, the detail endpoint, `ADMIN_PUBLIC_URL`, `plan_link` + `apply_chrome(link_base=)`, the caller kwarg, `spa.py` |
| 2 | [`_2-store-and-why-components`](2026-10-10-v151-plan-detail-why-panel_2-store-and-why-components.md) | V151-8 .. V151-12 | Models + store computeds, `sb-why-panel`, `sb-levels-block`, `sb-if-it-gets-there`, `sb-sizing-panel` |
| 3 | [`_3-shared-components-and-pages`](2026-10-10-v151-plan-detail-why-panel_3-shared-components-and-pages.md) | V151-13 .. V151-17 | `sb-outcome-path`, `sb-plan-chart`, the trade-page refactor + arrival banner, the plan page + routes, both full suites |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Symbols produced for later tasks |
|---|---|---|---|---|---|
| V151-1 | `SessionCalendar.session_after` | 1 | haiku | M `swingbot/core/market/session.py`; M `tests/market/test_session_calendar.py` | `SessionCalendar.session_after(self, d: dt.date, n: int) -> dt.date \| None` |
| V151-2 | `why_view.py`: `GateThresholds`, `gate_rows`, `calendar_rows` | 1 | sonnet | C `swingbot/core/presentation/why_view.py`; C `tests/presentation/test_why_view.py` | `@dataclass(frozen=True) GateThresholds(rs_gate: bool, rs_laggard_pct: float, rs_leader_pct: float, regime_gates: bool)`; `gate_rows(direction: str \| None, entry_context: dict, risk_features: dict, cohort_label: str \| None, thresholds: GateThresholds) -> list[dict]`; `calendar_rows(start: dt.date, end: dt.date) -> list[dict]` |
| V151-3 | Detail endpoint: the new `detail` keys | 1 | sonnet | C `swingbot/admin/trade_why.py`; M `swingbot/admin/api_v1/trades.py` (`_plan_detail`, `_legacy_detail`); M `tests/admin/test_api_v1_trade_detail.py` | `WIRE_CONTEXT_KEYS: tuple[str, ...]`; `gate_thresholds() -> GateThresholds`; `plan_why_fields(plan: dict, trade: dict \| None, today: dt.date \| None = None) -> dict`; `legacy_why_fields(trade: dict, today: dt.date \| None = None) -> dict`; `_session_day(stamp) -> dt.date \| None`; `_today() -> dt.date` (ET); the wire keys in § Wire contract |
| V151-4 | `ADMIN_PUBLIC_URL` config field | 1 | haiku | M `swingbot/config.py` (Discord Alerts group, beside `ALERT_EMBED_LAYOUT`); M `.env.example`; C `tests/test_config_admin_public_url.py` | `config.ADMIN_PUBLIC_URL: str` (default `""`, `type="text"`, `hot_reloadable=True`) |
| V151-5 | `plan_link` + `apply_chrome(link_base=)` | 1 | sonnet | M `swingbot/core/presentation/components.py`; M `tests/presentation/test_components.py` | `plan_link(plan_id: str \| None, base: str \| None) -> str \| None`; `apply_chrome(..., link_base: str \| None = None)` sets `embed.url`; module-level `_WARNED_BASES: set[str]` |
| V151-6 | Embed callers pass `link_base=config.ADMIN_PUBLIC_URL` | 1 | sonnet | M `swingbot/core/scanning/alert_embeds.py` (:32, :52, :298, :381); M `swingbot/core/scanning/execution_embeds.py` (:48); M `swingbot/core/scanning/lifecycle_embeds.py` (:130, :253, :407); M `swingbot/commands/views.py` (:170); M `swingbot/commands/trades.py` (:307); C `tests/scanning/test_embed_plan_link.py` | none |
| V151-7 | SPA serves `/plans/<id>` on reload | 1 | haiku | M `swingbot/admin/spa.py` (`WORKSPACES`); M `tests/admin/test_spa_serving.py` | `"plans"` in `WORKSPACES` |
| V151-8 | Models + `TradeDetailStore` computeds | 2 | sonnet | M `frontend/src/app/api/models.ts`; M `frontend/src/app/stores/trade-detail.store.ts`; M `frontend/src/app/stores/trade-detail.narrowing.spec.ts` | `GateKey`, `GatePart`, `GateRow`, `CalendarRow` (models.ts); `TradeDetailFields` + the 12 keys; store computeds `confidencePoints: Record<string, number> \| null` (null when absent, non-record or empty), `confidenceUnevaluated: string[]`, `gates: GateRow[]`, `calendar: CalendarRow[]`, `entryContext: Record<string, unknown>`, `riskFeatures: Record<string, unknown>`, `sessionsSinceCreated: number \| null`, `expiresOn: string \| null`, `timeExitOn: string \| null`, `holdCapBars: number \| null`, `acceptanceLevel: number \| null`, `gapP90Pct: number \| null`, `gapFragile: boolean \| null` |
| V151-9 | `sb-why-panel` | 2 | sonnet | C `frontend/src/app/workspaces/trades/why/why-panel.ts`; C `frontend/src/app/workspaces/trades/why/why-panel.spec.ts` | `WhyPanel` (`sb-why-panel`); `type WhySection = 'levels' \| 'confidence' \| 'gates' \| 'calendar' \| 'explanation'`; `WHY_SECTIONS: readonly WhySection[]` (all five, in order); `GATE_CAVEAT: string`; `marginTone(status: string \| null, barsToExpiry: number \| null, sessionsSinceCreated: number \| null): 'signed' \| 'neutral' \| 'indicative'`; inputs: `sections` (default `WHY_SECTIONS`), `status`, `barsToExpiry`, `sessionsSinceCreated`, `entry`, `trigger`, `stop`, `stopLabel` (default `'Stop'`), `target1`, `target2`, `targetSources`, `stopSources`, `target2Sources`, `confirmedBy: Confirmation[]`, `acceptanceLevel`, `confidencePoints`, `confidenceUnevaluated`, `confidenceFactors: ConfidenceFactor[]`, `qualityFactors: QualityFactor[]`, `gates: GateRow[]`, `calendar: CalendarRow[]`, `explanation: string \| null` |
| V151-10 | `sb-levels-block` (order-ready) | 2 | sonnet | C `frontend/src/app/workspaces/trades/why/levels-block.ts`; C `frontend/src/app/workspaces/trades/why/levels-block.spec.ts` | `LevelsBlock` (`sb-levels-block`); `entryTypeWord(entryType: string \| null, direction: string \| null): string`; `PAPER_LINE = 'Paper plan — this page places no orders.'`; inputs: `direction`, `entryType`, `trigger`, `entry`, `stop`, `stopLabel` (default `'Stop'`), `target1`, `target2`, `riskReward`, `acceptanceLevel`, `tp1Pct`, `breakevenTriggerPct` (all `number \| null` / `string \| null`, default `null`) |
| V151-11 | `sb-if-it-gets-there` | 2 | haiku | C `frontend/src/app/workspaces/trades/why/if-it-gets-there.ts`; C `frontend/src/app/workspaces/trades/why/if-it-gets-there.spec.ts` | `IfItGetsThere` (`sb-if-it-gets-there`); inputs `direction: string \| null`, `target2: number \| null`, `stopLoss: number \| null` |
| V151-12 | `sb-sizing-panel` + gap-risk row | 2 | sonnet | C `frontend/src/app/workspaces/trades/why/sizing-panel.ts`; C `frontend/src/app/workspaces/trades/why/sizing-panel.spec.ts` | `SizingPanel` (`sb-sizing-panel`); inputs `shares`, `positionValue`, `sizingMode`, `workingStop`, `gapP90Pct: number \| null`, `gapFragile: boolean \| null` |
| V151-13 | `sb-outcome-path` | 3 | sonnet | C `frontend/src/app/workspaces/trades/why/outcome-path.ts`; C `frontend/src/app/workspaces/trades/why/outcome-path.spec.ts` | `OutcomePath` (`sb-outcome-path`); inputs `legs: Leg[]` (default `[]`), `timeline: StatusEvent[]` (default `[]`) |
| V151-14 | `sb-plan-chart` | 3 | sonnet | C `frontend/src/app/workspaces/trades/why/plan-chart.ts`; C `frontend/src/app/workspaces/trades/why/plan-chart.spec.ts` | `PlanChart` (`sb-plan-chart`); inputs `ticker: string \| null`, `tradeId: string \| null`; injects `ChartStore`, calls `setTarget(ticker, tradeId)` in an effect |
| V151-15 | Trade page onto the shared components + arrival banner | 3 | sonnet | M `frontend/src/app/workspaces/trades/trade-detail.ts`; M `frontend/src/app/workspaces/trades/trade-detail.spec.ts` | `TradeDetail.arrivedFromPlan: boolean`; `arrivalBanner(status: string \| null, barsToExpiry: number \| null): string` (exported from `trade-detail.ts`) |
| V151-16 | Plan page `plans/:id` + routes + redirects | 3 | sonnet | C `frontend/src/app/workspaces/plans/plan-detail.ts`; C `frontend/src/app/workspaces/plans/plan-detail.routes.ts`; C `frontend/src/app/workspaces/plans/plan-detail.spec.ts`; M `frontend/src/app/app.routes.ts`; M `frontend/src/app/app.routes.spec.ts`; M `frontend/src/app/ui/async-coverage.spec.ts` | `PlanDetail` (`sb-plan-detail`); `planDetailRoutes: Routes`; `looksLikePlanId(id: string): boolean`; `redirectFor(status: string \| null, barsToExpiry: number \| null): 'banner' \| null` |
| V151-17 | Full suites, complexity check | 3 | haiku | none | none |

## Parallelisation

Parallel tasks need disjoint files and no contract dependency. Every sequential edge is listed with its reason.

- **Chain A (API):** V151-1 → V151-3 (`plan_why_fields` calls `session_after`). V151-2 → V151-3 (it calls `gate_rows` / `calendar_rows` and builds `GateThresholds`). V151-1 and V151-2 can run in parallel: disjoint files, no shared symbol.
- **Group B (bot link), parallel with Chain A:** V151-4 ∥ V151-5 (disjoint files). V151-5 ∥ V151-2 touch different files in the same package. They share no symbol, but the V151-2 no-config test reads `components.py`, so run V151-2's test again after V151-5 lands. V151-6 comes after V151-4 (it reads `config.ADMIN_PUBLIC_URL`) and after V151-5 (it passes `link_base=`). V151-7 is independent of everything.
- **V151-3 → V151-8.** The models mirror the endpoint's shape. The shape is fixed above, but the spec orders it so the store spec's fixtures can be checked against a real response.
- **Group A (components), after V151-8, all parallel:** V151-9, V151-10, V151-11, V151-12, V151-13, V151-14. Each creates its own files. Each imports from `trade-detail.store.ts` / `models.ts` only the types V151-8 fixes (`Confirmation`, `ConfidenceFactor`, `QualityFactor`, `Leg`, `StatusEvent`, `GateRow`, `CalendarRow`).
- **V151-15 after all of Group A**, because it replaces template regions with those six components. It is one file plus its spec.
- **V151-16 after V151-15.** It consumes the same components, and its redirect lands on the trade page whose banner V151-15 adds (the `state: { from: 'plan' }` contract). Their files are disjoint, but the spec orders them and `plan-detail.spec.ts` asserts against V151-15's banner state.
- **V151-17 last.** It runs both full suites once: `python scripts/dev/testrun.py full` (via the `test-runner` agent) and `npm --prefix frontend test -- --watch=false`.

## After merge (not a plan task)

- **Partner decision:** the value of `ADMIN_PUBLIC_URL` on the VM. With the admin reachable only through the SSH tunnel, the link does nothing on a phone. Exposing it (for example through the Cloudflare tunnel) is the partner's call. Ask with `AskUserQuestion`. Never guess.
- Setting it is a VM `.env` change under `mirror-prod`: edit in place (never `sed -i` the bind-mounted `.env`), SIGHUP the bot, verify, and mirror the change into the repo.
- Rollback: `ADMIN_PUBLIC_URL=` and SIGHUP. For the UI half, the previous image. `scripts/ops/rollback_to.sh` only as a last resort.
- v152's builder (`swingbot/commands/scanning/follow_notify.py`) passes `link_base=config.ADMIN_PUBLIC_URL` to `apply_chrome`. That is v152's plan, not this one.
