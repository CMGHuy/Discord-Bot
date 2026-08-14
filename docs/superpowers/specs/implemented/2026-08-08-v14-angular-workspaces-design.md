# The six workspaces

**Date:** 2026-08-08
**Version:** ui 1.0.9 · bot 1.1.2
**Status:** design agreed, not implemented
**Scope:** design only — component contracts and per-workspace composition

## Why this exists

The admin UI is being rebuilt as an Angular SPA. That migration is too large for
one spec, so it is split into six sub-projects:

| # | Sub-project | Status |
|---|---|---|
| 1 | REST API for the whole admin surface | agreed (`2026-08-08-v11-admin-rest-api-design.md`) |
| 2 | Real-time event push (bot → admin) | agreed (`2026-08-08-v12-realtime-push-design.md`) |
| 3 | Design system | agreed (`2026-08-08-v20-admin-design-system-design.md`) |
| 4 | Angular shell + build/deploy/auth | agreed (`2026-08-08-v13-angular-shell-design.md`) |
| 5 | **The workspace implementations** | **this document** |
| 6 | Cutover, delete Jinja | not started |

This is the largest sub-project — it is where the actual UI gets built. It
assumes the API exists (1), events flow (2), the visual language is settled (3),
and the shell boots with routing, stores and auth working (4).

**Sub-project 3 is the input, not a starting point for renegotiation.** Its
tokens, type scale, spacing, six-workspace IA and component inventory are used
verbatim. Where this document seems to restate them, spec 3 wins.

## Decision 1 — The data table is built first, alone

Sub-project 3 is explicit: the data table "is the load-bearing component — it
appears in Trades, Analytics, Universe and Risk, and carries the column picker
and row expansion. It should be specified and built first, and the other
workspaces should not begin until it is settled."

**This is a hard sequencing constraint, not a suggestion.** Four workspaces
depend on it. Discovering its API is wrong after three of them are built means
rewriting three workspaces.

"Settled" means: built, used by the Trades list, and reviewed against the other
three intended call sites on paper — not merely compiling.

### `DataTableComponent` contract

Generic over the row type, fully driven by inputs, owning **no** data fetching.

```ts
// Inputs
rows      = input.required<T[]>();
columns   = input.required<ColumnDef<T>[]>();   // full set; visibility is a separate input
visible   = input.required<string[]>();          // column keys, in DESIGNED order — see below
total     = input.required<number>();            // post-filter, pre-slice (API contract)
page      = input.required<number>();
perPage   = input.required<number>();
sort      = input<SortSpec | null>(null);
loading   = input<boolean>(false);
rowKey    = input.required<(row: T) => string>();
expansion = input<TemplateRef<{ $implicit: T }> | null>(null);
emptyState= input<{ title: string; hint?: string } | null>(null);

// Outputs
sortChange, pageChange, visibleChange, rowActivate
```

Five properties this contract deliberately enforces:

