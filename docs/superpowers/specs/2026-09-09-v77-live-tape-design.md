# v77 — The live tape: a two-lane ticker for the admin shell

**Version:** ui 1.12.0 · bot 1.6.2
**Bump:** ui minor · bot patch — `ui minor` because this hands the operator a
new permanent surface on every route, which is an observable difference in the
product rather than a large diff; `bot patch` because the scan's only change is
to publish a per-ticker last bar it already holds, and no alert, chart, plan or
sizing decision moves. Numbers are resolved at close-out from the then-current
`VERSION.json`, never predicted here. The `Version:` line is a historical stamp,
not a target.
**Edge:** none (integrity) — and labelled honestly. This buys **no** edge. It
does not change what the bot scans, plans, sizes or fills, and it will not move
pooled `ExpR` or win rate by a basis point. It is operator visibility, and it
competes for the same budget as work that would move those numbers. Calling it
`harvest` because it puts distance-to-entry in front of a human who could
theoretically act on it would be the borrowed-language failure
`document-conventions.md` warns against: the bot is automated, and the human
watching a tape is not a fill.

**On the number.** The counter's maximum was `v74` when this was written, but
`v75` and `v76` are not free: v74's own spec names them in nine places as its
committed roadmap (fold-train windows, the max-statistic permutation, the `DEAD`
verdict). Taking `v75` here would have meant rewriting a live spec's meaning to
make room for an unrelated feature. Numbers only ever increment and are never
reused; nothing requires taking the immediate next one, so this document takes
`v77` and leaves the gap for the documents v74 already named.

---

## What prompted this

The reference the request pointed at is <https://investing.tavrion.de/>. Read
with a browser rather than a fetch, its sliding bar turns out to be **a
TradingView `ticker-tape` embed**, not bespoke code — a 44px iframe under the
header carrying:

```
S&P 500 · Nasdaq 100 · Dow Jones · DAX 40 · FTSE 100 · Nikkei 225 · BTC · ETH · SOL · XRP
colorTheme: light · isTransparent: true · displayMode: "adaptive" · showSymbolLogo: true
```

Two things follow. First, it is a fixed *market pulse* strip and has nothing to
do with any watchlist, so "the same thing, but my stocks" is not a
configuration change to what that site does. Second, **the iframe is opaque** —
cross-origin, no API — so its prices can never be read out and decorated with
swingbot context. Any tile carrying both a live price and a setup badge has to
be ours end to end.

That constraint is what produced the two-lane design below rather than one
enriched tape.

## The shape

Two lanes inside `.main`, between `.topbar` and `.workspace`:

```
┌─ sidebar ─┬─ .topbar        KILLSWITCH · MARKET OPEN · ◍ · profile ─┐
│  swingbot │─ Lane A  mkt   S&P 500 +0.42%  NDX +0.71%  … │ live     │
│  Dashboard│─ Lane B  mine  NVDA 182.40 +2.1% ●2w 0.8%→entry … │ ◷14:35│
│  Watchlist│─ .workspace  router-outlet                              │
└───────────┴──────────────────────────────────────────────────────────┘
```

The sidebar keeps its full height. A full-bleed bar above the whole shell was
considered and rejected: it decapitates the rail, so the shell stops reading as
"rail + app", and it requires the 2-column grid to be rewritten as a row above a
grid. Tucking a single lane into the topbar's existing dead space was also
rejected — it is free vertically, but it puts three independently-moving things
(tape, MARKET OPEN, connection dot) in one 32px strip.

**Lane A — the market.** The TradingView `ticker-tape` embed, fixed indices
(SPX / NDX / DJI / VIX). Real-time, zero maintenance, no swingbot involvement,
and it earns the iframe precisely because nothing about it is ours. End-cap
reads `live`.

**Lane B — my names.** Our component, our design system. Dense one-line tiles:

```
SYM · price · %chg · context
```

where context is exactly one thing, resolved in this precedence:

1. `◆ +1.4R` — an open position. Unrealised R from the trade's `entry` and
   `stop_loss` against the tape's price. A position outranks a plan: it is
   money already committed.
2. `● <horizon> <n>% → entry` — an active plan and no open position.
3. `earnings 3d` — neither of the above, and the ticker reports within the
   current Monday–Sunday week. This is the **same boundary** the watchlist
   table's existing row-pulse uses, so the two never disagree about what
   "this week" means.
4. Nothing. A stacked two-line variant was
rejected for costing ~12px of workspace on every route to say what fits on one
line; a context-only variant that dropped the price was rejected because a tape
without a price stops reading as a tape, and loses the thing that makes
glancing at it habitual.

