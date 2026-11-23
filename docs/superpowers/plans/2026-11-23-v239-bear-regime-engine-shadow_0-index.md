# v239 — Bear-regime engine (shadow): Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V239-7" -A 400 <part file>`); never read a part whole.

**Bump:** bot minor, ui minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-23-v239-bear-regime-engine-shadow-design.md](../specs/2026-11-23-v239-bear-regime-engine-shadow-design.md) — its `## Code reconciliation` section overrides the text above it.
**Brief:** `.superpowers/briefs/2026-11-23-v239-bear-regime-engine-shadow.md`

## Goal

In the week of 11-16 the live book closed 74 longs at WR 14.9% and
ExpR −0.39R while SPY fell 8.6% and closed under its SMA200. The bot has
two market signals: the slow EMA200 regime, which only feeds confidence, and
the v209 shock detector, which watches for intraday breadth crashes. Neither
of them noticed a grinding decline: 73 of the 74 losing longs were stamped
`shock_state = NORMAL`. The partner wants two things. The bot should know
when the market is in a bear phase or a sharp downtrend, and it should tell
a dip that will be bought from a decline that keeps going. The repo's rules
say a live long veto needs a screen pass first, so this plan builds the
missing daily trend layer and runs it **in shadow**. It labels, shows and
records. It never acts.

Once this ships, every scan pass labels the coming NYSE session from
completed daily SPY and ^VIX bars. The label is `BEAR` (the long trend has
turned), `CORRECTION` (a dip while the long trend still rises), `NORMAL` or
`UNKNOWN`, plus a VIX `stress` flag and a `pullback_trigger` for the day the
panic eases inside a correction. One row per session is written once to
`market_regime_days`. Every new plan's `entry_context` gains `bear_regime`
and `regime_action` (what the engine *would* do: `would_veto`, `caution`,
`pullback_watch`, `aligned`, `none`). Every alert carries a one-line regime
note under its plan table. A confirmed state change posts one notice to the
ops channel, listing the resting bullish entries. bomeo-capital.com shows a
"Trend:" banner in the app shell and a regime chip on trade and plan detail.
A shadow report compares live would-veto longs with the rest. A base-rate
study measures, on SPY back to 1993, how often a CORRECTION became a BEAR and
how SPY behaved afterwards.

What it leaves alone: no plan is blocked, sized, scored, re-ordered,
cancelled or created. `regime.py`, `score_confidence` and the v209 machine
are untouched, and so is the execution ticket's own body. The classifier
constants live in code as `Final`s, never `.env`. `BEAR_REGIME_MODE=off` is a
byte-identical kill switch: no fetch, no row, no stamp, no line, no notice,
no banner. Success has four parts. The classifier replays this week as the
spec states (CORRECTION from `D = 10-22`, stress on `D = 11-17..11-20`,
never BEAR). The `off` arm is byte-identical in `entry_context`, in both
embed builders and in DB writes. The banner and chip pass the layout audit
at 390/768/1440. The base-rate results doc is committed with its hashes.
Each live action (B9 veto, B8 pullback long, B7 bear short) still waits for
its own screen row.

## Architecture

- **Pure core (`swingbot/core/market/`).** `bear_regime.py` holds the
  constants, `RegimeDay`, `classify` (frames already cut to session `s`;
  it truncates again defensively) and `shadow_action`. `regime_episodes.py`
  holds confirmed episodes (a run of two labelled sessions; flicker merges
  into its neighbour) and `confirmed_transition`. The live pass, the API's
  "since" count and the 1993 study all share it.
- **Live calendar (`swingbot/core/scanning/regime_calendar.py`).**
  `session_pair(now) -> (s, D)` uses the half-day-aware `session` helpers
  (`last_regular_close`, `nyse_calendar().next_session`). `cut_completed(df,
  now)` applies `strategy_pass.completed_frame` and then drops every bar
  dated after `s`, which covers the early close as well.
- **Vocabulary (`swingbot/core/presentation/regime_text.py`).** One label
  table, one plain-words table, one number form (`SPY −5.7% vs SMA200 ·
  −9.3% vs SMA50 · VIX 37.6`, U+2212 via `tokens.fmt_pct`) and the alert line
  per state × action. The notice, the embeds and the API all render through
  it. No glyphs.
