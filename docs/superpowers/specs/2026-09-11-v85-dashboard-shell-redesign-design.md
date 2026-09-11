# v85 — Dashboard and shell redesign

Version: ui 1.15.1 · bot 1.7.1
Bump: ui minor · bot patch
Edge: none (integrity)

## What this is

A visual and structural redesign of the admin SPA's shared chrome (top bar,
left nav) and of the Dashboard workspace, following a supplied mockup
(`images/Mock up.png`, `images/Mock up full view.png`), plus a restyle pass
over the remaining seven workspaces so nothing sits inside new chrome wearing
old clothes.

`Bump: ui minor` follows the `ui 1.2.0` precedent — "the SPA refresh (plan
v21): every workspace rebuilt" — which is what this is. `bot patch`: the bot
gains one metric and one endpoint; how it trades is untouched.

`Edge: none (integrity)` — this buys no expectancy, no harvest, no volume. It
is operator tooling. Stated rather than dressed up.

## What the mockup is not

The mockup is branded "Bomeo Capital" and shows pages this bot does not have
(Markets, Portfolio, Strategies, Journal), a fictional €997,480 book, an
intraday equity curve, a command palette, and a notification centre. It is a
visual reference, not a requirements document. Everything below that says
"drop" or "omit" is a deliberate refusal to build a facade over data that does
not exist.

## Findings established during the brainstorm

These were verified in the code, not assumed. They constrain the design.

