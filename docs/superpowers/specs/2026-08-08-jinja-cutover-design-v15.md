# Cutover and Jinja removal

**Date:** 2026-08-08
**Version:** ui 1.0.9 · bot 1.1.2
**Status:** design agreed, not implemented
**Scope:** design only — the switch, the acceptance gate, and what gets deleted

## Why this exists

The admin UI is being rebuilt as an Angular SPA. That migration is too large for
one spec, so it is split into six sub-projects:

| # | Sub-project | Status |
|---|---|---|
| 1 | REST API for the whole admin surface | agreed (`2026-08-08-admin-rest-api-design-v11.md`) |
| 2 | Real-time event push (bot → admin) | agreed (`2026-08-08-realtime-push-design-v12.md`) |
| 3 | Design system | agreed (`2026-08-08-admin-design-system-design.md`) |
| 4 | Angular shell + build/deploy/auth | agreed (`2026-08-08-angular-shell-design-v13.md`) |
| 5 | The workspace implementations | agreed (`2026-08-08-angular-workspaces-design-v14.md`) |
| 6 | **Cutover, delete Jinja** | **this document** |

This is the last sub-project. It changes almost no behaviour — it flips which UI
is served, then removes the one that lost.

## The problem being solved

Sub-projects 1–5 deliberately build **beside** the running UI rather than
inside it. That is what makes them safe to do incrementally, and it is also what
leaves the repo, at the end of sub-project 5, carrying two complete admin UIs:

- ~48 HTML routes across `app.py` and `pages.py`, plus 10 legacy `/api/*` routes
- 20 Jinja templates
- `dashboard.js`, `chart-init.js`, `style.css`, `tokens.css`
- vendored `lightweight-charts` 4.2.3, alongside npm's 5.x in the SPA
- a `tests/admin/` suite that asserts against rendered HTML

Leaving both is not neutral. Two UIs means every future change has two places to
make it, and the dead one silently rots until someone trusts it by mistake.

**The risk this spec exists to manage:** the cutover is the first moment the
SPA is the only UI. If something was missed across eleven pages of accumulated
behaviour, this is when it is discovered — potentially with the old UI already
deleted.

## Decision 1 — Flag first, delete second, in two releases

The switch and the deletion are **separate releases**, with real time between
them.

**Release A — the flip.** An env flag, `ADMIN_UI=spa|jinja`, defaulting to
`spa`. Flask serves the SPA at `/` and keeps every Jinja route mounted and
reachable. Rollback is `ADMIN_UI=jinja` plus a container restart — under a
minute, no rebuild, no git operation.

**Release B — the deletion.** After the SPA has been the only UI actually used
for **at least two weeks of live trading sessions**, the flag, the routes, the
templates and the old assets are removed in one commit.

Two weeks is chosen against the domain, not by feel: this bot's slower horizons
mean some behaviour — a trade reaching TP2, a weekly analytics rollover, a
tuning proposal cycle — simply does not occur in a few days. A cutover validated
over one afternoon validates the daily paths and nothing else.

**Rejected — flag-free straight replacement.** Fastest, and the rollback is
`git revert` plus a rebuild plus a redeploy, at the exact moment you have
discovered something is broken and are least inclined to do it carefully.

**Rejected — running both indefinitely behind the flag.** That is not a cutover,
it is a permanent second UI, which is the thing this sub-project exists to
prevent. Release B is what makes A a migration rather than a fork.

**The flag is deliberately crude.** No per-route switching, no gradual rollout.
One user, one instance: a partial cutover would only create states nobody tests.

## Decision 2 — The acceptance gate

Release A does not ship until every item passes. This list is the deliverable of
this sub-project as much as the deletion is.

### 2a. Route coverage, re-derived

**Do not trust sub-project 1's mapping table.** Re-derive it:

```bash
grep -rn "\.route(" swingbot/admin/*.py
```

Every route must be classifiable as *replaced by* (named v1 endpoint + named
workspace), *deliberately dropped* (with the reason), or **unmapped — which
blocks the cutover.** Routes added after 2026-08-08 will not be in that table,
and they are exactly the ones most likely to be forgotten.

That re-derivation was done at the end of Phase 4 and is recorded in
**Appendix A** at the end of this document, along with the colour, table and
1280px reviews. It found nothing unmapped and two mapped routes with no SPA
control — see A2, which is the part of this gate still open.

### 2b. Behaviour parity, walked

