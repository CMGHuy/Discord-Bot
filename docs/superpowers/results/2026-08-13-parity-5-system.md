# Jinja → SPA parity audit, group 5: Settings, Logs and the shell

Task SR45 of `2026-08-13-v21-spa-refresh.md`. Templates audited:
`settings.html`, `_settings_diff.html`, `logs.html`, `base.html`, `login.html`,
together with their routes (`app.py:settings_page`/`settings_preview`/
`save_settings`/`settings_export`/`settings_import`/`logs_page`/`logs_raw`/
`logs_clear`/`restart_bot`/`login`/`logout`).

Three statuses only — `migrated`, `dropped on purpose`, `missing`. Nothing is
left unclassified.

**The theme of this group is affordances, not data.** Settings, Logs and the
shell all migrated their content; what thinned out is the machinery around it —
the search box over 100+ settings fields, the reset-to-default button, the log
level filter, the line-count selector, the version footer. Each is small; the
settings search is the one whose absence changes how usable the page is.

---

## `base.html` — the shell

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Page title "`<page>` — Swing Bot Admin" | `base.html:6` | migrated (narrowed) | The document title is static; it does not name the current workspace |
| Favicons (png/ico/32/16) and apple-touch-icon | `:14-18` | migrated | SR6's identity assets |
| Inter webfont | `:19` | migrated | Same font, loaded by the SPA build |
| `tokens.css` + `style.css` | `:20-21` | migrated | SR2 rewrote the palette into the SPA's own `tokens.css` |
| Brand: avatar + "Swing Bot" + 📈 | `:40-49` | migrated | The sidebar mark: avatar, "swingbot", "paper" tag (`shell.html:11-24`) |
| Nav items with active highlight | `:50-58` | migrated | `routerLinkActive`, `shell.html:26-44` |
| Font/UI zoom control (A−/A+, 80-150%, persisted) | `:59-63, 129-160` | **missing** | — no text-size control anywhere; the saved `adminFontZoom` has no successor |
| Log out button in the sidebar footer | `:64-67` | migrated | Moved into the profile menu (`profile-menu.ts:55-58`), deliberately one control rather than two |
| "Last updated" from `VERSION.json` | `:68-74` | **missing** | `GET /health` returns `versions.last_updated` and `ApiClient.health()` exists (`api-client.ts:82`); nothing calls it |
| Version tag "UI vN · Bot vN" | `:75-79` | **missing** | — same endpoint, same gap. With SR48 about to bump `ui` to 1.2.0, the UI will not show its own version |
| Hamburger toggle for the mobile sidebar | `:85, 95-127` | migrated | The overlay menu button, `shell.html:4-8`, plus the scrim and Escape handling |
| Page header `<h1>{{ title }}` | `:86` | migrated | Each workspace renders its own `<h1>` |
| Flash banner (`msg` + ok/err) | `:88-90` | migrated | `sb-toast-host` (`shell.html:88`), plus per-panel `role="status"` / `role="alert"` lines |
| Sidebar collapse to a rail, persisted | — | n/a | New in the SPA (SR21) |
| Killswitch banner in the topbar | — | n/a | New at shell level (`shell.html:72-74`) — the Jinja killswitch banner was on `/risk` only |
| Connection status | — | n/a | New; there was no connection state to show when every page was a full reload |

---

## `login.html` — sign in

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Bot avatar on the login card | `login.html:26-29` | dropped on purpose | The SPA login is a wordmark ("swingbot" / "admin"), `login.html:3-4`. SR6 put the avatar in four places and this was not one of them |
| "Swing Bot Admin" heading | `:30` | migrated | The wordmark and its subtitle |
| Error banner | `:31-33` | migrated | `@if (error())` with `role="alert"` |
| Username field, `autocomplete="username"`, autofocus | `:36-39` | migrated | Same attributes (`login.html:6-15`) |
| Password field, `autocomplete="current-password"` | `:40-43` | migrated | Same |
| Sign in button | `:44` | migrated | Plus a `submitting()` state the form post could not have |
| `next` hidden field — return to the page you were sent from | `:35` | **missing** | — the SPA always lands on the Dashboard after sign-in, so a deep link followed while signed out loses its destination |
| Required-field validation (`required` on both inputs) | `:38, 42` | **missing** | — neither input is marked required and the button is not disabled on an empty form |

