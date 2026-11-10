# v224 — Inactive features: a Settings category for shadow and disabled features

**Version:** ui 1.40.4 · bot 2.18.1
**Bump:** ui minor, bot patch (a new Settings category the partner uses; the backend adds a read-only field and an optimistic-concurrency check to the existing settings endpoints)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** ux-designer, staff-engineer, financial-advisor

## Why

The bot ships many behaviours gated off or in shadow while they wait for a
soak, a verdict or a partner call. Examples are `MARKET_SHOCK_MODE` (shadow
since v209), `STRATEGY_ALERTS_MODE`, and around twenty `*_ENABLED` checkboxes.
They are scattered across the Settings sections (`Universe & Scanning`,
`Exit quality`, `Market Shock`, …) next to ordinary knobs. Nothing on the admin
UI answers "what is built but not live, and why". To promote one, the partner
has to remember the key, find its section, and know which value means "live".

This spec adds one Settings category that lists every real feature currently
in shadow or off. Each entry shows what the feature does, where its evidence
stands and what enabling it does to alerts and dollar risk, and has an
**Enable** action behind a confirmation. The partner trades real money from
alerts with resting orders placed at alert time, so the change takes effect
from the next scan.

## Decisions (partner, 2026-11-10)

1. **Curated registry, not auto-detection.** Only settings tagged as features
   appear. Auto-detecting "any select at `shadow`/`off` and any false
   `*_ENABLED`" would also list knobs, notification channels and research
   modes, which makes the list noisy and misleading.
2. **Enable is a confirmed write.** Clicking Enable opens a dialog that shows
   the feature's description, its evidence line, its money consequence and the
   exact `.env` diff. Only confirming writes. The write goes through the
   existing settings save path.
3. **Every enabled feature can be turned back off from the same place.**

## Design

### Backend: the feature registry

**The registry lives in `swingbot/admin/feature_registry.py`.** It is a tuple of
frozen `FeatureEntry` records keyed by `Field.key`. Its home is the admin
package, not `swingbot/config.py`: it is admin-only presentation metadata, so a
verdict update never touches the `.env` schema module that all three containers
import (staff-engineer).

| Field | Meaning |
|---|---|
| `key` | the `Field.key` it controls (must exist in `config.FIELDS`) |
| `title` | short human name ("Market-shock detector") |
| `description` | one or two sentences on what turning it on changes |
| `impact` | one of `alert-volume`, `risk-size`, `exit`, `risk-reducing`, `display` |
| `status` | one of `shadow-soak`, `awaiting-verdict`, `screen-pass`, `no-lift`, `partner-call` |
| `evidence` | one line citing the spec, ledger id or result behind the status |
| `enable_value` | the value Enable writes (`"live"`, `"on"`, `"true"`) |
| `disable_value` | the value Disable writes (`"shadow"`, `"off"`, `"false"`) |

**`impact` drives a fixed consequence sentence in the dialog.** Each class has
one sentence (financial-advisor):

| `impact` | Sentence |
|---|---|
| `alert-volume` | "May add alerts, and so resting orders, from the next scan." |
| `risk-size` | "Changes position size or open dollar risk per trade or across the book." |
| `exit` | "Changes when open trades exit." |
| `risk-reducing` | "Reduces risk. Turning it off raises risk." |
| `display` | "Changes what alerts show, not what is traded." |

A quantified alerts-per-week or heat delta is shown only when `evidence` quotes
a sourced figure. The bot has no generic way to estimate one, and an invented
figure is worse than none.

**There is no "validated" status.** A feature is in this list because it has no
live validation. Every status chip reads as unvalidated: `screen-pass` shows
"Screen pass, not validated live", and the others show "No verified edge" or
"Measured no-lift". No card or dialog shows green or approval styling
(financial-advisor).

**`value` and `inactive` use the bot's own casts.** `value` is the current value
read the way the bot reads it: `_truthy` for checkboxes, `_cast_mode` for mode
selects (`swingbot/config.py`). Without that, a hand-edited `on` or `Live` in
`.env` would show a feature as inactive while the bot runs it live
(staff-engineer). A feature is **inactive** when that value is not
`enable_value`. A three-state select is inactive at both `off` and `shadow`, and
the badge shows which one.

**`GET /system/settings`** (`swingbot/admin/api_v1/system.py:_settings_document`)
gains two top-level fields:

- `features`: each element has the registry fields plus `value`, `inactive`, and
  `last_changed` (timestamp of the newest settings-audit row touching that key,
  or null)
- `env_version`: a hash of the current `.env` text

The existing `sections` payload is untouched, so a feature still appears in its
home section as well.

**Writes: no new endpoint, plus a concurrency check.** Enable and Disable call
the existing `POST /system/settings/preview` for the dialog's diff, then
`PUT /system/settings` with a one-key body. `_effective_form` fills every absent
key from the current `.env`, so the only setting whose value changes is the
named one. `_build_env_text` still rewrites the whole file, as every save does.

Auth, validation, the settings audit row, the `.env` snapshot
(`swingbot/admin/helpers.py`) and the SIGHUP hot-reload are all inherited
unchanged. Viewer accounts (v207) are refused server-side by
`swingbot/admin/access.py` and get no buttons in the UI.

**Every PUT, the existing full-form Save included, carries `env_version`.** A
mismatch returns `409 conflict` and writes nothing. Without this check, a second
tab's stale full-form Save would silently revert an Enable made on the phone
(staff-engineer). On 409 the UI reloads the settings document and says another
change landed first.

**Integrity tests**, each failing on a bad row:

- every key exists in `config.FIELDS` and is not `sensitive`
- every key is `hot_reloadable`, which is what lets the dialog say "from the next scan"
- `enable_value`/`disable_value` are valid for the field type and `_MODE_VALUES`
- statuses and impacts come from their enums
- keys are unique
- no key matches `ETORO_*` or anything money-account related (financial-advisor)
- every `evidence` naming ExpR, win rate or N also says "pre-cost" or "net of costs" (financial-advisor; `pooled-numbers` governs how such a figure is derived)

### Keeping the registry true

- **Owner:** the plan that ships a gated feature adds its row in the same plan.
- **Updates:** `/close-out` gains a step. When the closing plan's spec names a
  `FEATURE_REGISTRY` key, that row's `status`/`evidence` is updated in the
  close-out commit, and it moves to `no-lift` when the plan closes no-lift.
- **Mirror:** the step ships its Codex mirror via `sync_codex.py`.
- **Release:** a row edit changes admin presentation only, so it is a ui patch
  at most and never a bot bump.

### Inclusion rule and initial registry

A setting joins the registry when it **switches a whole trading, alerting or
exit behaviour that was built and deliberately left off or in shadow**. These
stay out:

- notification channels and credentials (`ALERT_EMAIL_ENABLED`, `ALERT_PUSH_ENABLED`)
- data-provider and infrastructure switches (`ALPACA_ENABLED`, `TAPE_SHARED_ENABLED`, `PLAN_REBUILD_ENABLED`, `ADMIN_REFRESHER`, `MARKETDATA_LAYER`)
- measurement-only research modes (`*_RESEARCH_MODE`)
- multi-valued signal-source selects where no value means "off" (`FVG_LEVELS_MODE`, `CONFLUENCE_ATR_TARGET_MODE`, `POSITION_SIZING_MODE`)
- anything eToro or real-money (the roadmap forbids `account: real`; enforced by a test)

The candidates to check in the first plan task:

- **Mode selects:** `MARKET_SHOCK_MODE`, `STRATEGY_ALERTS_MODE`, `PLAN_ENGINE_V2`
- **Checkboxes:** `REGIME_GATES_ENABLED`, `LEVEL_LIFECYCLE_STOPS_ENABLED`, `AVWAP_LEVELS_ENABLED`, `PYRAMIDING_ENABLED`, `VOLUME_PROFILE_NODES_ENABLED`, `DATA_DRIVEN_STOPS_ENABLED`, `ADAPTIVE_RUNNER_TRAIL_ENABLED`, `RUNNER_GIVEBACK_ENABLED`, `STALL_EXIT_ENABLED`, `ACCEPTANCE_EXIT_ENABLED`, `SCALE_OUT_ENABLED`, `HTF_CONFLUENCE_ENABLED`, `DD_THROTTLE_ENABLED`, `NEAR_TP_TIMEOUT_ENABLED`, `REVERSAL_ENABLED`, `OPEX_CAUTION_ENABLED`, `DECISION_CHART_ENABLED`, `NEXT_SESSION_SCAN_ENABLED`, `SHORT_UNIVERSE_ENABLED`

