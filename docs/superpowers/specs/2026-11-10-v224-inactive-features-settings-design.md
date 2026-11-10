# v224 — Inactive features: a Settings category for shadow and disabled features

**Version:** ui 1.40.4 · bot 2.18.1
**Bump:** ui minor, bot patch (a new Settings category the partner uses; the backend only adds a read-only field to an existing response)
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
in shadow or off. Each entry shows what the feature does and where its evidence
stands, and has an **Enable** action behind a confirmation.

## Decisions (partner, 2026-11-10)

1. **Curated registry, not auto-detection.** Only settings tagged as features
   appear. Auto-detecting "any select at `shadow`/`off` and any false
   `*_ENABLED`" would also list knobs, notification channels and research
   modes, which makes the list noisy and misleading.
2. **Enable is a confirmed write.** Clicking Enable opens a dialog that shows
   the feature's description, its evidence line and the exact `.env` diff. Only
   confirming writes. The write goes through the existing settings save path.
3. **Every enabled feature can be turned back off from the same place.**

## Design

### Backend: the feature registry

**`swingbot/config.py` gains `FEATURE_REGISTRY`**, a tuple of frozen
`FeatureEntry` records declared beside `_MODE_VALUES`:

| Field | Meaning |
|---|---|
| `key` | the `Field.key` it controls (must exist in the schema) |
| `title` | short human name ("Market-shock detector") |
| `description` | one or two sentences on what turning it on changes |
| `status` | one of `shadow-soak`, `awaiting-verdict`, `no-lift`, `partner-call` |
| `evidence` | one line citing the spec/ledger/result behind the status ("v209 shadow since 2026-11-10; no verdict yet") |
| `enable_value` | the value Enable writes (`"live"`, `"on"`, `"true"`) |
| `disable_value` | the value Disable writes (`"shadow"`, `"off"`, `"false"`) |

A feature is **inactive** when its current value is not `enable_value`. A
select with three states (`off`/`shadow`/`live`) is inactive at both `off` and
`shadow`. The UI badge shows which of the two it is.

**`GET /system/settings`** (`swingbot/admin/api_v1/system.py:_settings_document`)
gains a top-level `features` list. Each element has the registry fields plus
`value` (current effective value) and `inactive` (bool). The existing `sections`
payload is untouched, so a feature still appears in its home section as well.
A sensitive field can never be in the registry, and a test enforces this.