1. **The theme already is the mockup's palette.** `frontend/src/styles/tokens.css`
   defines `--bg: #0c0f16`, `--surface: #131722`, `--pos: #17c98e`,
   `--neg: #ff5470`, `--accent: #5593ff`. No shared-token retune is needed —
   only additions (a hero-size type token; the scale currently tops out at
   `--text-metric: 28px` and the mockup's portfolio figure is roughly double).
2. **Expectancy already is mean realised R.** `expectancy_r` in
   `swingbot/core/analytics/metrics.py:220` is "mean `r_multiple()` over closed
   trades". An "Avg realised R" metric would print the same number twice under
   two labels. Resolved in D9.
3. **`clear_open()` deletes, it does not close.**
   `swingbot/core/tracking/performance.py:1267` drops every `status='open'`
   record and saves to disk immediately. It realises nothing. The "close all"
   action in D13 must therefore be built, never wired to this.
4. **There is no create-trade endpoint.** The bot authors plans; the admin
   never does. The mockup's "+ New Trade" button has nothing behind it.
5. **`TradeGroup` is used only by the Dashboard** (`dashboard.ts`, its own
   spec, and `trades.store.spec.ts`). Rebuilding the positions table as tabs
   does not reach the Trades workspace.
6. **Row actions are already backed.** `closeTrade`, `cancelTrade`,
   `deleteTrade`, `setTradeNote` all exist in `api-client.ts:121-149`.
7. **Portfolio history is 30 daily points, not intraday.** `equity_30d` on the
   dashboard payload. The mockup's 09:00–17:00 curve has no backing series.

## Decisions

**D1 — Nav keeps the real routes and the real grouping.** The same eight
entries under the same MONITOR / REVIEW / SYSTEM headers, restyled only. No
invented destinations. The `ui`/`bot`/updated version block stays exactly
where it is at the foot of the rail, including its rail-collapsed behaviour.

The mockup's Settings entry is not added: there is no `/settings` route, and
configuration lives under `/system`. Adding a nav entry to match a picture
would either dead-end or silently rename an existing page.

**D2 — The top bar becomes one row.** Wordmark → ticker → status cluster.
`MarketLane` and `NamesLane` move up out of their own strip and into that row,
restyled as inline chips. This is shared chrome on every page, so it is the
single highest-regression-risk change in the plan.

**D3 — Branding stays swingbot.** Not "Bomeo Capital". The existing avatar +
`swingbot` + `paper` mark is restyled, not replaced.

**D4 — The page title moves into the top bar,** driven by route data, with a
per-page descriptive subtitle beneath it. Proposed copy, to be corrected at
review:

| Route | Title | Subtitle |
|---|---|---|
| `/dashboard` | Dashboard | What's happening right now |
| `/watchlist` | Watchlist | The symbols being scanned |
| `/risk` | Risk | Exposure, caps and the killswitch |
| `/trades` | Trades | Every plan, filled or not |
| `/calendar` | Calendar | P&L by day |
| `/analytics` | Analytics | What already happened, measured |
| `/system` | System | What the bot itself is doing |
| `/versions` | Versions | What's deployed, and when it changed |

Each workspace's own `sb-section-head heading="…"` comes out as its title
moves up. Where a workspace uses that component for projected actions as well
as a heading, the actions stay and the heading attribute goes.

**D5 — A live clock and date join the status cluster,** alongside both the
market-open pill and the connection-status indicator, matching the mockup's
literal layout. `CLOCK` (`ui/clock.ts`) is already injectable, so this needs a
ticking source, not a new dependency. The clock must not tick change detection
for the whole app every second — it renders through a signal updated on an
interval owned by the top bar component alone.

**D6 — The text-zoom control moves into the profile menu,** beside sign-out.
It stays a single cycling control (`ZOOM_CHOICES`), and its preference
persistence through `PreferencesStore` is unchanged. This keeps the top bar as
sparse as the mockup while losing no accessibility capability.

**D7 — No search box, no notification bell.** Both are real features with
their own design questions (what does search search; what is a notification,
when is it read, where is it persisted) and neither has a backend. A
non-functional placeholder for either is a lie in the chrome of every page.

**D8 — Portfolio Value is simplified to figure + change + sparkline.** Balance,
day change, and the existing 30-point `equity_30d` sparkline. No range tabs —
`1D/1W/1M/3M/YTD/1Y/ALL` would be seven controls where at most one has data.

**D9 — Trading Performance carries eight metrics,** the eighth being a **payoff
ratio**, not an average realised R:

Open P&L % · Win Rate · Expectancy (R) · Avg Confidence · Realised P&L · Open
Trades · Risk Used (% of cap) · **Payoff ratio**

Payoff ratio is `mean R of winners ÷ |mean R of losers|`. With Win Rate
already on the panel, win rate and payoff ratio *decompose* expectancy, so the
three read as a coherent triple. Avg realised R was rejected under Finding 2.
`profit_factor` (metrics.py:234) is a neighbour but not the same figure — it is
gross currency, not mean-R — so this is a new function, not a rename.

The small risk dial and the Risk per trade / Current risk / Remaining risk
breakdown the mockup embeds in this panel are **not** built: that is the Risk
& Exposure content that was cut, and duplicating it inside another panel would
reintroduce it by the back door.

**D10 — The Today / All-days scope control moves into the Trading Performance
panel header,** as the mockup shows, and keeps its current page-wide
behaviour: it scopes Realised P&L, the realised win/loss count, and which
closed trades the Closed tab shows. This was chosen with the caveat stated —
a control inside one panel also re-scopes the table below it. Recorded here so
the next reader knows it is deliberate, not an oversight.

**D11 — The positions section becomes one tabbed table.** Five tabs —
Open Positions / Pending / Partial / Closed / Cancelled — replacing today's
four stacked panels. Counts on the tab labels come from the lifecycle counts
already on the dashboard payload.

Only the selected tab fetches. Today all four groups fetch simultaneously on
every dashboard visit; lazy per-tab fetching is strictly less work, and is the
one place this redesign makes the page cheaper rather than more expensive.
Cancelled is new — it exists today only as a count — and needs its own column
set: a plan that never filled has no entry fill, no P&L and no R, so the
columns that matter are why it ended and when.

**D12 — The table keeps all its machinery.** Column picker, compact/full
density, drag-to-reorder, and per-table saved preferences all carry over into
the tabbed rebuild. No capability regression; `dashboard.helpers.ts`'s
`deriveOpenVisible` / `deriveClosedVisible` / `reconcileReorder` logic survives,
now selecting per active tab rather than per rendered group.

**D13 — Row actions and one bulk action.** The row `…` menu offers Close
position, Cancel plan, Add/edit note, and Delete trade. Delete is destructive
and gets a confirm dialog naming the trade (`ui/confirm-dialog.ts` exists).

The mockup's "+ New Trade" is replaced by **Close all open/partial** — closing
every ACTIVE and PARTIAL position at its current price, realising profit or
loss. PENDING plans are excluded: one that never filled cannot be closed, and
cancelling it is a different act with a different meaning.

This needs a **new backend endpoint** (D16). It must not reuse
`/trades/clear-open`, which deletes (Finding 3). The button gets a confirm
dialog that states how many positions will be closed and is unambiguous that
this realises P&L rather than discarding records — the two actions are one
word apart in English and opposite in effect.

**D14 — No panel overflow menu.** The existing destructive bulk operations
(clear open trades, clear trade history — both deletes) stay where they are.
Putting a delete-the-book action one click from a close-the-book action is how
the wrong one gets pressed.

**D15 — Recent Activity is derived, not logged.** Position opened, position
closed, and plan cancelled, from timestamps already on the trade rows. TP1-hit
events are included **only if** a partial-exit timestamp actually exists on the
row; if implementation finds none, they are dropped rather than dated by
inference. No "system scan found N opportunities", no "price alert", no
"strategy updated" — there is no backend event log and price alerts are not a
concept this bot has.

**D16 — Two backend additions.**
- A payoff-ratio field on the `/api/v1/dashboard` payload, computed by a new
  function in `core/analytics/metrics.py` beside `expectancy_r`.
- `POST /api/v1/trades/close-open` in `admin/api_v1/trade_commands.py`, closing
  every ACTIVE/PARTIAL position at current price and returning a summary
  (count closed, total realised). Server-side iteration, one request, one
  report — a client-side loop over N single-close calls leaves the book half
  closed when a connection drops, with nothing that says which half.

**D17 — The bottom row is Recent Activity + Market Movers + Watchlist.**
Watchlist (symbol / price / 1D %) is directly backed by tape data already
fetched. Market Movers' Top Gainers and Top Losers are derivable by sorting
that same data. **Most Active needs volume**; if the tape payload does not
carry it, that sub-tab is dropped rather than filled with a proxy. This is the
one open data question in the spec and it is answered by reading
`tape.store.ts`'s payload during implementation, not by guessing now.

**D18 — Explanatory copy moves behind affordances, and none of it is lost.**
The "What appears here" qualifying-trades explainer, the share-count snapshot
note, the position-premium / sizing explanation, and the closing footnote all
move behind info affordances on the panels they explain. The plan-lifecycle
guide stays the drawer it already is. Earlier specs put that copy there
deliberately; the mockup simply has no room for it on the page face.

**D19 — All seven other workspaces get a restyle pass** in this plan, so no
release ever ships new chrome around old panels.

**D20 — chrome-devtools MCP is fixed first.** It and playwright both timed out
at 30s this session. Visual verification is the point of a visual redesign, so
diagnosing chrome-devtools is the plan's first task, before any redesign work.

**D21 — One plan, several part files, one release.** The work is well past a
single plan file's 1500-line cap, so it splits across `_1`/`_2`/`_3`… parts
under one v85 number, merged and released once when the whole thing is
coherent. No release ever ships the mismatch window between new chrome and
old panels.

## Out of scope

Search / command palette · notification centre · Risk & Exposure panel ·
Account Info panel · intraday equity series · mockup-specific mobile screens
(existing rail/overlay responsive behaviour carries over) · the mockup's Light
and Luxury theme variants · the alternate "Analytics Focus" and "Trades Focus"
desktop layouts · any change to how the bot trades.

## Responsive behaviour

The merged top-bar row is the hard part. At narrow widths, in order: the
subtitle drops, the clock drops, the ticker becomes horizontally scrollable
(it is already a strip and already scrolls), the title truncates. The existing
`ViewportService` breakpoints (`isNarrow`, `isPhone`) and the rail/overlay
sidebar behaviour are reused unchanged — no new breakpoint vocabulary.

The killswitch banner stays shell-level and unmissable: when engaged it renders
as a full-width alert strip directly beneath the top bar rather than competing
for space inside it.

## Loading, empty and error states

Unchanged in kind — `sb-async` already owns loading skeletons, measured-zero
empty states, staleness badges and retry across this workspace, and every new
panel adopts it rather than inventing a second vocabulary. Specifically:

- Each panel is independently async. A failed Market Movers fetch must not
  blank Trading Performance.
- "Measured zero" stays distinct from "no data yet" everywhere, including the
  new payoff ratio (null, never 0.0, when there are no losers to divide by —
  the same rule `profit_factor` already follows).
- A refetch failure keeps the previous figures on screen with a staleness
  marker, per `DashboardStore`'s existing contract.

## Testing

- **Frontend units:** shell (title/subtitle from route data, merged ticker row,
  clock, zoom relocation), the tabbed positions table (tab switching, lazy
  fetch per tab, column/density/reorder preferences surviving a tab change),
  each new panel component, and the Recent Activity derivation.
- **Backend units:** payoff ratio — winners only, losers only, mixed, no
  losers (null, not infinity), no closed trades (null); and the bulk-close
  endpoint — ACTIVE and PARTIAL closed, PENDING untouched, summary counts
  correct, empty book a no-op.
- **Visual:** chrome-devtools screenshots at each phase checkpoint, every
  workspace, at desktop and phone width (D20).
- **Suite:** `python scripts/dev/testrun.py fast` while iterating; one full
  `testrun.py full` as the plan's own final verification task.

## Parallelisation

- **Sequential, first:** the MCP fix (D20) — nothing else depends on it in
  code, but visual verification of everything after it does.
- **Sequential, second:** token additions (`tokens.css`, the hero type size and
  any new spacing rungs). One file, and every later task consumes it.
- **Sequential, third:** the shell itself (`shell.{ts,html,css}`, the tape
  lanes, `app.routes.ts` route-title data). The title/subtitle mechanism is a
  contract the workspace tasks consume.
- **Group A (parallel):** the two backend additions — payoff ratio
  (`core/analytics/metrics.py` + the dashboard endpoint) and bulk close
  (`admin/api_v1/trade_commands.py` + `core/tracking/performance.py`). Disjoint
  files, no shared symbol.
- **Group B (parallel), after the shell and after Group A:** the new Dashboard
  panel components — Portfolio Value, Trading Performance, Recent Activity,
  Market Movers, Watchlist. One new file each. Trading Performance consumes the
  payoff-ratio field, which is why Group A precedes it.
- **Sequential, after Group B:** Dashboard page assembly (`dashboard.ts`) —
  every Group B task would otherwise edit this one file.
- **Sequential:** the tabbed positions table (`trade-group.ts` →
  its replacement, `dashboard.helpers.ts`, `trades.columns.ts`), then its row
  actions and the close-all button, which consume both the table and the
  bulk-close endpoint.
- **Group C (parallel), last:** the seven other workspace restyles — one
  workspace file each, no shared file between them.
- **Sequential, final:** full-suite verification, alone.

Concurrent sessions share this working tree, so Group B and Group C are the
only places more than one agent may work at once, and only within a group.

## Risks

1. **The merged top bar is on every page.** The most likely regression source
   in the plan, and the reason Group C's restyle pass exists rather than being
   deferred.
2. **The tabbed table is a rewrite of working code** that carries preference
   reconciliation logic with real subtlety in it (`reconcileReorder`). Its
   existing specs are the safety net; they get ported, not dropped.
3. **Close all open/partial is irreversible and adjacent, in meaning, to a
   delete-everything action that already exists.** D13's confirm copy is not
   decoration.
4. **Most Active may have no backing data** (D17) — resolved by reading, and
   dropped if absent.
5. **The clock is a per-second signal in shared chrome.** Done carelessly it
   re-renders the app every second.