Every Jinja page opened, every control exercised, against the SPA. Not a code
comparison — a walk-through. The current UI has behaviour nobody wrote down.

Particular attention, because these are the ones that silently differ:

- **Settings** — preview diff, save, export, import, secret masking (`•••`),
  the audit trail entry. Verify a *round trip*: export, edit, import, confirm the
  bot reads it after SIGHUP.
- **Bot restart** without the Docker socket mounted — must report unavailable,
  not fail.
- **Destructive actions** — clear open trades, clear history, delete a trade.
  Confirm they destroy exactly what the old UI destroyed.
- **Scan control** — trigger, stop, pause, resume, and the flag files each
  leaves behind. The bot reads those files; a wrong flag name is invisible in
  the UI and breaks scanning.
- **Trade close** with a manual price, including the `manual_close_notify.json`
  path that tells the bot to announce it.
- **CSV export** — same columns, same ordering.

### 2c. Degraded-mode correctness

With `/api/v1/events` blocked, every workspace still correct. Sub-project 2
requires this and sub-project 5 tests it; it is re-checked here because the
cutover is when it stops being a nice property and starts being the thing
between you and a UI that lies.

### 2d. Suite green

`python scripts/testrun.py full` — `0 failed`, with the one quarantined
`xfail` behaving as documented in `CLAUDE.md`.

## Decision 3 — What is deleted, and what survives

### Deleted in Release B

- All 20 templates in `swingbot/admin/templates/`
- The HTML-rendering routes in `app.py` and `pages.py`, and the `pages` blueprint
- The 10 legacy `/api/*` routes and `swingbot/admin/api.py`
- `static/dashboard.js`, `static/chart-init.js`, `static/style.css`
- `static/vendor/lightweight-charts/` (4.2.3) — the SPA uses npm 5.x
- The `ADMIN_UI` flag itself

### Surviving, and why

**`static/tokens.css` survives, holding sub-project 3's tokens.** It stops being
read by Jinja and becomes the source the Angular build imports. This matters
because of the next item.

**`swingbot/admin/chart_style.THEME` survives, and so does the test that keeps
it in sync with `tokens.css`.** The theme feeds **server-rendered PNG charts,
which the Discord bot posts in its alerts** — that is a bot feature, not an
admin one, and it does not care that the admin UI changed. Deleting the tokens
file would break the sync test and leave the bot's chart colours with no
single source.

Consequence: **`tokens.css` must be updated to spec 3's palette during
sub-project 5, not at cutover**, because changing it changes the colours of
charts the bot posts to Discord. That is a user-visible change to a surface
outside this migration, and it should land deliberately and be looked at, rather
than arriving as a side effect of a deletion commit.

**Inter stays vendored**; JetBrains Mono joins it (sub-project 4).

### The PNG chart routes — decided

`GET /trades/<id>/chart.png` and `GET /plans/<id>/chart.png` are **deleted**.

The chart *generation* code stays — the bot needs it. Only these two admin HTTP
wrappers go. Every chart in the SPA is `lightweight-charts`, so nothing requests
them; they exist solely to serve `<img>` tags in templates that are also being
deleted.

**Verify before deleting** that no bot code path reaches those charts through
the admin's HTTP layer rather than the shared module. Two containers, one
codebase — this is the kind of coupling that is easy to assume away.

## Decision 4 — Tests

`tests/admin/` has 12 files today, most asserting against rendered HTML —
`test_dashboard_v2.py`, `test_pages.py`, `test_trade_detail_layout.py`,
`test_settings_v2.py`, `test_risk_panel.py` and others. Deleting the templates
deletes what they assert on. `tests/test_admin_pages.py` is in the same position.

**They are not deleted wholesale, and they are not ported wholesale.** Each is
triaged:

- **Asserts on HTML structure** (a table has these columns, this template
  renders this block) → delete. It tests a UI that no longer exists.
- **Asserts on behaviour reachable through v1** (this action closes that trade;
  this filter excludes those rows) → rewrite against the v1 endpoint. The
  assertion is about the domain and is worth keeping.
- **Asserts on a builder or query function** (`test_dashboard_builders.py`,
  `test_trade_history_paging.py`) → **keep unchanged.** These target
  `dashboard.py` and `_query_closed_trades()`, which the v1 API also uses. They
  were extracted from templates precisely so they would survive this.

