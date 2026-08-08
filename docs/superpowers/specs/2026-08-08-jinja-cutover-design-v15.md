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
