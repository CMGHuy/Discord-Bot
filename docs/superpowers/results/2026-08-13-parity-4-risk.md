# Jinja → SPA parity audit, group 4: Risk, Tuning and Watchlist

Task SR44 of `2026-08-13-v21-spa-refresh.md`. Templates audited: `risk.html`,
`tuning.html`, `watchlist.html`, together with their routes
(`app.py:risk_page`/`risk_killswitch`/`watchlist_*`, `pages.py:tuning_page`/
`tuning_propose`/`tuning_proposal_delete`/`_list_proposals`/`_grid_row_passes`).

Three statuses only — `migrated`, `dropped on purpose`, `missing`. Nothing is
left unclassified.

**Two of these three are the cleanest migrations in the audit and one has a
hole in the middle of its workflow.** Risk and Watchlist came across whole and
gained things. Tuning kept the launcher, the job log and the proposal list, but
lost the grid-results table — and with it the **Propose** button, which was the
only way a proposal was ever created. You can start a grid search in the SPA
and you can delete proposals in the SPA; there is no way to get from one to the
other.

---

## `risk.html` — the portfolio risk panel

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Kill-switch engaged banner at the top of the page | `risk.html:16-25` | migrated | Shell-level: `KILLSWITCH ENGAGED` in the topbar (`shell.html:72-74`), true in every workspace, plus the Killswitch panel |
| That banner's reason | `:21` | migrated | `killswitchDetail()`, `risk.ts:79-81` |
| "Release is manual and never clears itself" | `:22` | migrated | The Killswitch panel's `kill-explain` copy (`risk.ts:71`) |
| Portfolio heat: open heat % | `:35-36` | migrated | `store.openHeatPct()`, `risk.ts:127-129` |
| Portfolio heat: cap % | `:37` | migrated | "of N% cap", `risk.ts:130` |
| Portfolio heat: utilisation % | `:38-39` | migrated | `store.heatUtilisationPct()` on the meter |
| Utilisation bar, clamped at 100%, colour by band | `:40-45` | migrated | `role="meter"` track; only the width is clamped, so an over-cap figure still reads correctly (`risk.ts:137-155`) |
| "At or above the cap, new entries are blocked" | `:50-53` | migrated | `heatNote()` |
| Sector heat table, sorted by exposure | `:56-77` | migrated | Sector heat panel, `risk.ts:193-204` |
| Sector heat bars | `:67-72` | migrated | Same panel |
| Sector heat empty state | `:79` | migrated | "No sector exposure." |
| Correlated clusters table | `:83-96` | migrated | Clusters panel, `risk.ts:208-223` |
| "Positions in one cluster tend to lose together" | `:97-100` | **missing** | — the panel lists the clusters without saying why they matter |
| Clusters empty state | `:102` | migrated | "No correlated clusters among open positions." |
| Drawdown throttle: risk multiplier ×N | `:108-113` | migrated | "Drawdown throttle at ×N", `risk.ts:169-171` |
| Drawdown throttle: PAUSED / Throttled / Normal | `:115-121` | migrated | The three states, `risk.ts:162-175` |
| "Derived from the account's own equity curve…" | `:125-129` | **missing** | — the same kind of gap as the clusters note |
| Kill switch: status, reason, action | `:140-166` | migrated | Killswitch panel |
| Kill-switch engage with a confirm prompt | `:158-161` | migrated | `sb-confirm-dialog` in the workspace |
| Kill-switch release | `:153-155` | migrated | Same panel, the two states of one control |
| "A hard stop on new entries; open positions keep being monitored" | `:134-138` | migrated | `kill-explain` |
| Scan health: slowdown warning ("more than 2x the median of the prior 20") | `:171-176` | migrated | `store.scanSlowdown()`, `risk.ts:242-246` |
| Scan health: duration sparkline, last 50 scans | `:177-182` | migrated | `sb-sparkline` labelled "Recent scan durations, in seconds" |
| Scan health: latest duration in seconds | `:180-182` | migrated | Same panel |
| Scan health empty state | `:184` | migrated | Same panel |
| Exposure by position (per-position table) | — | n/a | New in the SPA (`risk.ts:181-190`) |

Risk is the one page that came across essentially intact. The two `missing`
rows are both explanatory sentences.

---

## `watchlist.html` — the watchlist

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Add one ticker | `watchlist.html:5-12` | migrated | The single Add input, `watchlist.ts:52-98` |
| Bulk add / restore, behind a disclosure | `:14-34` | migrated | Folded into the same input — "AAPL, or paste a list" (`watchlist.ts:62`). One control instead of two |
| "Already-present tickers are skipped safely, nothing is removed" | `:22-26` | migrated (narrowed) | `store.addResult()` reports what happened afterwards rather than promising it beforehand |
| Ticker autocomplete, debounced, stale-response guarded | `:94-150` | migrated | `store.suggestions()`, `watchlist.ts:66-85` |
| Autocomplete shows the company name | `:116` | migrated | `hit-name` |
| "already watched" marker on a suggestion | — | n/a | New in the SPA (`watchlist.ts:75-80`) |
| Ticker count in the card title | `:39-42` | migrated | The header's "N watched" |
| "changes take effect on the next !check or scheduled scan" | `:41-42` | **missing** | — nothing says when an add or remove takes effect |
| Column: row number | `:49, 58` | dropped on purpose | Same decision as the trades tables — an ordinal that moves with the sort is not information |
| Column: Ticker | `:50, 59` | migrated | `symbol`, a link into the ticker detail view |
| Column: Company | `:51, 60` | migrated | `company_name` |
| Column: Open trades | `:52, 61-67` | migrated | `open_trades` |
| Column: Closed trades | `:53, 68` | migrated | `closed_trades` |
| Remove, with a confirm prompt | `:69-75` | migrated | Remove button + `sb-confirm-dialog` (`watchlist.ts:128, 141`) |
| Empty state | `:81` | migrated | `data-table` empty state |
| Tip: Yahoo Finance symbol format (`ASML.AS`, `BTC-USD`, `^GSPC`) | `:85-92` | **missing** | — the one piece of copy on this page that prevents a failed add, and the format is not guessable |