**Do this triage during sub-projects 1 and 5, not at cutover.** A v1 endpoint
should arrive with its behavioural test already rewritten. Arriving at Release B
with 12 files of unexplained failures is how coverage gets deleted rather than
migrated, under time pressure, at the least reversible moment.

The pass count in `CLAUDE.md`'s baseline will drop when the HTML-structure tests
go. That is expected and correct — record the new baseline in the same commit,
because an unexplained drop is indistinguishable from lost coverage later.

## Decision 5 — Versioning and documentation

**Release A: `ui` minor bump — `1.0.9` → `1.1.0`.** A different UI is a minor
change, not a patch.

**Release B: `ui` patch bump**, since deletion is invisible to a user. `bot` is
untouched by both — the bot process does not change in this migration at all.

Documentation updated in Release B, in the same commit as the deletion:

- **`README.md`'s "Admin UI" section** describes vendored Inter, self-hosted
  `lightweight-charts` 4.2.3, and the `/api/ohlcv` surface. All three change.
- **`CLAUDE.md`** — the admin is no longer "Flask admin UI" alone; the
  `frontend/` directory, the npm build, and the two-namespace period ending all
  belong there. So does the new test baseline.
- **`docs/claude/architecture.md`** — the core/commands/admin split gains a
  frontend.
- **`DOCKER.md` / `DEPLOY_HETZNER.md`** — the multi-stage build, and the fact
  that a deploy now needs a Node build stage.
- **`docs/claude/known-traps.md`** — retire the traps that were about Jinja
  fragments; add whatever this migration taught.

## Definition of done

1. `ADMIN_UI=spa` is the default and the SPA is the only UI in use.
2. Two weeks of live sessions elapsed with no rollback.
3. Every item in Decision 2 passed and recorded.
4. Everything in Decision 3's delete list is gone; everything in the survive list
   remains, with the tokens sync test still green.
5. `python scripts/testrun.py full` green, with a new recorded baseline.
6. Docs in Decision 5 updated.
7. `grep -rn "\.route(" swingbot/admin/*.py` returns only `/api/v1/*` and the
   SPA-serving routes.

## Explicitly out of scope

- Any new feature. **This sub-project adds nothing.** The temptation to fix
  "one small thing" while deleting is how a low-risk cutover becomes a
  high-risk one.
- Replacing the Werkzeug dev server. Still worth doing, still not here.
- Merging `plans.json` and `trades.json` — sub-project 1 unified them at the API
  layer specifically so this data migration would never be on this critical path.
- Removing the `/api/v1/` prefix now that nothing competes with it. Churn for no
  benefit.

## Risks

**Something was missed, and it is found after Release B.** The two-week window
and the flag are the mitigation; the residual risk is a rarely-used path that
does not occur even in two weeks. Accepted — this is a personal paper-trading
tool, and the recovery is git history.

**The two-week wait will feel unnecessary** by day three, when everything works.
It is protecting against exactly the behaviour that has not happened yet. Write
the date down at Release A.

**Deleting tests is indistinguishable from losing coverage** to anyone reading
the diff later. The triage in Decision 4, done early and commit-by-commit, is
what makes it legible. A single commit deleting twelve test files is not.

**`tokens.css` reaches further than the admin UI** — through `chart_style.THEME`
into charts the bot posts to Discord. The palette change is a user-visible
change to the bot's output. It belongs in sub-project 5, seen and approved, not
discovered here.

**Rollback stops being free at Release B.** That is the point of the two
releases, and it is worth being explicit that the second one is the irreversible
one — the first is not.

## Open questions

None blocking.

1. Whether `ADMIN_UI` should default to `jinja` for the first deploy of Release
   A, requiring an explicit opt-in. Safer; also means the cutover can silently
   not happen. Lean `spa` — the flag's value is the rollback, not the opt-in.
2. Whether `tests/admin/` is worth restructuring at Release B, once it is
   entirely API-level. Probably; decide when the triage shows what survives.

---

# Appendix A — the NG52 parity audit

Recorded 2026-08-13, at the end of Phase 4. This is the mapping Decision 2a
asks for, re-derived from `grep -rn "\.route(" swingbot/admin/*.py` rather than
copied from sub-project 1, plus the three reviews the plan's NG52 names.

**It is not the acceptance gate.** 2b (a walk-through of every control against a
running pair of UIs) and 2c (degraded mode) are still owed, and so is the
browser half of the 1280px check below. What this appendix does is remove the
question "is anything unmapped" from that walk-through, and name the two things
that are.

