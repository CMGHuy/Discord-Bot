# v210 — Market-shock notices and admin badge (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch, ui patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md) (§ Units → *Discord notices*, *Admin*; § Track 1 tests → *Notice formatting*, *Frontend*; § What changes → *Plans* puts these two units in this plan, after plan v209)
**Brief:** `.superpowers/briefs/2026-11-05-v209-market-shock-detector.md` (§3.8 queue, §3.9–3.10 tape, §4 test patterns, D1, D8)
**Prerequisite:** plan v209 (the detector, its tables, `MarketShockRepository`, the `shock_scan.py` pass, the scan wiring and the `entry_context` stamp) **merged and released** before this plan's worktree is cut. Every `V209-*` id in this plan names a task of that merged plan; this plan only consumes its contracts.

## Goal

Plan v209 makes the bot *measure* a market shock: every scheduled scan in
NYSE regular hours stores a reading and steps a NORMAL → SHOCK → RECOVERY →
NORMAL state in shadow mode. On its own that state is visible only in two
database tables and in each new plan's `entry_context`. On 2026-11-05 the
partner learned about the turn from the losses, not from the bot; the spec
asked for the state to be **seen while it happens**: a notice in the ops
channel the moment the market turns, listing every open long with its last
price, open R and whether it is already through its stop, and a badge on the
admin tape that says which state the market is in. This plan builds those two
surfaces. It was carved out of v209 (old tasks V209-9..V209-11) when v209 went
over the 20-task cap.

Once it ships, a stepped pass that changes the label hands the repository's
one-transaction `record()` a `market_shock` event for the v197 notify queue,
the third kind beside `trade_closed` and `plan_transition`. Any transition
**into** SHOCK (from NORMAL, or a RECOVERY → SHOCK second leg) is always
sent and lists the open longs with the footer that says the bot moved and
closed nothing; other transitions are rate-limited to one per
`SHOCK_MIN_DWELL_MIN`. The delivery worker posts it as a plain status embed,
never an alert embed. `GET /api/v1/market/tape` gains a `shock` object and
the shell tape shows a NORMAL / SHOCK / RECOVERY badge (with `VIX missing`
when the VIX row is stale), beside the tape on desktop and on its own line
under it on tablet.

It leaves alone: every trade decision (still shadow: no long blocked, no
short issued, no stop moved), the detector, its thresholds and tables, the
two existing queue kinds, alert embeds, the shell layout, and Track 2's
screens. Success is measured by tests and by production, not by ExpR
(`Edge: none (integrity)`): the notice copy, the rate limit, the second-leg
exception and the open-long lines are pinned by unit tests; a failing notice
build never costs the reading; under `off` there is no notice and
`shock: null`; after the deploy a notice builds and renders from production's
stored state without being sent, and the badge renders at 820 and 1440 px.

## Architecture

- **Renderer** (V210-1): new `swingbot/core/scanning/shock_notices.py` (pure)
  turns an event's payload into one `ui.PushEmbed` — headline, numbers line,
  one line per open long, the footer copy — stripe by label from existing
  `kinds` colour constants; no new `Kind`.
- **Queue kind** (V210-1b): `lifecycle_events.KINDS` gains `"market_shock"`
  with its own payload validator; `lifecycle_notifications.build_lifecycle_notification`
  dispatches the kind to the renderer. The two existing kinds are untouched.
- **Payload helpers** (V210-2): pure `open_long_rows`, `should_notify`,
  `notice_payload`, `notice_event` appended to `shock_notices.py`.
- **Stepped-pass hook** (V210-2b): `shock_scan._stepped_pass` (v209) asks
  `_notice_for(...)` for the event and passes it to `repo.record(...,
  notice_event=)`, so reading, state and notice commit together; a failure to
  *build* the notice is swallowed and logged (`scan.shock.notice`).
- **Admin API** (V210-3): `swingbot/admin/api_v1/market.py` `tape()` carries
  `shock` from the repository's current state and latest reading.
- **SPA badge** (V210-3b): `TapeShock` model, `TapeFeed.shock` signal, a
  `.shock-badge` sibling of the tape lane in `shell/tape/`.
- **Release** (V210-4): bot patch + ui patch, deploy, read-only production
  checks of the notice path and the badge.
- **Close-out** (V210-5): `/panel` with three roles, then `/close-out` without
  a second bump.

**Tech stack:** Python 3.11, discord.py, SQLAlchemy + psycopg 3, Flask,
pytest; Angular standalone components + signals, Vitest via
`frontend/scripts/ng-test.mjs`.

## Global Constraints