**No new write endpoint.** Enable and Disable call the existing
`POST /system/settings/preview` (for the dialog's diff) and
`PUT /system/settings` with a one-key body. `_effective_form` already fills
every absent key from the current `.env`, so a one-key PUT changes exactly one
line. Auth, validation, the settings audit row and the SIGHUP hot-reload are all
inherited unchanged. Viewer accounts (v207) see the category but get no
Enable/Disable buttons, the same as every other write control (`auth/write-calls.ts`).

### Inclusion rule and initial registry

A setting joins the registry when it **switches a whole trading, alerting or
exit behaviour that was built and deliberately left off or in shadow**. These
stay out:

- notification channels and credentials (`ALERT_EMAIL_ENABLED`, `ALERT_PUSH_ENABLED`)
- data-provider and infrastructure switches (`ALPACA_ENABLED`, `TAPE_SHARED_ENABLED`, `PLAN_REBUILD_ENABLED`, `ADMIN_REFRESHER`, `MARKETDATA_LAYER`)
- measurement-only research modes (`*_RESEARCH_MODE`)
- multi-valued signal-source selects where no value means "off" (`FVG_LEVELS_MODE`, `CONFLUENCE_ATR_TARGET_MODE`, `POSITION_SIZING_MODE`)
- anything eToro or real-money (the roadmap forbids `account: real`; no such key is ever registered)

The candidates to check in the first plan task:

- **Mode selects:** `MARKET_SHOCK_MODE`, `STRATEGY_ALERTS_MODE`, `PLAN_ENGINE_V2`
- **Checkboxes:** `REGIME_GATES_ENABLED`, `LEVEL_LIFECYCLE_STOPS_ENABLED`, `AVWAP_LEVELS_ENABLED`, `PYRAMIDING_ENABLED`, `VOLUME_PROFILE_NODES_ENABLED`, `DATA_DRIVEN_STOPS_ENABLED`, `ADAPTIVE_RUNNER_TRAIL_ENABLED`, `RUNNER_GIVEBACK_ENABLED`, `STALL_EXIT_ENABLED`, `ACCEPTANCE_EXIT_ENABLED`, `SCALE_OUT_ENABLED`, `HTF_CONFLUENCE_ENABLED`, `DD_THROTTLE_ENABLED`, `NEAR_TP_TIMEOUT_ENABLED`, `REVERSAL_ENABLED`, `OPEX_CAUTION_ENABLED`, `DECISION_CHART_ENABLED`, `NEXT_SESSION_SCAN_ENABLED`, `SHORT_UNIVERSE_ENABLED`

**`status` and `evidence` are written from sources, never invented.** The
sources are the field's `help` text, its spec or plan, the pre-registration
ledger, and `docs/superpowers/{plans,specs}/no-lift/`. Where none of them
supports a verdict, the status is `partner-call` and the evidence says
"no recorded verdict". A feature whose arm closed **no-lift** stays listed:
being disabled is exactly what it is, and the partner may still want to see it.
Its dialog carries a warning (below). Each excluded candidate gets a one-line
reason in the plan task's commit message.

### Frontend: the category

**Rail placement.** `settings-tab.ts` adds one synthetic category, **Features**,
at the top of the rail. It is built from `features` and not from a `config.py`
section. `settings-grouping.ts:settingsCategories` stays key-agnostic: the
synthetic category is added in the tab, not by matching keys. The rail entry
shows a count badge of inactive features.

**Panel layout.**

- **Inactive** (open): one card per inactive feature. Each card shows the
  title, a state badge (`Shadow` or `Off`), a status chip, the description and
  the evidence line, and an **Enable** button. They are ordered by status
  (`shadow-soak`, `awaiting-verdict`, `partner-call`, `no-lift`), then by
  title.
- **Enabled** (collapsed by default): the registry features currently at
  `enable_value`, each with a **Disable** button.
- **Empty state:** "Every registered feature is enabled." The Inactive group
  is replaced, not hidden.

**Confirm dialog.** Enable or Disable first calls `preview` and then shows:

- the description and evidence
- the exact diff line (`MARKET_SHOCK_MODE: shadow → live`)
- "Restart required" when `restart_required` is non-empty
- for Enable, the sentence "This changes live bot behaviour from the next scan."

A `no-lift` feature's dialog adds a warning block: "Measured no-lift. Enabling
is against the recorded evidence." The confirm button there reads **Enable
anyway**. Confirming sends the one-key PUT, then reloads the settings document
so the card moves groups. A hot-reload failure is shown the way the existing
Save shows it.

**Dirty form guard.** While the Settings form has unsaved edits, Enable and
Disable are disabled, with the hint "Save or discard your pending changes
first". A one-key write followed by a reload would otherwise throw those edits
away silently.

**Three devices (`docs/claude/ui-design.md`).**

- **Phone:** single-column cards, buttons at full card width with at least 44 px
  touch targets, and a full-screen dialog.
- **Tablet:** a two-column card grid.
- **Desktop:** two columns inside the existing settings content width, with the
  rail unchanged.
- Long evidence lines wrap and are never truncated.

The plan checks all three widths with Playwright, logging in with `.env`'s
admin credentials.

## Error handling

- A registry key missing from the schema fails a unit test. At runtime the
  entry is skipped with a warning and the page never 500s.
- A preview or PUT failure shows the API error inside the dialog and leaves the
  card where it was.
- A current value that is neither `enable_value` nor `disable_value` (for
  example `off` on a three-state select) is shown as is. Disable is not offered
  for it, and Enable writes `enable_value`.

## Testing

**Backend (`tests/`, existing settings suite):**

- registry integrity: every key exists, is not sensitive, and has
  `enable_value`/`disable_value` valid for its field type and `_MODE_VALUES`;
  statuses come from the enum; keys are unique
- `inactive` for each value shape (checkbox true/false, three-state select at
  each state)
- the `features` payload shape on `GET`
- a one-key PUT changes exactly that `.env` line

**Frontend (`*.spec.ts` beside the components):**

- the category renders from `features` and its count badge
- grouping and order
- the empty state
- dialog content for normal and no-lift features
- the PUT body is exactly one key
- reload after save
- the dirty-form guard
- the viewer sees no buttons
- error display

Changed-file test runs only. CI runs the full suite.

## Out of scope

- editing the registry from the UI
- auto-detection of features
- scheduled or conditional promotion
- any eToro switch
- changing what any feature does

## What follows

Every future spec that ships a feature gated off or in shadow adds its
`FEATURE_REGISTRY` row in the same plan. That plan's close-out updates the row's
`status`/`evidence` when a verdict lands.