## A1 — Route coverage

Every non-`/api/v1` route in `swingbot/admin/`, classified. `pages.py` routes
are marked *(pages)*, `api.py` — the legacy JSON API the Jinja pages' own
JavaScript calls — *(legacy JSON)*.

### Pages, replaced

| Jinja route | v1 endpoint | Angular successor |
|---|---|---|
| `GET /` (dashboard) | `GET /cockpit`, `GET /trades` | `/cockpit` |
| `GET /dashboard` *(added after this audit, by NG53 — see B1)* | `GET /cockpit`, `GET /trades` | `/cockpit` |
| `GET /dashboard/fragment` | — | none needed: the fragment poll is what the event stream replaces |
| `GET /plans` *(pages)* | `GET /trades?status=planned` | `/trades` with the status chip |
| `GET /plans/fragment` *(pages)* | — | as above; no fragment polling in the SPA |
| `GET /plans/<id>` *(pages)* | `GET /trades/<id>` | `/trades/:id` |
| `GET /trades/<id>` | `GET /trades/<id>` | `/trades/:id` |
| `GET /journal` *(pages)* | `GET /trades?has_note=true` | `/trades`, and the detail's Notes tab |
| `GET /performance` | `GET /analytics/performance` | `/analytics?tab=performance` |
| `GET /strategies` *(pages)* | `GET /analytics/strategies` | `/analytics?tab=strategies` |
| `GET /calibration` *(pages)* | `GET /analytics/calibration` | `/analytics?tab=calibration` |
| `GET /tuning` *(pages)* | `GET /analytics/tuning/proposals`, `GET /jobs` | `/analytics?tab=tuning` |
| `GET /watchlist` | `GET /universe/tickers` | `/universe` |
| `GET /risk` | `GET /risk` | `/risk` |
| `GET /settings` | `GET /system/settings` | `/system?tab=settings` |
| `GET /logs` | `GET /system/logs` | `/system?tab=logs` |
| `GET /login`, `POST /login`, `POST /logout` | `GET/POST/DELETE /session` | the shell's login form |

### Commands, replaced

| Jinja route | v1 endpoint | Where it is in the SPA |
|---|---|---|
| `POST /trades/<id>/close` | `POST /trades/<id>/close` | Trades row action, detail Live tab |
| `POST /trades/<id>/delete` | `DELETE /trades/<id>` | same |
| `POST /plans/<id>/cancel` *(pages)* | `POST /trades/<id>/cancel` | same |
| `POST /plans/<id>/close` *(pages)* | `POST /trades/<id>/close` | same |
| `POST /trades/clear-open` | `POST /trades/clear-open` | **nothing — see A2** |
| `POST /trades/history/clear` | `POST /trades/clear-history` | **nothing — see A2** |
| `GET /trades/export.csv` | `GET /trades/export.csv` | **no control — see A2** |
| `POST /watchlist/add` | `POST /universe/tickers` | Universe add box |
| `POST /watchlist/bulk_add` | `POST /universe/tickers` | the same box: one endpoint absorbs both |
| `POST /watchlist/remove` | `DELETE /universe/tickers/<symbol>` | Universe row action |
| `GET /watchlist/suggest` | `GET /universe/suggest` | Universe add box |
| `POST /risk/killswitch` | `POST /risk/killswitch` | Risk, `ConfirmDialog`-gated |
| `POST /settings/preview` | `POST /system/settings/preview` | System, Settings tab |
| `POST /settings/save` | `PUT /system/settings` | same |
| `GET /settings/export` | `GET /system/settings/export` | same, as a download link |
| `POST /settings/import` | `POST /system/settings/import` | same, paste-to-import |
| `POST /bot/restart` | `POST /system/bot/restart` | System, Scan tab |
| `POST /logs/clear` | `DELETE /system/logs` | System, Logs tab |
| `GET /logs/raw` | `GET /system/logs/raw` | System, Logs tab, "Raw" link |
| `POST /scan/{trigger,stop,pause,resume}` | `POST /system/scan/*` | System, Scan tab |
| `GET /scan/status` | `GET /system/scan` | same |
| `POST /tuning/propose` *(pages)* | `POST /analytics/tuning/proposals` | Analytics, Tuning tab |
| `POST /tuning/proposals/<f>/delete` *(pages)* | `DELETE /analytics/tuning/proposals/<f>` | same |
| `POST /journal/<id>/note` *(legacy JSON)* | `PUT /trades/<id>/note` | detail Notes tab |