1. **Server-side everything.** Sorting, filtering and paging emit events; the
   table never slices its own rows. The API already works this way
   (`_query_closed_trades()` and sub-project 1's collection convention), and a
   table that sorts the current page is the bug that convention was written to
   prevent.
2. **`visible` is a list of keys, and order is ignored.** Rendering order comes
   from `columns`. This is what physically retires the drag-to-reorder
   machinery sub-project 3 removed — the component offers no way to express an
   order, so the old behaviour cannot creep back through a call site.
3. **Row expansion is a caller's template**, not a config object. Every
   workspace expands into something different, and the alternative is a
   configuration language that slowly reinvents templates.
4. **`total` is the post-filter, pre-slice count.** Stated in the contract
   because a table that receives `rows.length` will silently show one page.
5. **No data access.** The table cannot fetch, cannot know a store exists.

### `ColumnPickerComponent`

Sub-project 3's three constraints are enforced structurally, not by discipline:

1. **"Reset to default" is always present**, and the default set is passed in as
   a distinct input from the current set — so the designed state is a first-class
   thing the component knows about, not the first entry in a list of presets.
2. **Visibility only.** No ordering affordance exists (see above).
3. **Persists per user** via the `PreferencesStore` from sub-project 4, keyed by
   table id, stored server-side.

## Decision 2 — Component build order

Nothing in the six workspaces starts until phase A finishes. Within B, the order
is by how many workspaces are blocked.

**Phase A — the table.** `DataTableComponent`, `ColumnPickerComponent`,
`PaginationComponent`, `EmptyStateComponent`.

**Phase B — shared display.** `MetricCard` (large) · `MetricChip` (compact) ·
`Sparkline` · `StatusIndicator` (dot + SL→TP progress bar) · `Chip` (tier,
horizon, confidence) · `ChartContainer`.

**Phase C — shared input and layout.** `Button` (primary/secondary/danger/
ghost/icon) · `Select` · `TextInput` · `Checkbox` · `FilterBar` · `ConfirmDialog`
· `Panel` · `TabBar` · `SplitView` · `Drawer`.

That is sub-project 3's inventory exactly. **Nothing outside it gets built
without amending that spec** — the inventory is what stops the drift into
"components that nearly match" which spec 3 named as a root cause.

**The chip components are where spec 3's colour rule bites.** Confidence level,
confidence score and tier chips must render on the greyscale ramp
(`Lv5/A` → `--text`, `Lv3/B` → `--text-secondary`, `Lv1/C` → `--warn`), never
green/amber/red. This is the single easiest decision to accidentally revert by
copying the current UI's styling, and it should be called out in review.

## Decision 3 — Workspace order

**Trades → Cockpit → Analytics → Risk → System → Universe.**

Trades first, not Cockpit, even though Cockpit is the landing page. Trades is
the workspace that exercises the table, the expansion, the column picker, the
detail view, the tab bar and the chart — everything the other five reuse. Cockpit
is mostly metric cards and would validate almost nothing.

Universe last: sub-project 3 explicitly rates it "the same shape at lower
priority", so it is the safest thing to be holding when time runs short.

## Decision 4 — Trades

The workspace the whole IA change was for: Plans, Journal, the Dashboard's two
tables and the trade detail page collapse into one entity.

**Routes:** `/trades` (list) · `/trades/:id` (detail)

**List** — `GET /api/v1/trades`, driven entirely by query parameters, which per
sub-project 4 are the source of truth for filter/sort/page state.

Seven default columns, exactly as spec 3 specifies: `#` · Status · Ticker · Now ·
P&L% · Held · actions. The other eleven fields live in row expansion and are
individually re-addable through the column picker.

Row expansion shows the four groups spec 3 names: plan levels (entry/target/stop,
R:R), setup (strategy, horizon, confidence level and score), sizing (shares,
deployed, unrealised amount), and opened timestamp.

**Status is a filter chip row, not a tab strip.** Tabs would reintroduce the
"separate page per state" model this workspace exists to abolish.

Refetches on the `trades` event. Because events are thin, the refetch reissues
the *current query* — it does not reconcile individual rows.

**Detail** — `GET /api/v1/trades/:id`, with `TabBar` over the five tabs spec 3
specifies: **Plan · Live · Chart · Notes · Strategy**.

- *Plan* — entry, stop, TP1/TP2, R:R, sizing.
- *Live* — price, unrealised P&L, `StatusIndicator`'s SL→TP progress bar.
  Refetches on `trades`.
- *Chart* — `ChartContainer` over `GET /api/v1/market/ohlcv/:ticker?trade_id=`,
  which already returns the trade's levels when given `trade_id`.
- *Notes* — was Journal. `PUT /api/v1/trades/:id/note`, debounced autosave, and
  a visible saved/unsaved state. Refetches on `journal`.
- *Strategy* — how this setup has performed historically, from
  `/api/v1/analytics/strategies` filtered to this trade's strategy. Read-only;
  it is a window into Analytics, not a second copy of it.

Actions — close, cancel, delete — go through `ConfirmDialog`. Delete and
clear-open are destructive and irreversible against paper-trade history; the
dialog must name what is being destroyed, not ask "are you sure?".

**Open question resolved:** no saved filters. Spec 3 left this open; the answer
is that query parameters in the URL already make any filter combination
bookmarkable, which is saved filters without a feature. Revisit only if a
specific combination proves genuinely hard to reconstruct.

## Decision 5 — Cockpit

> **Superseded in part by v18 (2026-08-13).** The workspace is now **Dashboard**
> — route `/dashboard`, endpoint `/api/v1/dashboard`, `DashboardStore` — with
> `/cockpit` redirecting. Its "Open positions" table is no longer the fixed
> four-column summary described below: it is the same component, the same two
> density modes and the same column sets as Trades, filtered to open positions.
> Two tables of the same rows behaving differently is a thing to learn twice.
> The header's metric tiers are untouched. See spec v18 Decisions 6 and 7.

**Route:** `/cockpit` (and `/` redirects here)

`GET /api/v1/cockpit`, refetching on `account` and `trades`.

Header is spec 3's two tiers, verbatim:

- **Three `MetricCard`s:** Account balance · Open P&L · Risk used
- **Six `MetricChip`s:** Open trades · Avg confidence · Win rate · Expectancy ·
  Equity 30d (`Sparkline`) · Position premium

Below: a compact trades table — **the same `DataTableComponent`**, filtered to
open positions, capped, with a link into `/trades`. Not a bespoke component, and
not the six metrics that moved to Analytics.

Scan and bot status live in the **shell**, not here. They are global facts, and
duplicating them into Cockpit is how the "one thing in four places" problem
started.

**No card-flash on refresh.** Spec 3 removed it; with push, "something changed"
is continuous rather than a discrete event.

## Decision 6 — Analytics

**Route:** `/analytics`, absorbing Performance, Strategies, Calibration, Tuning.

**Open question resolved: tabs, not sub-navigation.** Spec 3 left this open.
Four sections is within what a `TabBar` carries comfortably, and a second level
of navigation inside one of six workspaces reintroduces exactly the depth the IA
change removed. If a fifth and sixth section ever appear, revisit.

- *Performance* — `GET /api/v1/analytics/performance`. **This is where the six
  relocated Cockpit metrics live** (wins, losses, avg realised P&L, best trade,
  worst trade, avg holding period). They must actually appear here; spec 3
  accepted the cost of moving them, not of losing them.
- *Strategies* — `GET /api/v1/analytics/strategies`, plus the registry. Table.
- *Calibration* — `GET /api/v1/analytics/calibration`: deciles, tiers, drift.
- *Tuning* — proposals list, `POST` to propose, `DELETE` to remove. Proposing
  starts a job; progress comes from `GET /api/v1/jobs/:id` refetched on the
  `jobs` event, replacing today's polling.

Tuning sits here rather than in System because spec 3 decided it: it proposes
parameters from backtests, which is analysis, not administration.

## Decision 7 — Risk

**Route:** `/risk`. `GET /api/v1/risk`, refetching on `risk` and `trades`.

Exposure breakdown as a table, portfolio heat against `PORTFOLIO_HEAT_CAP_PCT`,
and the **killswitch**.

Risk keeps its own destination — spec 3's reasoning — because it owns an
operational control rather than a readout. The killswitch is `danger`-variant,
`ConfirmDialog`-gated, and its current state must be unmistakable from across a
room: when engaged, the shell shows it too, since it changes what the bot does
regardless of which workspace you are looking at.

"Risk used" appears both here and as a Cockpit primary card. That is intended
duplication of a single number, not of a feature.

## Decision 8 — System

**Route:** `/system`, tabs: **Settings · Logs · Scan**.

- *Settings* — `GET /api/v1/system/settings` returns schema **and** values,
  driven by `swingbot/config.py`'s `Field` entries. **The form renders from the
  schema; the SPA hardcodes no field list.** A new setting in `config.py` must
  appear with zero frontend change — this is a property the current UI has and
  the rebuild must not lose. Preview-before-save stays (`POST .../preview` →
  diff → `PUT`). Sensitive values stay masked as `•••`; export still omits them
  entirely rather than masking. On a `settings` event from another session, warn
  rather than silently reloading a form being edited.
- *Logs* — `GET /api/v1/system/logs`, raw view, clear action.
- *Scan* — `GET /api/v1/system/scan` and the four commands (trigger, stop,
  pause, resume). Bot liveness from the heartbeat. Refetches on `scan` and `bot`.

Bot restart lives here, `ConfirmDialog`-gated, and must degrade honestly: the
Docker socket mount is optional in `docker-compose.yml`, so the API can return
`503 unavailable` and the UI must say the button is unavailable in this
deployment rather than reporting a failure.

## Decision 9 — Universe

**Route:** `/universe` (list) · `/universe/:symbol` (detail)

Ticker list with add (single and bulk, one endpoint), remove, and suggest-as-you-
type. Per-ticker detail shows open trades, past trades and a chart — reusing
`DataTableComponent` with a filtered trades query and `ChartContainer`, building
nothing new.

Deliberately the thinnest workspace. Spec 3 rates it lower priority and this
document does not upgrade it.

## Decision 10 — The chart wrapper

One `ChartContainer` component wrapping `lightweight-charts` — **5.x from npm**,
per sub-project 4, not the 4.2.3 vendored for the Jinja UI. The v4→v5 API change
is real and every example predating v5 will mislead; check the migration notes
before writing the wrapper rather than after debugging it.

Requirements: theme from spec 3's tokens (never hardcoded colours), price lines
for entry/stop/targets when a `trade_id` is supplied, resize handling,
disposal on destroy, and `OnPush`-compatible behaviour — the chart owns imperative
canvas state and must not be re-created on every change detection pass.

Used by: Trades detail, Universe detail, and the Cockpit quick-chart modal.
Server-rendered PNG charts are not used anywhere in the SPA; their fate is
sub-project 6's.

## Definition of done

1. Every route in sub-project 4's list renders real data from real endpoints.
2. Every Jinja page has a named successor here — the mapping that sub-project 6
   audits.
3. `DataTableComponent` is used by Trades, Analytics, Universe and Risk. Four
   call sites. A second table implementation anywhere is a defect.
4. The column picker persists server-side, offers no ordering, and resets to the
   designed seven.
5. Killing `/api/v1/events` leaves every workspace correct, just slower. This is
   sub-project 2's stated acceptance criterion and this is where it is tested.
6. Nothing renders green or red except money; nothing renders blue except
   interactive affordances. Reviewed per spec 3's colour rules.
7. Checked at **1280px** — spec 3 flags mono digits as wide and names the
   expansion content as the thing to verify at that width.
8. The Jinja UI still works, untouched.

## Explicitly out of scope

- Deleting Jinja templates or routes (sub-project 6)
- New API endpoints. If a workspace needs something sub-project 1 did not
  specify, that is an amendment to that spec, not a quiet addition here
- Components outside spec 3's inventory
- Mobile and responsive layouts below ~1100px
- Chart rendering internals beyond the container and theme

## Risks

**This sub-project is larger than the other five combined**, and it is the one
where "nearly finished" can persist for a long time. Sequencing by workspace,
with each one done before the next starts, is what makes progress legible —
resist building all six to 80%.

**The table's API will want to grow** as each new call site brings a
requirement. Each addition is fine; the fourth is how a component becomes
unmaintainable. Prefer a caller-supplied template over a new config input.

**Settings is the highest-risk single screen.** It is schema-driven, it masks
secrets, it previews diffs, and getting it wrong can write a broken `.env` that
takes the bot down. It deserves its own tasks and its own tests, and it should
not be the last thing built with time pressure on it.

**Feature parity is judged against a UI nobody has fully enumerated.** Eleven
pages of accumulated behaviour, some of it undocumented. The mapping in the
definition of done is the mitigation, and it must be built *while* the
workspaces are built, not reconstructed at cutover from memory.

**The colour rules are easy to violate by copying the old UI.** The quality-
indicator chips are the specific trap: green/amber/red today, greyscale by
design. Copy the markup and the violation comes with it.

## Open questions

Both of spec 3's deferred questions are answered above (Analytics uses tabs;
the Trades list needs no saved filters). One new one, non-blocking:

1. Whether the Cockpit's open-positions table should share the Trades list's
   persisted column preferences or keep its own. Sharing is simpler; separate is
   probably what a user actually wants, since the contexts differ. Decide when
   Cockpit is built, after Trades has established the preference mechanism.