## The feed: no new price source

The scan loop already fetches OHLCV for **every** watchlist ticker every
`SCAN_INTERVAL_MINUTES` (default 5). The last bar is therefore already in hand
on every pass and is simply not surfaced. Lane B is fed by emitting it on the
**existing** `scan` SSE topic (`swingbot/admin/events/stream.py`,
`frontend/src/app/api/event-stream.ts`).

This was chosen over a dedicated ~60s quote poller and over a real-time paid
feed. The poller buys ~5 minutes of freshness in exchange for a new failure
mode, a new rate-limit surface, and a second price path that can disagree with
the scan's — two numbers for the same ticker on the same screen is a
correctness bug, not a freshness improvement. The paid feed buys real time in
exchange for a secret, a dependency and a bill, for a strip that answers a
question the operator is not trading on.

**The cost is latency, and it must be shown, not hidden.** Up to ~20 minutes:
5 minutes of scan interval plus yfinance's ~15-minute delay. Lane B therefore
carries a **pinned** `◷ 14:35` as-of badge in a fixed end-cap outside the
moving track. This is not cosmetic: a badge that rides the tape scrolls away,
so the freshness signal would blink in and out and be absent exactly when
someone glances. A screen that hides how stale its data is has a correctness
bug.

Lane A and Lane B are never merged into one strip, at any width, for the same
reason — the lanes have different latencies, and one as-of badge cannot sit
honestly over two different truths.

## The flag

Per-ticker opt-in, stored as a key in the **existing** `ui_preferences` doc:

```json
{ "shell.sidebar": "rail",
  "tape.symbols": ["NVDA", "AMD", "ASML"] }
```

`data/watchlist.json` is **untouched**. It is a flat `list[str]` consumed at
~12 call sites across `commands/backtest.py`, `commands/data.py`,
`commands/scanning/loops.py`, `commands/scanning/commands.py`,
`commands/watchlist.py` and `admin/api_v1/watchlist.py`, every one of which
treats it as strings — `len()`, `set()`, iteration, fetcher input. Widening it
to `list[dict]` is the semantically correct home for the flag and was rejected
anyway: the ripple is large and it collides head-on with v67 phase 2
(`P2-21`/`P2-22`), which is mid-migration on that exact module. A separate
`data/tape_symbols.json` was rejected for requiring a **new** v67 task, since
v67 enumerates every data path.

`ui_preferences` is already covered by v67 at `P3-01` (`p3_003` migration,
`ui_preferences` table, one JSON doc per `owner`) — a different and later phase
than the watchlist one. A list value fits that shape.

**The scan emits all watchlist tickers; Lane B filters client-side.** ~90
tickers × a few fields per 5 minutes is a few KB, and it keeps the backend
ignorant of a pure display concern while making a toggle take effect
immediately rather than at the next scan.

**Empty behaviour is opt-in with no fallback:** nothing flagged means Lane B
does not render at all. Lane A is unaffected.

## The toggle, and the Remove button

A new **leading, sortable `Tape` column** in the watchlist table — `◉` flagged,
`○` not. With ~90 tickers and a handful flagged, the common act is *auditing*
the flag set rather than changing it, and only a persistent column makes that a
glance; one header click then groups the flagged names. `data-table.ts:758`
already exempts `button, a, input, select, textarea, label` from row
activation, so an in-row control needs no `stopPropagation` handling.

**The Remove button becomes a red trash icon.** This needs two additions:

- `icon.ts` gains a `trash` name. It currently has thirteen — `dashboard`,
  `trades`, `analytics`, `calendar`, `watchlist`, `risk`, `system`, `versions`,
  `collapse`, `expand`, `profile`, `signout`, `menu` — and no destructive one.
- `button.ts` gains a ninth variant, `danger-icon`. The variants are mutually
  exclusive today (`classes = computed(() => this.variant())` emits exactly one
  class): `icon` paints `--text-muted`, `danger` paints `--neg`, and there is no
  way to have both. Making `variant` compose with a tone was rejected for
  legalising pairs nobody has designed (`chip`+`danger`, `segment`+`link`) and
  weakening the "inventory names, and no others" guarantee. A call-site CSS
  override was rejected as the exact pattern the `chip` variant's own comment
  records regretting.

The button carries `aria-label="Remove <SYM>"` — an icon-only destructive
control with no accessible name is not shippable — and **still routes through
the existing `ConfirmDialog`**. `button.ts` documents `danger` as the variant
every irreversible action uses precisely because it pairs with that dialog;
only the paint changes here, never the gate.

## Motion