### Legacy JSON, replaced

`GET /api/trade-history` maps to `GET /trades`; `GET /api/ohlcv/<ticker>` to
`GET /market/ohlcv/<ticker>`; and `/stats`, `/plans`, `/journal`,
`/calibration`, `/registry`, `/jobs`, `/jobs/<id>`, `/jobs/tune` and `/health`
*(all legacy JSON)* to their `/api/v1` namesakes. These have no UI of their
own; they die with the templates whose JavaScript calls them.

### Deliberately dropped

| Route | Why |
|---|---|
| `GET /trades/<id>/chart.png`, `GET /plans/<id>/chart.png` *(pages)* | Decision 3 already decided this: the SPA draws charts client-side from `/market/ohlcv`. The PNG route survives Release B for Discord only, not for any UI. |
| `GET /dashboard/fragment`, `GET /plans/fragment` *(pages)* | Fragment polling is the thing sub-project 2 replaced. There is nothing to port. |

### Not a Jinja route

`GET /app/<path:filename>` and the six workspace prefixes in `spa.py` serve the
SPA itself.

**Unmapped: none.** Two mapped routes have no SPA control, which is a different
finding and is A2.

## A2 — Gaps that block the cutover — CLOSED 2026-08-13

Both were closed in the commit after this audit, in the Trades workspace:
"Export CSV" is a plain anchor carrying the current query, and "Clear open"
and "Clear history" are `ConfirmDialog`-gated with consequences that name
what goes, what stays, and that the filter on screen does not narrow either
command. The clears report their row count rather than a bare
acknowledgement — "cleared 0" and "cleared 40" are different answers — and a
refused command says so instead of being swallowed the way a row action's
error is.

The finding is left below as written, because how they came to be missing is
the part worth keeping.

**1. `clear-open` and `clear-history` have no SPA control.** Both endpoints
exist (`api_v1/trade_commands.py`), and `ApiClient` has `clearOpenTrades()` and
`clearTradeHistory()` — with no call site anywhere in `frontend/src`. The Jinja
dashboard has both buttons. Either the Trades workspace grows them behind
`ConfirmDialog` (they are the two most destructive actions in the product), or
they are dropped on purpose and this document says so. Right now they are
neither, which is the state Decision 2a calls blocking.

**2. CSV export has no SPA control.** `ApiClient.tradesExportUrl()` exists and
is tested; nothing links to it. Decision 2b lists CSV export as a parity item to
walk, so it needs a link on the Trades workspace — a plain anchor, as the
method's own docstring explains.

Neither is a task in the Phase 4 plan, which is how both were missed: NG42
listed the row actions, and NG52 is the first task that counts what is *not*
there.

## A3 — Colour review

Against spec 3's rules: green and red mean P&L direction only, amber means
caution, blue means interactive and is never applied to data.

**One violation found and fixed.** `ConnectionStatus` painted the live dot
`--pos` and the dead dot `--neg`, so in one strip of chrome green meant both
"this position is in profit" and "the event stream is up", and a fallback to
polling looked like a loss. Live is now `--text` — the pulse is what carries
"live", and it is the one motion spec 3 keeps — while degraded and dead are both
`--warn`, told apart by the label, with dead taking the whole label amber.

**Green now appears in exactly four components, all money:** `MetricCard`,
`MetricChip`, `Sparkline`, and `StatusIndicator`'s settled-win dot and SL→TP
fill — plus the `.pos`/`.neg` pairs the five workspaces apply to P&L columns.

**Red has two sanctioned non-money uses, recorded here rather than left to be
rediscovered:**

- The `danger` button variant, and the killswitch's ENGAGED state which matches
  it. `ui/button.ts` documents why: an irreversible control that does not look
  dangerous is worse than a colour rule kept perfectly.
- Failure text — a save that did not save, a command that did not run, a note
  that is not stored. Amber is wrong for these because amber already means
  "stale but correct", and a failed write is not stale. This is the same
  "something is wrong" red as the danger button rather than a status colour.

**Blue is interactive everywhere it appears:** links, row links, the active nav
and tab indicators, focus rings, the primary button, the sort arrow, the column
picker, the checkbox, and the chart's loading spinner. Two uses are worth naming
because they sit closest to the line — the settings form's edited-field marker
(`.changed`), which is selection state on a control rather than colour on a
value, and the spinner, which is system feedback rather than data. Neither
colours a number.