---

## `tuning.html` — the parameter workbench

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Section help: what tuning is, the TRAIN/VALIDATION firewall, the pass bar | `tuning.html:4-12` | migrated (narrowed) | The launcher's `note` keeps the firewall paragraph (`analytics.ts:267-273`); the acceptance bar (WR ≥80%, positive expectancy, N ≥30) is not stated anywhere |
| "Current parameters" table: Strategy | `:23, 28` | migrated | Strategy registry table, Strategies tab |
| Current parameters: Badge | `:29` | migrated | Registry `status` |
| Current parameters: R:R | `:30` | migrated | Registry `rr_override` |
| Current parameters: Gate | `:31` | migrated | Registry `gate_description` |
| Current parameters: **Default params** | `:32-34` | **missing** | — `default_params` appears nowhere in `frontend/src`; the tab proposes changes to values it never shows |
| Current parameters: Window | `:35` | migrated | Registry `window` |
| Current parameters: Run date | `:36` | migrated | Registry `run_date` |
| "Values are code, changed only via reviewed commits" | `:17-19` | migrated | The Proposals panel's note says the same thing more concretely (`analytics.ts:337-341`) |
| TRAIN window dates, printed | `:75-78` | **missing** | — the SPA says no date input exists but never says which window is in force |
| Strategy select | `:80-88` | migrated | `sb-select`, `analytics.ts:282-287` |
| Launch TRAIN grid | `:89` | migrated | `analytics.ts:288-297` |
| Launch status / error, incl. the 409 "busy" case | `:90, 105-106` | migrated | `store.launchError()` + the `jobActive()` branch, which hides the launcher entirely |
| Job progress card with state pill | `:47-52` | migrated | `sb-chip [label]="jobStateLabel(job)"`, `analytics.ts:306-310` |
| Job log tail | `:51, 60` | migrated | `<pre class="log">`, `analytics.ts:311` |
| 3-second polling of `/api/jobs/<id>` | `:56-71` | dropped on purpose | Replaced by the `jobs` SSE event, stated in the panel itself (`analytics.ts:312-315`) |
| Full-page reload when the job ends | `:66, 107` | dropped on purpose | The log stays put and the launcher returns on its own |
| **Grid results table** — one row per parameter combination | `:114-155` | **missing** | — no results view of any kind. The job's stdout is shown; the parsed grid is not |
| Results column: Params | `:123, 135-137` | **missing** | — |
| Results column: N | `:124, 138` | **missing** | — |
| Results column: Win rate | `:125, 139` | **missing** | — |
| Results column: ExpR | `:126, 140` | **missing** | — |
| Results column: Excl% | `:127, 141` | **missing** | — |
| Results column: Pass, with the row highlighted | `:128, 134, 142` | **missing** | — |
| **Propose** — stage a passing row as a proposal | `:143-149`, `pages.py:tuning_propose` | **missing** | — the endpoint exists; nothing in `frontend/src` calls it. This is the break in the workflow: proposals can be listed and deleted but never created |
| Recent jobs list | `:157-172` | migrated | "Earlier jobs", `analytics.ts:319-334` |
| "view results" link per finished job | `:168` | **missing** | — follows from the results table being absent |
| Proposals: strategy, created-at, job id | `:181-186` | migrated | `analytics.ts:347-354` |
| Proposals: current-vs-proposed diff table | `:187-198` | migrated | `analytics.ts:355-368` |
| Proposals: TRAIN stats line (N / WR / ExpR) | `:199-203` | migrated | `proposal.trainSummary`, `analytics.ts:369` |
| Proposals: delete, with a confirm prompt | `:204-207` | migrated | Delete button + `sb-confirm-dialog` |
| Proposals empty state | `:179` | migrated | "No proposals yet." |
| Seven `?` tip icons | throughout | dropped on purpose | Where the feature migrated, the panel notes carry the explanation; where it did not, there is nothing to annotate |

---

## Tally for this group

| Status | Count |
|---|---|
| migrated (incl. narrowed) | 48 |
| dropped on purpose | 5 |
| **missing** | 13 |
| new in the SPA (not a parity row) | 3 |

The `missing` rows split three ways:

1. **The tuning workflow's missing middle** — 9 rows, all one feature: the grid
   results table and its Propose action. `POST /tuning/propose` still exists
   server-side (`pages.py:435-479`), and the job writes its result file, so this
   is a view over data that is already produced. Without it the Tuning tab can
   start work and file work away but cannot act on what a run found, which
   makes the Proposals panel below it unreachable by any normal route.
2. **Default params and the TRAIN window** — 2 rows. The tab proposes changes
   to parameter values it never displays, and never names the window it ran
   against.
3. **Explanatory copy** — the two risk notes and the watchlist's Yahoo-format
   tip. The last of these is the one worth arguing for: an add that fails
   because the symbol format is wrong gives no hint what the right format was.