**`status`, `impact` and `evidence` are written from sources, never invented.**
The sources are the field's `help` text, its spec or plan, the pre-registration
ledger, and `docs/superpowers/{plans,specs}/no-lift/`. Where none of them
supports a verdict, the status is `partner-call` and the evidence says
"no recorded verdict". A feature whose arm closed **no-lift** stays listed:
being disabled is exactly what it is, and the partner may still want to see it.
Each excluded candidate gets a one-line reason in the plan task's commit message.

### Frontend: the category

**Rail placement.** `settings-tab.ts` adds one synthetic category, **Features**,
at the top of the rail. It is built from `features` and not from a `config.py`
section. `settings-grouping.ts:settingsCategories` stays key-agnostic: the
synthetic category is added in the tab, not by matching keys. The rail entry
shows a count badge of inactive features with an accessible name
("Features, 14 inactive").

**Panel layout.**

- **Group headings carry counts:** "Inactive (14)", "Enabled (6)".
- **Filter chips above the Inactive group:** All, Shadow, Off, No-lift.
  The registry is bounded (~22 rows), so grouping and the chips stand in for a
  pager (ui-design.md § Tables and pagers). A pager would split a list the
  partner reads whole.
- **Inactive** (open): one card per inactive feature. Each card shows:
  - the title
  - a state badge with text (`Shadow` or `Off`)
  - a status chip with text (`no-lift` styled as a warning, never green)
  - an impact line
  - the description and the evidence line
  - "Last changed <date>" when `last_changed` is set
  - an **Enable** button

  They are ordered by status (`shadow-soak`, `screen-pass`, `awaiting-verdict`,
  `partner-call`, `no-lift`), then by title.
- **Enabled** (collapsed by default): the registry features currently at
  `enable_value`, each with a **Disable** button.
- **Empty state:** "No registered feature is currently off or in shadow."
  It has a link that expands the Enabled group.
- **Loading state:** the skeleton cards the settings tab already uses.
- **Error state:** when `features` is absent or the GET fails, an inline error
  with Retry; the rest of Settings still works.
- **Viewer:** each card shows a "Read-only" note in place of its buttons.

**Confirm dialog.** The dialog opens at once with a spinner while `preview`
runs. It then shows:

- the description, evidence and status chip
- the impact sentence
- the exact diff line, wrapped with `overflow-wrap: anywhere` inside its own
  box, so a key like `LEVEL_LIFECYCLE_STOPS_ENABLED` never scrolls the page
- "Restart required" when `restart_required` is non-empty
- for Enable, the sentence "Takes effect from the next scan."
- the rollback route: "Undo with Disable here; every save also keeps a `.env` snapshot."

**Typed confirmation for the two risk-raising cases** (financial-advisor). Both
replace the plain confirm with a field where the partner types the feature title:

- Enable of a `no-lift` feature. It adds a warning block ("Measured no-lift.
  Enabling is against the recorded evidence."), and the button reads
  **Enable anyway**.
- Disable of a `risk-reducing` feature (e.g. `DD_THROTTLE_ENABLED`).

**Dialog behaviour.**

- Initial focus is on Cancel.
- Escape closes the dialog, focus is trapped inside it, and closing returns
  focus to the card's button.
- Confirm is disabled while the PUT is in flight, so a double submit is
  impossible.

**After saving.** Confirming sends the one-key PUT with `env_version`, then
reloads the settings document:

- The card moves groups, and an inline note "Enabled. Moved to Enabled"
  (or the reverse) stays in its place for 5 s.
- Focus goes to the next card in the list, or to the group heading when the
  list is empty.

**When a write fails.**

- A hot-reload failure is shown the way the existing Save shows it.
- A validation refusal (`_coupling_problem` caused by an unrelated key already
  on disk) is shown verbatim in the dialog, naming that key, and the card stays
  put.

**Dirty form guard.** While the Settings form has unsaved edits, Enable and
Disable are disabled on every card. Each card shows the hint "Save or discard
your pending changes first", with a **Discard and continue** action. A one-key
write followed by a reload would otherwise throw those edits away silently.

**Three devices (`docs/claude/ui-design.md`).** The rail behaves as the
existing settings tab does at each width.

| Width | Layout |
|---|---|
| Phone (390) | single-column cards; full-width buttons with touch targets of at least 44 px; full-screen dialog |
| Tablet (768) | two-column card grid |
| Desktop (1440) | three columns in the settings content width |

Long evidence lines wrap and are never truncated. The plan checks all three
widths with `frontend/scripts/layout-audit.mjs` through Playwright, logging in with `.env`'s
admin credentials.

## Error handling

- A registry key missing from `config.FIELDS` fails a unit test. At runtime the
  entry is skipped with a warning and the page never 500s.
- A preview or PUT failure shows the API error inside the dialog and leaves the
  card where it was.
- An `env_version` mismatch returns 409: the UI reloads and explains, and
  nothing is written.
- A current value that is neither `enable_value` nor `disable_value` (for
  example `off` on a three-state select) is shown as is. Disable is not offered
  for it, and Enable writes `enable_value`.
- **Rollback:** Disable on the same card. If the admin UI itself is down, the
  per-save `.env` snapshot or `scripts/ops/rollback_to.sh`.

## Testing

**Backend (`tests/`, existing settings suite):**

- every registry integrity rule above
- `inactive` and `value` for each value shape, including the hand-edited
  casts `on`/`Live`
- the `features`, `last_changed` and `env_version` payload
- a one-key PUT: the `settings_diff` names only that key, and re-parsing `.env`
  yields the new value with every other value unchanged
- a stale `env_version` gets 409 and leaves `.env` untouched, for both the
  one-key PUT and a full-form PUT

**Frontend (`*.spec.ts` beside the components):**

- category and count badge, including its accessible name
- grouping, order, counts and filter chips
- empty, loading and error states
- dialog content per `impact` and per status (no-lift warning, typed confirm,
  risk-reducing Disable)
- focus handling
- in-flight disable
- the PUT body is exactly one key plus `env_version`
- the 409 path
- reload and the moved-note
- the dirty-form guard and Discard and continue
- the viewer's Read-only note
- error display

Changed-file test runs only. CI runs the full suite.

## Out of scope

- editing the registry from the UI
- auto-detection of features
- scheduled or conditional promotion
- any eToro switch
- changing what any feature does
- a settings-audit history view (only `last_changed` is shown)

## What follows

Every future spec that ships a feature gated off or in shadow adds its
`feature_registry.py` row in the same plan. `/close-out` keeps the row's status
current.

## Panel review

- financial-advisor: Enable dialog never shows a badge tier, so a feature could read as endorsed (BLOCKING) -- applied: no "validated" status exists, every chip reads unvalidated, no green styling
- financial-advisor: "changes live behaviour" omits the alert-volume/dollar-risk consequence (BLOCKING) -- applied: `impact` field with a fixed consequence sentence per class; a quantified delta is shown only when sourced, because none can be computed generically
- financial-advisor: evidence figures must be labelled pre-cost/net -- applied as an integrity test
- financial-advisor: eToro exclusion only a policy -- applied as an integrity test
- financial-advisor: empty-state copy could read as "fully on / optimal" -- applied: reworded
- financial-advisor: one-click Enable anyway on no-lift; Disable of a risk-reducing feature -- applied: typed confirmation for both
- financial-advisor: no audit trail on the card -- applied: `last_changed` per card; a full history view stays out of scope
- staff-engineer: `inactive` compared raw `.env` strings, not the bot's casts -- applied
- staff-engineer: "one-key PUT changes exactly one line" is false, `_build_env_text` rewrites the file -- applied: test asserts on `settings_diff` and re-parsed values
- staff-engineer: a stale tab's full-form Save silently reverts an Enable -- applied: `env_version` with 409 on every PUT
- staff-engineer: registry prose in `config.py` forces bot bumps and goes stale unowned -- applied: moved to `swingbot/admin/feature_registry.py`, owner named, `/close-out` step added
- staff-engineer: rollback path and `_coupling_problem` refusals unstated -- applied
- ux-designer: dirty guard hint shown once -- applied: per card, with Discard and continue
- ux-designer: no pager for ~22 cards -- applied: group counts and filter chips, with the reason no pager is needed
- ux-designer: empty, loading and error states incomplete -- applied
- ux-designer: dialog loading, in-flight and focus behaviour unspecified -- applied
- ux-designer: the diff line overflows at 390 px -- applied: `overflow-wrap: anywhere` in its own box
- ux-designer: badges colour-only, rail badge unlabelled, viewer bare card -- applied
- ux-designer: tablet and desktop both two-column; name `layout-audit.mjs` -- applied: 1/2/3 columns, audit tool named
- ux-designer: card moving groups reads as disappearance -- applied: inline moved-note and focus rule