## A4 — One table, six call sites

`DataTableComponent` is used by Trades, Analytics (the strategy, confidence,
decile and drift tables), the Cockpit's open positions, Risk's exposure,
Universe's watchlist and the ticker detail's trade list. Spec v14's definition
of done says "four call sites"; it is six, because spec 3 added the Cockpit
summary table (NG47) and Decision 9 requires the ticker detail to reuse the same
component (NG51). More reuse of one component is not the failure that clause
guards against.

**No second grid exists.** Two kinds of hand-written `<table>` do: Analytics'
win-rate heatmap (a matrix with a header column, no sorting, no paging, no rows
in the grid sense) and the two three-column diffs — Analytics' tuning proposal
parameters and the System settings preview. A diff is a fixed pair of columns
over a handful of rows; routing it through a component carrying sorting, paging,
a column picker and row expansion would be more machinery, not less. Recorded so
a later reader does not read them as drift.

## A5 — The 1280px check

The layout is committed to 1280px (spec 3). The geometry, computed rather than
eyeballed:

- Viewport 1280, less the 168px sidebar and 2×20px workspace padding, leaves
  **1072px** of content — and less the panel's 2×1px border and the expansion's
  2×14px padding, **1042px** for the expansion grid.
- The expansion is `repeat(auto-fit, minmax(160px, 1fr))` over four groups with
  20px gaps: 4×160 + 3×20 = **700px** minimum. It fits on one row with room to
  spare, at roughly 245px per column.
- The widest cell in any group is a label plus a mono number: "Unrealised"
  (~60px at 11px Inter) + a 10px gap + eight mono digits (8 × 0.6em × 11px ≈
  53px) ≈ **123px**, well inside 245px. Spec 3's warning that mono digits are
  wide holds for the *table* columns, not for these two-column groups.

**Still owed: the browser half.** Font fallback (if Inter or JetBrains Mono
fails to load, both metrics above change), real values rather than assumed digit
counts, and the three surfaces wider than the expansion — Trades with all
eighteen columns picked, Analytics' strategy registry, and the heatmap at ten
horizons. Those belong to 2b's walk-through, at 1280px, and this appendix does
not claim them.

---

# Appendix B — the NG54 acceptance gate

Recorded 2026-08-13. Decision 2's four items, each with its result. **The gate
is not passed:** 2a and 2d pass, 2b and 2c are untouched and are the only
things between here and Release A.

## B1 — 2a route coverage, re-derived — PASS, with one addition and a method fix

### The method the spec asks for is not sufficient any more

Decision 2a and NG57's own verify step both say to re-derive coverage from:

```bash
grep -rn "\.route(" swingbot/admin/*.py
```

That grep returns 60 rules. The application actually serves **121**. The
difference is not all missing coverage — most of it is `/api/v1`, registered on
a blueprint in `api_v1/__init__.py`, which the glob `swingbot/admin/*.py` does
not descend into. But **12 of the missing rules are the SPA's own workspace
routes**, and those are invisible to the grep for a different and more
interesting reason: `spa.py:register()` mounts them with `app.add_url_rule()` in
a loop, not with a `@route` decorator. A pattern that only sees decorators
cannot see them.

That matters beyond bookkeeping. `register()` deliberately *skips* any rule the
Jinja UI already owns, so which SPA routes exist is a runtime outcome, not a
readable fact — and the grep would report the same 60 rules whether the skip
logic worked or was broken. Re-derive from the live map instead:

```bash
python -c "
import os; os.environ.setdefault('ADMIN_PASSWORD','x')
from swingbot.admin.app import app
for r in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    print(r.rule, sorted(r.methods - {'HEAD','OPTIONS'}), r.endpoint)"
```

This is what B1 was derived from, and **NG57's verify step should use it too** —
the grep there would pass on a build where the Jinja routes were deleted but
some `add_url_rule` caller still served HTML.

### The live map, classified

121 rules: 33 `/api/v1/*`, 13 SPA (`/app/<path:filename>` plus 12 workspace
rules), 1 Flask `static`, and 74 Jinja-era page, command and legacy-JSON rules.
Every one of the 74 is in Appendix A's tables — **unmapped: none** — with one
exception, below.

Two rules confirm `spa.py:register()`'s documented collisions actually behave as
its docstring claims, which is exactly what the grep could not have shown:

| Rule | Endpoint | Reading |
|---|---|---|
| `/risk` | `risk_panel` *(Jinja)* | the skip fired; no duplicate rule was registered |
| `/risk/<path:_rest>` | `spa_risk_sub` | the sub-route registered, as intended |
| `/trades` | `spa_trades` | no Jinja rule for the bare path, so the SPA has it |
| `/trades/<trade_id>` | `trade_detail` *(Jinja)* | Werkzeug ranks the narrower converter first, as documented |

All six workspaces are present (`spa_cockpit`, `spa_trades`, `spa_analytics`,
`spa_universe`, `spa_system`, and `spa_risk_sub`).

### The one route added after the audit

`GET /dashboard` → `dashboard_page`. It does not appear in Appendix A because
it did not exist when A was written — it was added by **NG53** so the Jinja
dashboard keeps a URL of its own once `/` hands over to the SPA, which is what
makes the rollback a restart. Verified absent at `d1ddb95` (the audit commit)
and present at HEAD.

It is **mapped, not unmapped**: same successor as `/`, the `/cockpit`
workspace. Its row has been added to A1's "Pages, replaced" so that table
stands on its own.

This is Decision 2a's own warning landing exactly as written — "routes added
after 2026-08-08 will not be in that table, and they are exactly the ones most
likely to be forgotten." One route, five days, one sub-project. It is worth
assuming the same thing happens again between here and Release A, and re-running
the live-map derivation immediately before NG55 rather than trusting this
appendix.

## B2 — 2b behaviour parity, walked — NOT DONE

Not attempted. It needs both UIs running against the same data, and its list
includes destructive actions — clear open trades, clear history, the killswitch
— which must not be walked against real `data/`. It needs a decision about
where it runs before it can run at all.

Nothing here is blocked on code. What B1 removes from it is only the question
"is anything unmapped"; every control still has to be exercised, plus the
browser half of A5's 1280px check.

## B3 — 2c degraded mode — NOT DONE

Same reason: it is a browser check against a running pair. The unit-level half
exists (`event-stream.spec.ts`, `connection.store.ts` and the shell's
`connection-status.ts` all model the degraded state, and those specs pass in
B4), but 2c asks whether every *workspace* stays correct with `/api/v1/events`
blocked, and that is not a question a unit test answers.

## B4 — 2d suite green — PASS, both suites

```
python scripts/testrun.py full   →  1537 passed, 136 skipped, 1 xfailed  in 84.5s
```

`0 failed`. The quarantined `test_flag_on_polls_open_plans` behaved as
`CLAUDE.md` documents. Note the pass count: `CLAUDE.md`'s reference baseline of
~1015 is the `main` figure and this branch is 500-odd tests above it, which is
the migration's own test mass, not drift. **NG57 must record the post-deletion
baseline**, as its checklist already says.

### The frontend suite, which 2d does not name — run anyway

`ng test` (Vitest, jsdom): **294 passed across 18 files.** Decision 2d predates
the frontend existing; a gate on an Angular cutover that never runs the Angular
tests is a gap in the gate, not in the suite.

It passed *with 7 unhandled rejections*, all "this._window.matchMedia is not a
function" out of `fancy-canvas`, which `lightweight-charts` calls to watch the
device pixel ratio the moment a chart is created — jsdom 28 implements no
`matchMedia` at all. They failed nothing, which is the argument for fixing them
rather than living with them: seven errors permanently in the output are seven
errors nobody reads, and the eighth will be real. Fixed with
`testing/match-media-polyfill.ts`, in the same shape as the existing
`dialog-polyfill.ts`, installed by `app.routes.spec.ts` — the only spec that
routes into the chart-bearing detail views. Re-run: 294 passed, **no errors**.

Deliberately not fixed: jsdom's `HTMLCanvasElement.getContext` notices. Silencing
those means adding the native `canvas` package as a dev dependency to satisfy a
chart nothing asserts against, which is a worse trade than a console notice.

## B5 — Gate status

| Item | Result |
|---|---|
| 2a route coverage | **PASS** — nothing unmapped; `/dashboard` added to A1; method changed to the live url_map |
| 2b behaviour parity | **NOT DONE** — needs a running pair and a safe data story |
| 2c degraded mode | **NOT DONE** — browser check, same prerequisite |
| 2d suite green | **PASS** — 1537 Python, 294 frontend, 0 failed, 0 errors |

**Do not ship Release A (NG55).** Two of four are owed.