---

## `settings.html` + `_settings_diff.html` — the settings editor

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Fields grouped into sections | `settings.html:107-131` | migrated | One `sb-panel` per section, `settings-tab.ts:46-103` |
| Section icon | `:111` | dropped on purpose | The SPA has an icon sprite (SR20) and does not decorate headings with emoji |
| Section description | `:113` | migrated | `section.description`, `settings-tab.ts:48-50` |
| Field-count badge per section | `:115` | **missing** | — |
| Field label | `:49` | migrated | Every control takes a `label` |
| Field help text, HTML-safe for `POSITION_SIZING_MODE` | `:58-62` | migrated (narrowed) | `field.help` rendered as text; the one field with markup in its help loses its formatting |
| "Env var: KEY" fallback when there is no help | `:61` | migrated | The key is always shown, `settings-tab.ts:88` |
| Checkbox / select / password / number / text control types | `:64-92` | migrated | `controlOf(field)` switch, `settings-tab.ts:55-82` |
| `min` / `max` / `step` on numeric fields | `:83-85` | migrated | Passed through to `sb-text-input` |
| Password placeholder "blank = keep current" | `:78` | migrated | "stored value hidden — type to replace", `settings-tab.ts:96` |
| "↺ restart" badge on non-hot-reloadable fields | `:51` | migrated | "restart required", `settings-tab.ts:89-94` |
| Default-value badge beside the label | `:50` | **missing** | — the default is never shown, so "what was this before I touched it" has no answer on screen |
| Changed-from-**default** dot | `:48` | **missing** | The SPA's `.changed` class marks fields edited in the current draft (`isChanged`, `settings-tab.ts:415`), which is a different question. A field that has been saved away from its default looks untouched |
| Per-field reset-to-default button | `:52-56, 265-270` | **missing** | — no way to restore one field; `store.resetDraft()` discards the whole draft |
| Search settings by name or description | `:96-97, 250-263` | **missing** | — over a hundred fields across every section, with no way to find one by name. The largest usability loss in this group |
| "Only changed" filter | `:99` | **missing** | — follows from the changed-from-default state not existing |
| "● = changed from default" legend | `:101-103` | **missing** | — |
| Save & reload bot | `:134` | migrated | The save bar, `settings-tab.ts:107-148` |
| Save hint: hot reload vs restart | `:135` | migrated | Per-field "restart required" plus the diff's `restartRequired()` list (`settings-tab.ts:182-187`) |
| Diff preview before saving | `:140-181`, `_settings_diff.html` | migrated | "Pending changes" panel, `settings-tab.ts:156-188` — a panel rather than a modal |
| Diff table: Setting / Current / New | `_settings_diff.html:4-15` | migrated | `settings-tab.ts:158-181` |
| Diff "Nothing changed." | `_settings_diff.html:2` | migrated | "No changes" in the save bar |
| Diff modal Confirm & Save / Cancel | `settings.html:147-150` | migrated | Save and Discard in the bar |
| Hot-reload result reported after saving | — | n/a | New (`store.saved()`, `settings-tab.ts:191-207`) — the Jinja page redirected with a flash |
| "Settings changed elsewhere while you were editing" | — | n/a | New (`store.settingsStale()`, `settings-tab.ts:28-41`) |
| Recent changes audit, collapsed, with a count | `:183-201` | migrated (narrowed) | "Recent changes" panel, `settings-tab.ts:208-227` — always expanded, no count in the heading |
| Audit entry timestamp + per-key diff | `:191-196` | migrated | Same shape |
| Export .env | `:206` | migrated | Export/import panel, `settings-tab.ts:229-263` |
| "Export omits credentials/tokens entirely; import accepts them" | `:209` | **missing** | — the asymmetry is not stated, and it is the reason an exported file is safe to hand around |
| Import .env by pasting text | `:221-223` | migrated | The import textarea, placeholder "KEY=value, one per line — as exported." |
| Import .env by **file upload** | `:224` | **missing** | — paste only; a saved `.env` has to be opened and copied first |
| Restart bot container + confirm | `:232-247` | migrated | The Scan tab's Bot process panel (`scan-tab.ts:104-135`), with a confirm dialog |
| "Docker socket not mounted" explanation | `:241-245` | migrated | `restartAvailable()` hides the button and explains why (`scan-tab.ts:119-128`) |