Continuous slide, so every flagged name is shown regardless of how many are
flagged or how narrow the viewport is. Seamless loop: the track is rendered
twice and translated `-50%`, so there is no visible snap-back. Pause on hover,
which is also what makes a tile clickable. Full stop under
`prefers-reduced-motion` — the shell already honours that flag for the sidebar
transition.

**Tick colouring reuses existing code.** `frontend/src/app/ui/flash.ts` is a
directive that flashes an element when its value *actually changed* — never on
first render, never when a re-render reports the same value — coloured
`--pos-soft` / `--neg-soft`, with `prefers-reduced-motion` already zeroed
globally. Lane B tiles take `[sbFlash]="pctChange"` and inherit all of it. No
new animation code, and no risk of the permanent flicker its own comment warns
about. The flash washes the **whole tile**, not the digits: on a strip that is
already moving, a recoloured number is invisible.

Because the feed lands once per scan, flashes are periodic (~5 min), not
continuous. This is expected behaviour and should not be read as a stall.

## Mobile

Both lanes survive at phone width, compressed to 28px each (~56px total). Below
`sm` the shell's sidebar is already an overlay and the grid collapses to `1fr`,
so the lanes span the full viewport.

This is a deliberate cost: 56px of a ~700px viewport is ~8% of the screen spent
permanently, and two strips sliding at different rates on a small screen is
visually busy. Dropping Lane A below `sm` was offered and declined — the
layered read is wanted on every device, not only where it is cheap.

## Decisions taken without a question

1. **Ordering** — open positions first, then tickers with an active plan by
   distance-to-entry ascending, then the remainder alphabetically. Deterministic,
   so the tape does not reshuffle jarringly on each scan.
2. **Market closed** — the tape keeps sliding. A frozen tape reads as broken,
   and the truth is already carried twice: the topbar's existing SR58
   MARKET OPEN/CLOSED indicator and Lane B's as-of badge.
3. **Tile click** — navigates to `/watchlist/:symbol`, the same destination the
   table's `RowLink` already uses. Hover-pause makes it hittable.
4. **Flagged but no scan data yet** — renders the symbol with a dim placeholder
   rather than omitting the tile. A flagged name silently vanishing is the
   failure mode to avoid; an obviously-empty one is self-explaining.

## Seams this reuses rather than rebuilds

| Need | Existing |
|---|---|
| Push transport | `admin/events/stream.py` + `api/event-stream.ts`, `scan` topic |
| Tick colouring | `ui/flash.ts` (`sbFlash`) |
| Market-hours truth | `connection.marketActive()` (SR58, already in `.topbar`) |
| In-row controls | `data-table.ts:758` button exemption |
| Destructive gate | `sb-confirm-dialog` via `ask(row)` |
| Flag persistence | `ui_preferences` doc + `PreferencesStore` |
| Reduced motion | already global in `tokens.css` |

## Coordination with v67

v67 (JSON → Postgres) runs long and in parallel. This spec deliberately keeps
its write inside `ui_preferences`, which v67 migrates at `P3-01` in phase 3, and
keeps `watchlist.json` untouched, which v67 migrates at `P2-21`/`P2-22` in
phase 2.

**The implementation plan must still add `tape.symbols` to v67's `P3-01`
task**, so the migration carries the key across rather than dropping it. A
parallel plan that touches a `data/` JSON file and does not update v67's
matching task is how the key gets silently lost at cutover.

## What this does not do

- Does not change what the bot scans, plans, sizes, fills or alerts on.
- Does not add a price source, a secret, or a paid dependency.
- Does not place, modify or close any trade — paper or otherwise.
- Does not make Lane A configurable. Its symbols are fixed indices; the
  watchlist flag drives Lane B only.
- Does not backfill history. The tape shows the latest scan, not a session
  series.

## Risks

- **The as-of badge is load-bearing.** If it is ever allowed into the moving
  track — by a later refactor that simplifies the end-cap away — the tape
  silently becomes a screen that hides its own staleness. Worth a test that
  asserts the badge is outside the animated element.
- **~56px on every route, forever.** The cost is paid on screens where the tape
  is irrelevant. If it grates, the escape is a shell-level hide toggle, not a
  per-route rule.
- **TradingView is a third party in the shell.** Lane A can break, restyle
  itself, or start asking for consent without notice. It must fail to *absent*,
  never to a broken box, and Lane B must not depend on it having loaded.

## Verification

Per `document-conventions.md`, the plan built from this spec runs the full
suite **once**, as its own final task. Per-component work is verified with
`python scripts/dev/testrun.py file <test>`; the fast tier auto-escalates
because template files are touched.