- **Storage.** Alembic `v239_001` creates `market_regime_days` (PK
  `session_date`, plus the standard `doc` / `updated_at` columns).
  `MarketRegimeRepository.insert_once` runs `INSERT … ON CONFLICT DO NOTHING
  RETURNING` and enqueues the notice in the same transaction only when a row
  came back.
- **Pass (`swingbot/core/scanning/regime_scan.py`).** `regime_for_pass()`
  returns None in `off` mode without reading anything. Otherwise it reads the
  row for `D`. If there is none, it fetches SPY and ^VIX through
  `get_daily_data` (^VIX is yfinance-only, SPY Alpaca-first), cuts, classifies
  and decides on a notice (`regime_notices`), then inserts once. It never
  raises: failures are swallowed and logged, and the pass then returns None.
  `scan_run._sync_run_scan` calls it once per pass, unconditionally, and
  `short_run._lane_state` once per lane run.
- **Stamp.** `regime_day` is threaded beside `shock_state`
  (`attach_plan_v2`, `QualifyContext`, `_attach_item_plan`, `_rebuild_item`,
  `_maybe_run_strategy_pass`'s `asof_of`). The asof fragment is
  `params.regime_asof(day)`. `stamp_entry_context` calls `_merge_regime`, which
  derives `regime_action` from `plan.direction`.
  `trade_why.WIRE_CONTEXT_KEYS` gains both keys.
- **Surfaces.** A `Trend` field (full alert line as value) goes on
  `build_embed` (in `sections["plan"]`), `build_simple_alert` (both branches),
  `build_strategy_alert_embed` (after Ledger), and in the
  `build_strategy_simple_embed` description. `GET /api/v1/market/regime` lives
  in a new `api_v1/market_regime.py`. In the SPA: `RegimeStore`, an
  `sb-regime-banner` in `shell.html` directly after the `.tape-strip` div, and
  an `sb-regime-chip` on the `.tags` rows of `trade-detail.ts` and
  `plan-detail.ts`.
- **Evidence.** `scripts/reports/regime_shadow_report.py` (live monitoring,
  never a screen), `scripts/reports/regime_parity.py` (stored rows vs a cache
  replay, with the boundary-day tolerance) and
  `scripts/research/regime_base_rates.py`, which reads a new
  `data/backtest_cache_regime/` (SPY and ^VIX, 1993-01-01 → 2026-11-20,
  hash-pinned).

**Tech stack:** Python 3.11, pandas/numpy, SQLAlchemy + Alembic (Postgres), discord.py embeds, Flask, Angular (signals, OnPush, vitest), Playwright layout audit.

## Decisions this index fixes (spec silent; controller may override)

1. **A stale-SPY `UNKNOWN` is not persisted.** Rows are write-once, so
   storing a data-lag label (for example a scan at 16:05 before the
   provider has the bar) would freeze it for the whole session.
   `regime_for_pass` returns that day for the pass, stamps it (`UNKNOWN`,
   action `none`) and skips the insert, so the next pass retries. `UNKNOWN`
   from short history or a NaN is persisted. The reason goes in
   `RegimeDay.unknown_reason` (`"short_history"` / `"nan"` / `"stale"`),
   stored in the row's `doc` JSONB.
2. **`last_bar_date` is the SPY frame's actual last bar date.** It equals
   `s` unless the frame is stale, so parity can say which input the row saw.
   The spec's single `provider` becomes `spy_provider` and `vix_provider`
   (reconciliation 1), taken from `df.attrs.get("source")`.
3. **Episode key** (`regime_episodes.episode_key`): `BEAR` (stress ignored,
   since the vocabulary has no "Bear · Stress"), `CORRECTION_STRESS`
   (`stress is True`), `CORRECTION`, `NORMAL`, `UNKNOWN`. A stress change
   inside a CORRECTION is a transition. A pullback day is notified on its
   own, without confirmation, and is not an episode key.
4. **First reading.** With no prior confirmed episode, a confirmed episode
   that is not `NORMAL` notifies with `old = None` (headline "Regime: first
   reading → Correction"). A first `NORMAL` episode stays silent.
5. **`today` in the API** is the stored row whose `session_date` equals the
   current `D` from `session_pair(now)`, else `null` (the banner is then
   hidden). The admin process never fetches market data.
6. **Unfilled bullish plans** in a notice are `PlanStore().open_plans()`
   with status `PENDING`, direction `bullish`, and an
   `entry_context.bear_regime` that is not the new state (a missing key counts
   as the old state). Each is listed as `ticker entry` within a 3500-character
   budget, followed by `… and N more`.
7. **Alert field name** is `Trend` (it matches the banner's "Trend:"
   prefix). The value is the full line from `regime_text.alert_line`, which is
   at most 80 characters.
8. **Inputs are fetched by the pass itself** (`get_daily_data(t,
   period="2y")`, about 500 bars), never the scan's cache-first `spy_df`, so
   `spy_provider` is truthful. That happens once per `D`, because later passes
   read the row.

## Global Constraints

- **Shadow only.** Nothing blocks, sizes, scores, re-orders, drops,
  cancels or creates a plan (spec § Non-goals). The alert line says what the
  engine *would* do and never gives an order instruction.
- **`off` is byte-identical:** no fetch, no `market_regime_days` read or
  write, no notice, no `entry_context` key, identical embed bytes for every
  builder, `/market/regime` returns `{mode:"off", today:null, history:[],
  episode:null}` without reading. An unknown mode value falls back to `off`.
  `live` behaves exactly like `shadow`.
- **No-lookahead** (`docs/claude/architecture.md`): every input is a
  completed daily bar dated `≤ s`. `classify` truncates to `last_session`
  itself, and a test appends a bar after `s` and asserts the label does not
  change. ^VIX is aligned by exact session date and never forward-filled.
- **Rules are raw and frozen.** No hysteresis on `state`. Constants are
  module `Final`s in `bear_regime.py` (`MIN_BARS = 220`, `SMA_FAST = 50`,
  `SMA_SLOW = 200`, `SLOW_SLOPE_LAG = 20`, `FAST_SLOPE_LAG = 5`,
  `STRESS_VIX = 25.0`, `PULLBACK_VIX_RATIO = 0.85`, `PULLBACK_VIX_WINDOW =
  5`). Changing one is a new idea under slate rows B7–B9, not a knob.
- **Vocabulary and number form** come only from `regime_text`, with no
  glyphs (⚠ etc.). Alert lines are ≤ 80 characters (`regime_text.MAX_LINE`).
  The chip's text prefixes `×` / `!` / `↺` are the spec's own and are the only
  exception.
- **`entry_context` is additive:** `bear_regime` and `regime_action` only,
  never upcast onto old records (`docs/claude/schema-evolution.md`).
- **Write once.** A stored row is never updated or rewritten, by a revised
  close or by a later pass. There is no backfill.
- **Complexity < 15** on every new or changed function. `_sync_run_scan`
  (F 94) and `build_embed` (E 33) get exactly one unconditional helper call
  each, with no new branch. `attach_plan_v2` (C 12) gets a kwarg and a dict
  splat, with no branch (`scripts/dev/complexity_gate.py`).
- **Hybrid-table contract:** `register()`, `PROMOTION_REASONS` (≤ 100
  characters each), `*standard_columns()`, an entry in
  `tests/db/test_unknown_field_round_trip.py`, and exactly one Alembic head
  (`down_revision` = `python -m alembic heads` at implementation time,
  `v228_001` when briefed).
- **Tests and suites.** New `tests/regime/` (created by V239-1) joins suite
  `market-signals` in `tests/suites.toml`. It holds every test that needs no
  DB, Flask or Angular: classifier, episodes, calendar, vocabulary, notices,
  pass, stamp, wiring, embeds, reports, parity and study. DB tests go in
  `tests/db/`, API tests in `tests/admin/test_api_v1_market_regime.py`, config
  in `tests/test_config_v239_keys.py`, lifecycle kinds in `tests/infra/`.
  Never add to `tests/scanning/` or `tests/scripts/` (near cap). Frontend
  specs are colocated `*.spec.ts`.
- **Verification is narrow:** `python scripts/dev/testrun.py file <test>`
  per task (frontend: `cd frontend && npx ng test --include <spec>`).
  **No task runs the full suite**, because CI does that after the push. A
  task whose tests reach Postgres runs `/replicate-prod-db` first, against
  the shared `swing-db` container.
- **UI:** every banner or chip change is checked at 390 / 768 / 1440. Touch
  targets are ≥ 44 px at ≤ 1023 px. Driving the browser is Playwright only.
  The `.env` admin credentials are loaded inside scripts and never printed.
- **Study reproducibility:** fixed end `2026-11-20`. The study refuses to run
  if a cache file's SHA-256 differs from its recorded value. It checkpoints
  per year and writes Markdown with `encoding="utf-8", newline="\n"`. It
  describes SPY and moves no gate.
- **Commits.** The implementer commits per task in the plan's worktree, in
  scoped commits. Plan writers do not commit tasks. Skill edits ship
  `python scripts/dev/sync_codex.py`, and `docs/claude/` edits ship the
  `AGENTS.md` mirror, in the same commit.

## Parallelisation

At most 2 implementers at once (session rule).

- **Lane A (pure core):** V239-1 → V239-2 (the replay fixture is cut from
  V239-1's cache) → V239-3 (imports `RegimeDay`, the state constants and
  `shadow_action`).
- **Independent starters:** V239-4 (calendar: `session` and
  `completed_frame` only), V239-5 (config and mode reader) and V239-6
  (schema, migration and repo: dict rows, no import from `bear_regime`) have
  disjoint files and no contract on lane A. They can run beside it.
- **V239-7** (notices) needs V239-2 and V239-3 (`RegimeDay`, `Transition`,
  `regime_text`).
- **V239-8** (pass) needs V239-2, 3, 4, 5, 6 and 7 (it calls all of them).
- **V239-9** (stamp) needs V239-2 (`RegimeDay`, `shadow_action`). It runs in
  parallel with V239-4..8 (disjoint files).
- **V239-10** (wiring) needs V239-8 (`regime_for_pass`) and V239-9
  (`regime_day` kwargs, `regime_asof`).
- **V239-11** (embeds) needs V239-3 (`alert_line`) only. It reads the stamped
  keys by name, so it runs in parallel with V239-8..10.
- **V239-12** (API) needs V239-3, 4, 5 and 6.
- **V239-13** (store, banner, shell) needs V239-12 (wire shape).
  **V239-14** (chip) needs V239-9 (the wire keys). V239-13 ∥ V239-14
  (disjoint files: neither touches the other's component, and only V239-13
  edits `models.ts` / `api-client.ts`).
- **V239-15** (layout audit) needs V239-13 and V239-14.
- **V239-16** (shadow report, parity) needs V239-2. V239-17 (study) needs
  V239-1, 2 and 3. V239-16 ∥ V239-17 (disjoint files).
- **V239-18** (docs, skills, guide) needs every other task (it cites final
  names).

## Task ledger

| ID | Title | Part | Model | Files (C create, M modify) | Symbols for later tasks |
|---|---|---|---|---|---|
| V239-1 | Study data fetch, `scripts/research/` and the `tests/regime/` suite | 1 | sonnet | C `scripts/data/fetch_regime_data.py`, C `scripts/research/README.md`, C `tests/regime/__init__.py`, C `tests/regime/test_fetch_regime_data.py`, M `tests/suites.toml` | `fetch_regime_data.CACHE_DIR = ROOT / "data/backtest_cache_regime"`; `START = "1993-01-01"`; `END = "2026-11-20"`; `SYMBOLS = ("SPY", "^VIX")`; `MANIFEST = "manifest.json"` (keys `symbols: {sym: {sha256, rows, first, last}}`, `command`, `fetched_at`); `sha256_file(path) -> str`; `write_manifest(cache_dir, frames, command) -> dict`; `main(argv=None) -> int` |
| V239-2 | Pure classifier, SPY side: `RegimeDay`, `ROW_COLUMNS`, `to_row`/`from_row`, state and UNKNOWN rules (`REASON_STALE`/`REASON_SHORT`/`REASON_NAN`) | 1 | opus | C `swingbot/core/market/bear_regime.py`, C `tests/regime/test_bear_regime_rules.py` | as written in part 1 (V239-2); the full signature contract below is completed by V239-2b |
| V239-2b | Classifier, VIX side: `stress`, `pullback_trigger`, `vix_gap`, `shadow_action`, replay fixture and replay test | 1b | opus | M `swingbot/core/market/bear_regime.py`, M `tests/regime/test_bear_regime_rules.py`, C `tests/regime/test_bear_regime_replay.py`, C `tests/fixtures/regime/spy_vix_replay.csv` | `classify(...)` VIX fields and `shadow_action(state, stress, pullback_trigger, direction) -> str` as in the index Global Constraints; V239-3, 7, 9, 17 depend on it |
| V239-3 | Confirmed episodes and the shared vocabulary | 1 | sonnet | C `swingbot/core/market/regime_episodes.py`, C `swingbot/core/presentation/regime_text.py`, C `tests/regime/test_regime_episodes.py`, C `tests/regime/test_regime_text.py` | `episode_key(state: str, stress: bool \| None) -> str` (`"BEAR"`, `"CORRECTION_STRESS"`, `"CORRECTION"`, `"NORMAL"`, `"UNKNOWN"`); `CONFIRM_SESSIONS = 2`; `@dataclass(frozen=True) Episode(key: str, start: date, end: date, sessions: int)`; `confirmed_episodes(days: Sequence[tuple[date, str]]) -> list[Episode]` (oldest first, flicker merged); `current_episode(days) -> Episode \| None`; `@dataclass(frozen=True) Transition(old: str \| None, new: str)`; `confirmed_transition(prior: Sequence[tuple[date, str]], new: tuple[date, str]) -> Transition \| None`. `regime_text`: `MAX_LINE = 80`; `LABELS: dict[str, str]` (keys = episode keys + `"PULLBACK"`); `WORDS: dict[str, str]`; `label_for(state, stress, pullback=False) -> str`; `words_for(state, stress, pullback=False) -> str`; `number_line(*, spy_close, sma50, sma200, vix_close) -> str \| None`; `display(day: RegimeDay) -> dict` (`{"label", "words", "numbers"}`); `alert_line(state: str \| None, action: str \| None) -> str \| None` |
| V239-4 | Live session pair and completed-bar cut (half-day aware) | 1 | opus | C `swingbot/core/scanning/regime_calendar.py`, C `tests/regime/test_regime_calendar.py` | `session_pair(now: datetime) -> tuple[date, date]` (`(s, D)`); `cut_completed(df: DataFrame, now: datetime) -> DataFrame`; `sessions_between(older: date, newer: date) -> int` (NYSE sessions after `older` up to and including `newer`) |
| V239-5 | `BEAR_REGIME_MODE` config field and mode reader | 2 | haiku | M `swingbot/config.py`, M `.env.example`, M `docs/deploy/DEPLOY_HETZNER.md`, C `swingbot/core/scanning/regime_scan.py`, C `tests/test_config_v239_keys.py` | `config.BEAR_REGIME_MODE` (select, section "Bear Regime", default `"shadow"`); `regime_scan.MODES = ("off", "shadow", "live")`; `regime_scan.regime_mode() -> str` |
| V239-6 | `market_regime_days` table, Alembic `v239_001`, insert-once repository | 2 | opus | M `swingbot/core/db/schema.py`, C `swingbot/core/db/migrations/versions/v239_001_market_regime.py`, C `swingbot/core/db/repositories/market_regime.py`, M `tests/db/test_unknown_field_round_trip.py`, C `tests/db/test_v239_market_regime_schema.py`, C `tests/db/test_market_regime_repository.py` | `schema.market_regime_days`; revision `"v239_001"`; `class MarketRegimeRepository(Repository)` (key `session_date`): `insert_once(row: dict, *, notice_event: dict \| None = None, conn=None) -> bool`, `day(session_date: date, *, conn=None) -> dict \| None`, `latest(*, before: date \| None = None, conn=None) -> dict \| None`, `recent(limit: int = 60, *, conn=None) -> list[dict]` (oldest first); `market_regime_repo() -> MarketRegimeRepository` |
| V239-7 | `bear_regime` notify kind and the transition notice | 2 | sonnet | M `swingbot/core/infra/lifecycle_events.py`, M `swingbot/core/scanning/lifecycle_notifications.py`, C `swingbot/core/scanning/regime_notices.py`, C `tests/infra/test_lifecycle_events_bear_regime.py`, C `tests/regime/test_regime_notices.py` | `lifecycle_events.KINDS` gains `"bear_regime"`; `regime_notices.KIND = "bear_regime"`; `FOOTER = "Shadow: no long blocked, no short issued, no plan cancelled."`; `GAP_NOTE_SESSIONS = 5`; `UNFILLED_BUDGET = 3500`; `unfilled_bullish_rows(plans: Iterable, *, new_state: str) -> list[dict]` (`{"ticker", "entry"}`); `notice_payload(day: RegimeDay, transition: Transition \| None, *, open_longs: int, unfilled: list[dict], gap_sessions: int \| None, now: datetime) -> dict` (keys `occurred_at`, `session_date`, `kind` `"transition"`/`"pullback"`, `old_label`, `new_label`, `numbers`, `open_longs`, `unfilled`, `gap_sessions`); `notice_event(payload: dict, *, session_date: date) -> dict` (`transition_id=f"market_regime:{session_date}"`); `build_regime_embed(event: dict) -> discord.Embed` |
| V239-8 | Regime pass: compute-or-read `D`, insert once, notice from the winner | 2 | opus | M `swingbot/core/scanning/regime_scan.py`, C `tests/regime/test_regime_pass.py` | `regime_for_pass(*, now: datetime \| None = None, repo=None, fetch: Callable[[str], DataFrame] \| None = None, plans=None, trades=None) -> RegimeDay \| None` (never raises; `None` when off or on failure) |
| V239-9 | Stamp `bear_regime` / `regime_action`; thread `regime_day`; wire keys | 3 | opus | M `swingbot/core/planning/params.py`, M `swingbot/core/scanning/analyze.py`, M `swingbot/core/scanning/qualify.py`, M `swingbot/admin/trade_why.py`, M `tests/admin/test_api_v1_trade_detail.py`, C `tests/regime/test_regime_stamp.py` | `params.regime_asof(day: RegimeDay \| None) -> dict` (`{}` or `{"bear_regime_day": day}`); `params._merge_regime(plan, asof) -> None`; `attach_plan_v2(..., shock_state=None, regime_day=None)`; `QualifyContext.regime_day: RegimeDay \| None = None`; `trade_why.WIRE_CONTEXT_KEYS` gains `"bear_regime"`, `"regime_action"` |
| V239-10 | Scan wiring on every lane, and the `off` byte-identical pins | 3 | opus | M `swingbot/core/scanning/scan_run.py`, M `swingbot/core/scanning/short_run.py`, C `tests/regime/test_regime_wiring.py`, C `tests/regime/test_regime_off_byte_identical.py` | `_attach_item_plan(..., shock_state=None, regime_day=None)`; `_rebuild_item(..., shock_state=None, regime_day=None)`; `_maybe_run_strategy_pass(..., shock_state=None, regime_day=None)`; `short_run._bare_context(frames, shock_state=None, regime_day=None)`; `_lane_state` adds key `"regime_day"` |
| V239-11 | Regime line on every alert builder | 3 | sonnet | M `swingbot/core/scanning/alert_embeds.py`, C `tests/regime/test_regime_embeds.py` | `alert_embeds.REGIME_FIELD = "Trend"`; `alert_embeds.regime_fields(plan) -> list[tuple[str, str, bool]]` (reads `getattr(plan, "entry_context", None)`; `[]` without a line) |
| V239-12 | `GET /api/v1/market/regime` and its access row | 3 | sonnet | C `swingbot/admin/api_v1/market_regime.py`, M `swingbot/admin/api_v1/__init__.py`, M `tests/admin/access_expectations.py`, C `tests/admin/test_api_v1_market_regime.py` | JSON `{mode: str, today: RegimeDayWire \| null, history: RegimeDayWire[≤60] (oldest first), episode: {label: str, since_sessions: int} \| null}`; `RegimeDayWire` = `RegimeDay.to_row()` columns minus `doc`, dates ISO, plus `computed_at` ISO and `display: {label, words, numbers}`; `market_regime.HISTORY_LIMIT = 60`; `regime_payload(now=None, repo=None) -> dict` |
| V239-13 | SPA wire types, `RegimeStore`, `sb-regime-banner` in the shell | 4 | sonnet | M `frontend/src/app/api/models.ts`, M `frontend/src/app/api/api-client.ts`, C `frontend/src/app/stores/regime.store.ts`, C `frontend/src/app/stores/regime.store.spec.ts`, C `frontend/src/app/shell/regime-banner.ts`, C `frontend/src/app/shell/regime-banner.spec.ts`, M `frontend/src/app/shell/shell.html`, M `frontend/src/app/shell/shell.ts`, M `frontend/src/app/shell/shell.spec.ts` | TS `RegimeState`, `RegimeAction`, `RegimeDisplay`, `RegimeDay`, `RegimeEpisode`, `RegimeResponse`; `ApiClient.marketRegime(): Observable<RegimeResponse>`; `RegimeStore` (`banner: Signal<RegimeBanner \| null>`, `status: Signal<'loading' \| 'ready' \| 'error'>`, `refresh()`); `RegimeBanner {kind: 'reading' \| 'none'; label; since: number \| null; numbers: string \| null; words: string \| null; pullback: boolean; accessibleName: string}`; selector `sb-regime-banner` |
| V239-14 | Regime chip on trade detail and plan detail | 4 | sonnet | C `frontend/src/app/workspaces/trades/why/regime-chip.ts`, C `frontend/src/app/workspaces/trades/why/regime-chip.spec.ts`, M `frontend/src/app/workspaces/trades/trade-detail.ts`, M `frontend/src/app/workspaces/plans/plan-detail.ts`, M `frontend/src/app/workspaces/trades/trade-detail.spec.ts`, M `frontend/src/app/workspaces/plans/plan-detail.spec.ts` | `regimeChip(ctx: Record<string, unknown> \| null \| undefined) -> {label: string; tone: ChipTone; prefix: string} \| null`; selector `sb-regime-chip` (input `context`) |
| V239-15 | Layout audit: banner and chip at 390 / 768 / 1440 | 4 | sonnet | M `frontend/src/app/shell/regime-banner.ts`, M `frontend/src/app/workspaces/trades/why/regime-chip.ts`, M `frontend/scripts/layout-audit.allow.json` (only if a finding is a documented false positive) | none |
| V239-16 | Shadow report and live-vs-replay parity check | 5 | sonnet | C `scripts/reports/regime_shadow_report.py`, C `scripts/reports/regime_parity.py`, C `tests/regime/test_regime_shadow_report.py`, C `tests/regime/test_regime_parity.py`, C `tests/fixtures/regime/market_regime_days_export.json` | `regime_shadow_report.MIN_N = 30`; `summarise(trades: Iterable[dict]) -> list[dict]`; `render(rows) -> str`; `main(argv=None) -> int`; `regime_parity.BOUNDARY_PCT = 0.001`; `boundary_day(day: RegimeDay) -> bool`; `@dataclass ParityResult(matches: int, boundary: list, failures: list)`; `compare(stored: list[dict], spy, vix) -> ParityResult`; `main(argv=None) -> int` |
| V239-17 | SPY base-rate study (1993 → 2026-11-20) and its results doc | 5 | opus | C `scripts/research/regime_base_rates.py`, C `tests/regime/test_regime_base_rates.py`, C `docs/superpowers/results/2026-11-23-v239-regime-base-rates.md` | `regime_base_rates.END = "2026-11-20"`; `label_series(spy, vix) -> list[RegimeDay]`; `check_hashes(cache_dir: Path, work_dir: Path) -> str \| None`; `main(argv=None) -> int` |
| V239-18 | Skills, architecture map, guide and Codex mirror | 5 | sonnet | M `.claude/skills/alert-surface/SKILL.md`, M `.agents/skills/alert-surface/SKILL.md` (via `sync_codex.py`), M `docs/claude/architecture.md`, M `AGENTS.md`, M `docs/guide/07-trade-plan.md` | none |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-23-v239-bear-regime-engine-shadow_1-classifier.md` | V239-1, V239-2, V239-2b | study data fetch, pure classifier (SPY and VIX sides) and replay |
| 1b | `2026-11-23-v239-bear-regime-engine-shadow_1b-episodes-and-calendar.md` | V239-3, V239-4 | confirmed episodes and vocabulary, live session calendar |
| 2 | `2026-11-23-v239-bear-regime-engine-shadow_2-store-and-pass.md` | V239-5..V239-8 | config/mode, table + migration + repo, notify kind + notice, the scan-pass engine |
| 3 | `2026-11-23-v239-bear-regime-engine-shadow_3-stamp-and-alerts.md` | V239-9..V239-12 | `entry_context` stamp, every scan lane, `off` pins, alert lines, admin API |
| 4 | `2026-11-23-v239-bear-regime-engine-shadow_4-frontend.md` | V239-13..V239-15 | store + shell banner, detail chip, three-width layout audit |
| 5 | `2026-11-23-v239-bear-regime-engine-shadow_5-evidence-and-docs.md` | V239-16..V239-18 | shadow report, parity, base-rate study + results doc, skill/guide/doc alignment |

## Handoff

- 2026-11-23: index written. Ledger at 18 rows, leaving 2 slots for `b`
  splits. Part writers: the likeliest splits are V239-10, V239-13 and
  V239-17. A third split is a `SCOPE` stop.