---

## `logs.html` — the log viewer

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Source tabs: Bot / Admin UI | `logs.html:4-19` | migrated | Two pressed-state buttons, `logs-tab.ts:23-33` |
| Line-count selector (100 / 500 / 1000 / 2000 / 5000) | `:21-31` | **missing** | `SystemStore` has no `lines` control (`system.store.ts:390, 433` expose only source), so the tail is whatever the server defaults to. The count is *displayed* (`logs-tab.ts:64`) but cannot be changed |
| Auto-refresh checkbox, every N seconds | `:32-34, 150-152` | dropped on purpose | Stated in the component: a log that refreshes on a timer looks live without being live, and scrolls a traceback away mid-read (`logs-tab.ts:11-14`) |
| Refresh button | `:35` | migrated | `logs-tab.ts:34-42` |
| Raw view in a new tab | `:36` | migrated | A real anchor to the raw endpoint, `logs-tab.ts:45` |
| Clear log + confirm | `:37-40` | migrated | Clear button + `sb-confirm-dialog` |
| "Hard reload bot" from the logs page | `:49-58` | dropped on purpose | Restart is one control on the Scan tab. Two restart buttons is the duplication the workspace model removes — though this one was placed on Logs deliberately, which SR46 may want to weigh |
| Log file path | `:59` | migrated | The panel heading is the path, and `.meta` repeats it |
| Level filter checkboxes: INFO / WARNING / ERROR / DEBUG | `:62-76, 115-132` | **missing** | — no filtering of any kind over the tail |
| Per-level colourising of whole lines | `:80-113` | **missing** | — the `<pre>` is uniform; an ERROR line is not distinguishable at a glance |
| "N line(s) hidden by filter" counter | `:75, 127-128` | **missing** | — follows from the filter being absent |
| Scroll-to-bottom on load, preserved across refresh | `:136, 143-146` | **missing** | — the tail opens at the top, so the newest lines need a manual scroll |
| Empty-log state | — | n/a | New ("This log is empty.", `logs-tab.ts:66`) |

---

## Tally for this group

| Status | Count |
|---|---|
| migrated (incl. narrowed) | 40 |
| dropped on purpose | 4 |
| **missing** | 20 |
| new in the SPA (not a parity row) | 6 |

The `missing` rows group as:

1. **Settings navigability** — 6 rows: the search box, the "only changed"
   filter and its legend, the default-value badge, the changed-from-default
   dot, and the per-field reset. Together they are what made a hundred-field
   form usable; individually each looks optional. Note that the changed-dot and
   the reset button both need the field's default, which `SettingField` may not
   currently carry — worth checking before sizing that work.
2. **Log triage** — 5 rows: the level filter, the colourising, the hidden
   count, the line-count selector and the scroll-to-bottom. The log tail
   migrated as text; the tools for reading it did not.
3. **Version and identity** — 2 rows: "Last updated" and "UI vN · Bot vN".
   `GET /health` already serves both and `ApiClient.health()` already exists;
   this is the same fetched-but-unrendered pattern as SR42's detail fields, and
   SR48 bumps the very number that is not displayed.
4. **Login** — 2 rows: the `next` redirect and required-field validation.
5. **Single rows** — the font-zoom control, the field-count badge, the
   export/import asymmetry note, the `.env` file upload, and the HTML in the
   one field help that carries markup.