- **No trade changes.** `shadow` and `live` behave identically. No notice, badge or helper in this plan blocks a long, issues a short, moves a stop or alters a plan.
- **`MARKET_SHOCK_MODE=off` is a byte-identical kill switch:** no reading (v209), therefore no notice; `GET /api/v1/market/tape` returns `"shock": null` (also for an unknown mode value, before the first state row, or when the store cannot be read).
- **Labels** are exactly `"NORMAL"`, `"SHOCK"`, `"RECOVERY"` (`shock.LABELS`, v209). A notice is sent only on a label change (`label != prior_label`).
- **Notice copy, exact.** Footer line on entry into SHOCK and on a second leg: `The bot moved no stop and closed nothing. Stop move-up and long block are pending screen (v209 Track 2).` Through-stop marker: `THROUGH STOP`. Otherwise: `stop at broker untouched: <stop:.2f>`. Unknown last price: `last n/a` and `stop status unknown: <stop:.2f>`. Zero open longs: `No open longs.`
- **Notice layout.** Headline `Market state: <prior> → <new>`; numbers line `breadth <pct>% · sectors <down>/<total> · speed <+pp> · SPY <x:+.2f> ATR · QQQ <x:+.2f> ATR · VIX <lvl:.2f> (<chg:+.1f>%)`, `n/a` for any `None`; one line per open long `<TICKER> · entry <e:.2f> · stop <s:.2f> · last <l:.2f> · <r:+.2f>R · <age> · <marker>`, age `<h>h<mm>m` (or `<m>m` under an hour). Open-long lines stop at a 3,500-character budget, the rest collapse into `+<n> more open longs` (Discord's 4096 cap).
- **Open longs** come from `singletons.trade_log.get_trades(status="open", limit=None)`, `direction == "bullish"` only, last price from the pass's `live_prices`; `open_r = (last − entry) / (entry − stop)`; `through_stop = last <= stop`. They are read only on an entry into SHOCK. A trade log that cannot be read ⇒ `open_longs: []` plus `open_longs_unavailable: true`, and the notice says so instead of `No open longs.`
- **Rate limit:** at most one `market_shock` notice per `SHOCK_MIN_DWELL_MIN` (from `market_shock_state.last_notice_at`), except any transition **into** SHOCK, which is always sent. A dropped notice is not deferred.
- **Routing:** `target_channel_id = config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID or None`, computed in the worker thread (never `bot.get_channel` there). A notice is a plain status embed, never an alert embed, never carries the alert disclaimer.
- **One transaction.** The notice event goes through `repo.record(..., notice_event=)` (v209's V209-5b), so reading, state and event commit together; a failing *enqueue* rolls the pass back. A failure to *build* the notice is swallowed (`scan.shock.notice`) and the reading is recorded without an event.
- **The two existing queue kinds are untouched** (`trade_closed`, `plan_transition`): their validators, renderers and tests do not change.
- **Tape `shock` object, exact keys:** `{"label", "since", "as_of", "breadth_pct", "sectors_down", "sectors_total", "spy_atr_move", "qqq_atr_move", "vix_level", "vix_chg_pct", "vix_missing": bool}`; `breadth_pct = round(breadth_frac * 100, 1)`; `as_of` is the last reading's; `vix_missing = vix_level is None`. Both returns of `tape()` carry the key. The admin never steps the detector.
- **Badge:** copy `NORMAL` / `SHOCK` / `RECOVERY`, and `VIX missing` when `vix_missing`; element `.shock-badge[data-label]`, a sibling of the tape lane; it never truncates the tape. Checked at 390, 820 and 1440 px: to the tape's right at ≥ 1024 px, on its own line under the tape at 640–1023 px. Below 640 px the shell hides the whole tape strip (see OPEN).
- Every function written or changed < 15 cyclomatic complexity (`python scripts/dev/complexity_gate.py`); no legacy function's CC rises.
- Narrow test runs only: backend `python scripts/dev/testrun.py file <test>`; frontend `node frontend/scripts/ng-test.mjs frontend --include <spec>`. **No task runs the full suite**; CI does after the push. A task whose tests reach Postgres runs `/replicate-prod-db` first (one shared `swing-db` container, port 56789, `.env` credentials never printed). Every new test file sits in an existing `tests/` directory, so `tests/suites.toml` is unchanged.
- `.env` values are read, never printed; production is reached only through `bash scripts/ops/ssh-hetzner.sh`.
- Commit steps of V210-1..V210-3b run on the plan's worktree branch, never on `main`; V210-4 and V210-5 run on `main` after the merge.

## OPEN (for the partner, not decided)

- **No badge on phones.** The shell hides the whole tape strip below 640 px (`frontend/src/app/shell/shell.css`, `.tape-strip { display: none; }`), so the badge, which lives in the tape component, is not shown at 390 px. V210-3b leaves the shell alone and documents this; showing the state on phones (e.g. a chip in the mobile header) would be a shell change outside the spec. The partner decides whether that is wanted and, if so, in which plan.

## Review Focus

1. **Second-leg notice.** RECOVERY → SHOCK inside the rate-limit window still enqueues and lists open longs. Owner: V210-2 (`should_notify`), V210-2b.
2. **Notice build failure.** An exception while reading the trade log or building the payload never costs the reading or the state. Owner: V210-2b.
3. **Trade log unreadable vs. empty.** `open_longs_unavailable: true` renders a different line from `No open longs.` Owner: V210-1, V210-2b.
4. **Many open longs.** 60 open longs never push the description past 4096 characters. Owner: V210-1.
5. **Stale VIX / `off`.** `vix_missing` shows on the badge; under `off` the API returns `shock: null` and the badge is absent. Owner: V210-3, V210-3b.

## Parallelisation

| Group | Tasks | Files | Why sequential inside |
|---|---|---|---|
| E notices | V210-1 → V210-1b → V210-2 → V210-2b | `shock_notices.py` (1 creates, 2 extends), `lifecycle_events.py`, `lifecycle_notifications.py` (1b), `shock_scan.py` (2b), `tests/scanning/test_shock_notice_*.py`, `tests/infra/test_lifecycle_events_market_shock.py`, `tests/scanning/test_shock_pass*.py` | 1b dispatches to 1's renderer and appends to 1's test file; 2 calls `make_event` with 1b's kind; 2b calls 2's helpers |
| F admin | V210-3 → V210-3b | `admin/api_v1/market.py`, `tests/admin/test_api_v1_tape_shock.py`, `frontend/src/app/{api/models.ts,stores/tape-feed.ts,shell/tape/*}` | 3b renders 3's API field. Shares no file with E: may run beside it |
| H release | V210-4 | `docs/deploy/DEPLOY_HETZNER.md`, `VERSION.json`, `swingbot/admin/version_history.json` | needs E and F merged on `main` and CI green |
| I close-out | V210-5 | plan files (moved) | needs V210-4 deployed and its checks done |

Groups E and F need only plan v209 merged. Track 2's plan (the next free
number when written) shares no file with this plan.

## Task ledger

| Id | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V210-1 | `shock_notices.py` renderer — the `market_shock` status embed | 1 | sonnet | C `swingbot/core/scanning/shock_notices.py` (renderer half); C `tests/scanning/test_shock_notice_render.py` | `shock_notices.FOOTER` (exact copy in Global Constraints), `THROUGH_STOP = "THROUGH STOP"`, `NO_LONGS = "No open longs."`, `LONGS_UNAVAILABLE`; `long_line(row: dict) -> str` where `row = {"ticker", "entry", "stop", "last" (float \| None), "open_r" (float \| None), "age_min" (int), "through_stop" (bool)}`; `numbers_line(reading: dict) -> str`; `headline(payload: dict) -> str`; `build_shock_embed(event: dict) -> discord.Embed` reading `event["event_id"]` and `event["payload"]` |
| V210-1b | `market_shock` queue kind — validator and delivery dispatch | 1 | sonnet | M `swingbot/core/infra/lifecycle_events.py`; M `swingbot/core/scanning/lifecycle_notifications.py` (one dispatch branch in `build_lifecycle_notification`); C `tests/infra/test_lifecycle_events_market_shock.py`; M `tests/scanning/test_shock_notice_render.py` (three delivery tests) | `lifecycle_events.KINDS = ("trade_closed", "plan_transition", "market_shock")`; `_validate_shock_payload(payload) -> None`: `label`, `prior_label` in `shock.LABELS` and different, aware ISO `occurred_at`, dict `reading` (a `ShockReading.as_row()`), list `open_longs`, optional bool `open_longs_unavailable`, bool `entry_into_shock == (label == "SHOCK")`; `make_event(kind="market_shock", ...)` validates it; `build_lifecycle_notification` / `send_lifecycle_notification` render and post it |
| V210-2 | Notice payload helpers — open longs, rate limit, queue event | 1 | sonnet | M `swingbot/core/scanning/shock_notices.py` (payload half); C `tests/scanning/test_shock_notice_payload.py` | `open_long_rows(trades: list[dict], last_prices: Mapping[str, float], now: datetime) -> list[dict]` (bullish, positive `entry`/`stop_loss`, sorted by ticker); `should_notify(prior_label: str, new_label: str, last_notice_at: datetime \| None, now: datetime, min_dwell_min: int) -> bool`; `notice_payload(prior: ShockState, new: ShockState, reading: ShockReading, open_longs: list[dict], now: datetime) -> dict` (may carry optional bool `open_longs_unavailable`); `notice_event(payload: dict, *, as_of: datetime) -> dict` = `make_event(transition_id=f"market_shock:{as_of.isoformat()}", kind="market_shock", target_channel_id=config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID or None, occurred_at=payload["occurred_at"], payload=payload)` |
| V210-2b | Enqueue the notice from the stepped pass | 1 | sonnet | M `swingbot/core/scanning/shock_scan.py` (`_stepped_pass` passes `notice_event`; new `_open_trades`, `_open_longs`, `_notice_for`, `_safe_notice`); C `tests/scanning/test_shock_pass_notice.py`; M `tests/scanning/test_shock_pass.py` (one stub line in the autouse `_env` fixture) | `shock_scan._open_trades() -> list[dict] \| None` (`None` when the trade log cannot be read); a stepped pass that changes the label hands v209's `repo.record(..., notice_event=)` the event the V210-2 rules allow |
| V210-3 | Admin tape `shock` object (API) | 1 | sonnet | M `swingbot/admin/api_v1/market.py` (`_iso()`, `_shock_fields()`, `_shock_block()`, `"shock"` in both returns of `tape()`); C `tests/admin/test_api_v1_tape_shock.py` | `GET /api/v1/market/tape` → `"shock": null` under `off`/unknown mode, before the first state row, or when the store cannot be read; else the object with the exact keys in Global Constraints |
| V210-3b | SPA market-shock badge beside the tape, at three widths | 2 | sonnet | M `frontend/src/app/api/models.ts`; M `frontend/src/app/stores/tape-feed.ts` + `tape-feed.spec.ts`; M `frontend/src/app/shell/tape/tape.ts`, `tape.css`, `tape.spec.ts` | `type ShockLabel = 'NORMAL' \| 'SHOCK' \| 'RECOVERY'`; `interface TapeShock` (V210-3's keys); `TapeResponse.shock?: TapeShock \| null`; `TapeFeed.shock: Signal<TapeShock \| null>`; `shockSummary(s: TapeShock): string` in `tape.ts`; badge `.shock-badge[data-label]` |
| V210-4 | Release: bot patch + ui patch, deploy, shadow checks for the notice path and the badge | 2 | sonnet | M `docs/deploy/DEPLOY_HETZNER.md` (one `v210` paragraph at the end of v209's `### v209: market shock tables` section); M `VERSION.json`; M `swingbot/admin/version_history.json` | release commit `release(bot,ui): bot <B> / ui <U> -- market-shock notice and tape badge (v210)` and its `chore(bot,ui)` regeneration commit, which V210-5 detects to skip a second bump; read-only production checks: `MARKET_SHOCK_MODE=shadow` still set, a notice built and rendered from stored state without enqueueing, queue rows delivered, tape `shock` object and badge at 1440/820 px; `/mirror-prod` for any production change |
| V210-5 | `/panel` (veteran-trader, senior-engineer, financial-advisor) + `/close-out` without a second bump | 2 | sonnet | M (moved by `/close-out`) the three v210 plan files (index + parts 1, 2) `docs/superpowers/plans/2026-11-06-v210-market-shock-notices-and-badge_*.md` → `docs/superpowers/plans/implemented/`; the v209 spec stays in `specs/` (the Track 2 plan closes it); `VERSION.json` and `version_history.json` **not** modified | none (last task). Double-bump guard: before `/close-out` Step 3, run `git log --oneline -- VERSION.json` and confirm V210-4's `release(bot,ui): ... (v210)` commit is present and `VERSION.json` holds that pair or later; if so, tell the close-out the bump is already released (Steps 3–4 skipped, Step 5's prediction check still runs) and record `bump released in V210-4 (<sha>)` in the close-out commit message. If the release commit is missing, stop and report — never bump here |

8 ledger rows (`b` rows included).

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-06-v210-market-shock-notices-and-badge_1-notices.md` | V210-1, V210-1b, V210-2, V210-2b, V210-3 | `market_shock` renderer, queue kind, payload helpers, stepped-pass hook; tape API `shock` object |
| 2 | `2026-11-06-v210-market-shock-notices-and-badge_2-admin-badge.md` | V210-3b, V210-4, V210-5 | SPA badge at three widths; release (bot patch, ui patch) with read-only production checks; `/panel` + `/close-out` |
