# v211 — Shock-conditioned short screens (Track 2 of v209) (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V211-7:" -A 400 docs/superpowers/plans/2026-11-06-v211-shock-short-screens_3-*.md`.

**Bump:** none (offline screen code and results docs only; no running bot, admin or Discord code changes — `document-conventions.md`: a spec that ships no running code bumps nothing)
**Edge:** expectancy — a prediction: the two shots decide whether a shock-conditioned short arm exists that adds pooled ExpR on exactly the days the long book loses most (2026-11-05: 26 trades, −13.9R). The plan ships no live change; if both shots fail, the closing commit amends this to "expectancy, measured none" with one clause.
**Screen:** Stage −2 pre-registration — this plan spends the two one-shot screens the spec pre-registers in § Track 2 (frozen at the spec's commit); no `SCREEN-PASS` can precede them. The spec header's `exempt (integrity)` covers Track 1 (plans v209, v210) only.
**Spec:** [v209 — Market-shock detector (shadow) and shock-conditioned short screens](../specs/2026-11-05-v209-market-shock-detector-design.md) (§ Track 2 — the shock-conditioned short screens; § What changes → Plans names this plan; § Rollback, § Non-goals; § Panel review and the plan-briefer reconciliation at the end)
**Brief:** `.superpowers/briefs/2026-11-05-v209-market-shock-detector.md` (§1 "Track 2 -- screens", §2 "Track 2", §3.11–3.13, §4 Track 2 idea and runner tests, §5 rows for `screen/*`, D4–D7, traps T9–T15)
**Worktree:** implement V211-1..V211-12 in `.claude/worktrees/2026-11-06-v211-shock-short-screens` (branch of the same name, created in V211-1's first step; `docs/claude/document-lifecycle.md`). V211-13..V211-16 run on `main` after V211-1..12 are merged and CI is green.

## Goal

The partner's goal for this work is **short performance**. On 2026-11-05 the
long book lost 13.9R in one session while the market fell, and the partner
asked the bot to switch to shorts when the market turns sharply. Every short
idea measured so far was tested *unconditionally*, across all days, and
failed (v104 Part B, v182). The spec's new hypothesis is narrower: breakdown
shorts pay **only while a broad shock is on**. Before any live short arm can
be built, that hypothesis has to clear the Stage −2 idea screen. This plan
runs that screen, once per idea, exactly as the spec froze it.

Once shipped, the repository holds two new idea modules
(`shock_support_break_short`, `shock_failed_bounce_short`, one `FAMILY`
`shock_breakdown`), two new daily context series (`BREADTH_ATR1`, the share
of point-in-time S&P 500 members that fell at least 1 ATR14 that day, and
`^VIX`), and a screen runner that can read a context series as a **level**
instead of a z-score. Two results docs and two ledger rows record the
verdicts; the methodology's closed list gains both, so neither is ever
re-run with a looser definition.

How it works: a declared `CONTEXT_KIND = "level"` extension lets an idea
load a context file under the session-alignment checks but without the v174
z-coverage check (a breadth fraction of 0.0 breaks `trailing_z`). Each idea
computes the daily SHOCK state itself from the two series (enter at breadth
≥ 0.40; release on breadth ≤ 0.10 with VIX down, SHOCK still on the release
date). The standard race (fixed, K = 20 matched null, cap 10, short, 5 bps,
commission, borrow) decides the verdict. Beside it, never gating, the
results doc prints a null drawn only from the ticker's SHOCK days, the
unconditional control, a gap split, a day-of-episode split, a 3× slippage
re-price, `skipped_overlap`, an outcome-blind per-year preflight, and the
BH q-values across every short idea screened so far.

What it leaves alone: **every live path.** No scan, plan, gate, alert,
Discord notice, admin endpoint or stored record changes; **LONG issuing is
byte-for-byte unchanged** (the screens are offline runs over 2010–2019
cache files). It does not touch the Track 1 detector (plans v209, v210) and
its pass would not license the detector's labels. Success is the two
verdicts recorded honestly: the pre-registered rule (N ≥ 300, ≥ 7/9 years,
lower 95 % CI > 0, ΔExpR ≥ +0.10R) decides; a `SCREEN-PASS` opens a
follow-on live spec (Stage −1 on the bot's own replay first), a fail
closes the definition for good.

## Architecture

- **Data** (V211-1..3): `CONTEXT_ONLY_STEMS` keeps both new files out of every
  ticker listing; `fetch_backtest_data.py --vix-context` writes `^VIX.csv`
  (not `_VIX.csv`) and refuses a calendar that differs from SPY's sessions;
  `screen/breadth.py` + `scripts/data/build_breadth_context.py` build
  `BREADTH_ATR1.csv` from the PIT members' cache files with ATR dated `t−1`.
- **Runner level kind** (V211-4..6, `scripts/backtest/screen_idea.py`):
  `Idea.context_kind` (`"z"` default, `"level"`), level loads skip only the
  z-coverage check; `--pin-context` adds the new SHAs to the existing pin
  file; level branches for scope sentence, hypothesis, family overlap (real
  context), v174 diagnostics (skipped); opt-in per-ticker checkpointing.
- **Ideas** (V211-7..9, `screen/ideas/`): `_shock_breakdown.py` (frozen
  constants, daily SHOCK state with episode ids, shared helpers), then one
  module per idea with its `control_events`.
- **Read-outs** (V211-10..12): pure `screen/shock_readouts.py` (gap buckets,
  day-of-episode tag, shock-day null, per-year preflight); runner wiring into
  `TickerScreen.shock`, the summary and the results doc; `--count-only`
  learns context ideas and prints the preflight block.
- **Shots and records** (V211-13..16, on `main`): build the two files on the
  real cache, pin, preflight, one shot each through `backtest-runner`, the
  closed-list rows, the summary doc, `/panel` and `/close-out`.

**Tech stack:** Python 3.11, pandas/numpy, yfinance (the `^VIX` fetch only),
pytest.

## Global Constraints

- **LONG unchanged, no live path touched.** The diff may touch only `scripts/backtest/screen_idea.py`, `scripts/backtest/cache_dir_source.py`, `scripts/data/{fetch_backtest_data,build_breadth_context,fetch_earnings_dates}.py`, `swingbot/core/backtesting/screen/**`, `tests/**`, and docs. Any other `swingbot/` file in `git diff --stat main...HEAD` is a review stop.
- **Existing ideas are byte-identical.** `tests/backtest_scripts/test_screen_context_runner.py::PARITY_DIGESTS`, `tests/backtesting/screen/test_long_byte_identical.py`, the hypothesis golden (V211-5) and the count-only golden (V211-12) pass **untouched**. A changed digest or golden is a stop, never an update.
- **Frozen definitions (spec § Track 2), never tuned.** Enter SHOCK on `d_breadth[t] ≥ 0.40`; release on the first SHOCK date with `d_breadth[t] ≤ 0.10` **and** `^VIX Close[t] < Close[t−1]`, the release date itself still SHOCK; the next date is NORMAL unless `d_breadth ≥ 0.40` (then SHOCK, **a new episode**). `d_breadth[t]` = share of date-`t` PIT members with `(Close[t] − Close[t−1]) / ATR14[t−1] ≤ −1.0`. Idea 1: SHOCK on `t`, `Close[t] < min(Low[t−20 .. t−1])`, first such close in the episode. Idea 2: spec conditions 1–5 verbatim (decline ≥ 1.0 × `ATR14[b−2]` from `max(High[b−10 .. b−2])`, `b ∈ t−5 .. t−1`, `Close[b] > Close[b−1]`, `High[b] < max(High[b−10 .. b−2])`, `Close[t] < Low[b]` first failure, latest `b`). Both: `RACE = "fixed"`, `CAP = 10`, `DIRECTION = "short"`, `ENTRY` next open, `FAMILY = ("shock_support_break_short", "shock_failed_bounce_short")`.
- **Names.** Context stems `BREADTH_ATR1` and `^VIX`; files `<cache_dir>/BREADTH_ATR1.csv`, `<cache_dir>/^VIX.csv` (columns `Date,Open,High,Low,Close,Volume`); ledger ids `screen-shock_support_break_short`, `screen-shock_failed_bounce_short`.
- **Level scope sentence, exact copy** (V211-5, `diagnostics.scope_sentence` for `context_kind == "level"`, `{enter}`/`{release}` from `idea.params`, `{cap}` = `idea.time_cap_bars`): `Scope: a daily breadth-shock proxy (SHOCK_D: enter when BREADTH_ATR1 >= {enter:.2f}, release when BREADTH_ATR1 <= {release:.2f} and ^VIX closes down), not the live market-shock detector; a pass does not license the detector's labels, and a fail closes exactly this frozen definition (short only, the fixed {cap}-bar race) and is never re-run with a looser one.`
- **No lookahead.** `BREADTH_ATR1[t]` reads bars dated `≤ t` (ATR `≤ t−1`); the state at `t` reads context `≤ t`; a ticker date absent from the context calendar is NORMAL (no forward-fill, as `pit.context_on`). Truncation tests pin each (`helpers.assert_prefix_stable`).
- **Never gating.** The verdict is `verdict.decide` on the standard paired events, unchanged. Shock-day null, control, gap split, day-of-episode split, 3× stress (`SHOCK_STRESS_SLIPPAGE_FACTOR = 3`, level-kind ideas only), `skipped_overlap`, preflight and q-values are printed only.
- **One shot each.** Closed pre-registrations are never re-run (`backtest-methodology.md` § Closed pre-registrations: v17 P2a, v34, v104 Part B, v182 `range_breakdown_close`, v191; `range_breakdown_stop` is unspent and is **not** run here). A `SCREEN-FAIL` or `SCREEN-UNDERPOWERED` is final; the preflight never decides whether to shoot.
- **Shots run only on `main`**, after V211-1..12 are merged and the CI run on that push is green (a shot on unreviewed code cannot be taken back). Each shot runs through `backtest-runner` with `--checkpoint-dir data/screen_checkpoints/screen-<idea>` so a restart skips finished tickers (`working-conventions.md` § Long runs must checkpoint).
- **Data never refetched after the pin.** `^VIX.csv` and `BREADTH_ATR1.csv` are built once on the real cache (`E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext`, gitignored) in V211-13, pinned with `--pin-context` into the existing `docs/superpowers/results/2026-10-18-v174-context-hashes.json` (existing entries never rewritten), and the pin file is committed before shot 1.
- Every function written or changed < 15 cyclomatic complexity (`python scripts/dev/complexity_gate.py`); no legacy function's CC rises (`main()` in `screen_idea.py` gains no branch: new modes go through helpers).
- Narrow test runs only: `python scripts/dev/testrun.py file <test>`. **No task runs the full suite**; CI does. No task reaches Postgres (no `/replicate-prod-db`). New test files sit in existing directories (`tests/backtesting/screen/` → `backtesting-arms`, `tests/backtest_scripts/` → `backtest-scripts`, `tests/history_store/`), so `tests/suites.toml` changes only if a suite passes `max_tests` (then split by feature, never raise the limit).
- `.env` values are never printed. No production access is needed by any task.

## Review Focus

1. **Re-entry the day after a release.** SHOCK on the release date, NORMAL or a *new* episode the next date; Idea 1's first-break clause resets with the new episode. Owner: V211-7 (state), V211-8 (first break).
2. **A session where no member has a finite ATR move** (warm-up, data holes). `BREADTH_ATR1` is `0.0` with `Volume = 0`, never NaN, so the session index stays contiguous; a member with a missing bar leaves the denominator that day. Owner: V211-3.
3. **A restarted shot.** Resuming from the checkpoint gives the same `TickerScreen`s as an uninterrupted run; a checkpoint written for another idea, window or ticker list refuses. Owner: V211-6.
4. **Gap exactly at ±1 %.** `−1 %` falls in `<= -1%`, `+1 %` in `>= +1%`; a missing next open is excluded and counted. Owner: V211-10.
5. **A context idea in `--count-only`.** Today `count_ticker` passes no context, so a context idea would raise; the preflight must load and check context like the real run, while other ideas' count output stays byte-identical. Owner: V211-12.

## OPEN (decisions the controller should check)

- **`d_breadth` denominator.** The spec says "share of that date's PIT members"; the plan uses members **with a finite move that day** (cache file present, `Close[t]`, `Close[t−1]`, `ATR14[t−1]` all finite) and writes that count as `Volume`; 0 members ⇒ 0.0. The builder prints per-year coverage (members with data / members).
- **Control events.** Idea 1's control is "a fresh 20-day-low close" (`Close[t−1]` was not below its own prior 20-day low), because "first break per episode" has no episode once the shock state is ignored. Idea 2's control is conditions 1–5 with the shock state ignored.
- **Shock-day null and day-of-episode.** The second null draws K = 20 from the ticker's eligible SHOCK-day bars **without** the month/trend match (inside a handful of shock days that match would drop nearly every event); "day after the breadth peak" is computed from the episode's running maximum through the signal date (no lookahead), bucket `peak` vs `later`.

## Parallelisation

| Group | Tasks | Files | Why sequential inside |
|---|---|---|---|
| A data | V211-1, V211-2, V211-3 (any order, parallel) | 1: `screen/context.py` (one constant + helper), `scripts/backtest/cache_dir_source.py`, `scripts/data/fetch_earnings_dates.py`; 2: `scripts/data/fetch_backtest_data.py`; 3: C `screen/breadth.py`, C `scripts/data/build_breadth_context.py` | disjoint files, no contract between them |
| B runner | V211-4 → V211-5 → V211-6 | `scripts/backtest/screen_idea.py`, `screen/ideas/__init__.py` (4), `screen/diagnostics.py` (5), `tests/backtest_scripts/test_screen_level_context.py`, `test_screen_checkpoint.py` | one file (`screen_idea.py`) throughout; 5 builds on 4's `context_kind` |
| C ideas | V211-7, then V211-8 → V211-9 | C `screen/ideas/_shock_breakdown.py` (7); C the two idea modules, M `screen/ideas/__init__.py`, `tests/backtesting/screen/test_ideas_registry.py`, `tests/backtest_scripts/test_screen_context_runner.py` (8, 9) | V211-7 may run beside group B (disjoint files, needs nothing from it); 8 needs V211-4 (`CONTEXT_KIND`) and V211-6 merged (both edit runner test files and the registry), 9 appends to 8's registry edits |
| D read-outs | V211-10 → V211-11 → V211-12 | C `screen/shock_readouts.py` (10); `screen_idea.py` (11, 12) | 10 needs V211-7 (`shock_state`); 11 needs 10, V211-6 and V211-9; 12 edits `screen_idea.py` after 11 |
| E shots | V211-13 → V211-14 → V211-15 → V211-16 | results docs, ledger, pin file, `backtest-methodology.md`, plan/spec files | on `main` after A–D merged and CI green; shot 2 after shot 1 so its doc cites shot 1's q; 15 needs both rows; 16 closes |

Group A runs beside B and V211-7. **No dependency on plans v209 or v210**,
checked against the brief: those plans touch `swingbot/core/market/shock.py`,
`swingbot/core/scanning/*`, `swingbot/commands/loops.py`, the Alembic
revision, `db/repositories/`, `lifecycle_*`, `admin/api_v1/market.py`,
`frontend/` and `VERSION.json`; this plan touches none of those and imports
nothing they create (`SHOCK_D` is computed inside the ideas, deliberately not
the detector). The only shared file is the spec, edited in V211-16 only.

## Task ledger

| Id | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V211-1 | Context-only stems never listed as tickers | 1 | sonnet | M `swingbot/core/backtesting/screen/context.py`; M `scripts/backtest/cache_dir_source.py` (`listing`, `load_all`, `cache_files`); M `scripts/data/fetch_earnings_dates.py` (`cached_symbols`); C `tests/backtest_scripts/test_context_stems_never_listed.py` | `screen.context.CONTEXT_ONLY_STEMS: frozenset[str] = frozenset({"BREADTH_ATR1", "^VIX"})`; `screen.context.is_context_only(stem: str) -> bool`. `SPY`, `TLT`, `UUP` stay listed (`test_cache_dir_scripts.py:117` unchanged); `scripts/data/snapshot_backtest_cache.py` deliberately keeps copying every file; `fetch_intraday_cache.py` and `reports/audit_quality_score.py` read `data/backtest_cache`, which never holds the context files, and stay untouched |
| V211-2 | `^VIX` daily context fetch, stored as `^VIX.csv`, aligned to SPY sessions | 1 | sonnet | M `scripts/data/fetch_backtest_data.py`; C `tests/backtest_scripts/test_fetch_vix_context.py` | `VIX_CONTEXT = "^VIX"`; `vix_context_path(cache_dir: Path) -> Path` (`<cache_dir>/^VIX.csv`); `fetch_vix_context(cache_dir: Path, *, start: str = "2009-01-01", end: str = "2019-12-31", fetcher=fetch) -> Path` — writes normalised OHLCV, then `check_vix_sessions`; `check_vix_sessions(vix_index: pd.DatetimeIndex, spy_index: pd.DatetimeIndex, *, start: str = CONTEXT_START, end: str = "2019-12-31") -> None` raising `screen.context.ContextError` on any missing or extra date; CLI `--vix-context --cache-dir PATH` (refuses an existing `^VIX.csv` without `--force`) |
| V211-3 | `BREADTH_ATR1` builder (point-in-time, ATR dated `t−1`) | 1 | opus | C `swingbot/core/backtesting/screen/breadth.py`; C `scripts/data/build_breadth_context.py`; C `tests/backtesting/screen/test_breadth.py`; C `tests/backtest_scripts/test_build_breadth_context.py` | `breadth.NAME = "BREADTH_ATR1"`, `breadth.ATR_MOVE = -1.0`; `member_atr_moves(df: pd.DataFrame) -> pd.Series` = `(Close − Close.shift(1)) / indicators.atr(df).shift(1)`; `breadth_atr1(frames: Mapping[str, pd.DataFrame], intervals: Mapping[str, list], sessions: pd.DatetimeIndex) -> pd.DataFrame` (index `sessions`, `Open=High=Low=Close` = fraction in [0, 1], `Volume` = members with a finite move, 0.0/0 when none); script `main(argv=None) -> int` with `--cache-dir`, `--membership`, `--out` (default `<cache-dir>/BREADTH_ATR1.csv`), refusing an existing output, printing per-year coverage |
| V211-4 | Runner `CONTEXT_KIND = "level"`: idea field, level load path, `--pin-context` | 2 | opus | M `swingbot/core/backtesting/screen/ideas/__init__.py` (`Idea.context_kind`, `_load`, docstring); M `scripts/backtest/screen_idea.py` (`_context_frame`, `load_context`, `_context_step`, `add_context_hashes`, `--pin-context`); C `tests/backtest_scripts/test_screen_level_context.py` | `ideas.CONTEXT_KINDS = ("z", "level")`; `Idea.context_kind: str = "z"` (module attr `CONTEXT_KIND`, `"level"` requires a non-empty `CONTEXT`, `ValueError` otherwise); `load_context(cache_dir, tickers, *, end=WINDOW_END, kind: str = "z")` (level: raw-index + contiguity checks, **no** `check_z_coverage`); `add_context_hashes(records: Mapping[str, dict], path) -> list[str]` (adds missing tickers, returns their names sorted, raises `ContextError` if a pinned SHA differs, never rewrites an existing entry); CLI `--pin-context` (pins `_hash_records(cache_dir)` missing entries, prints them, writes nothing else, exit 0; exit 2 on a differing SHA) |
| V211-5 | Level branches: scope sentence, hypothesis, family overlap with context, v174 read-outs skipped | 2 | opus | M `swingbot/core/backtesting/screen/diagnostics.py` (`scope_sentence`); M `scripts/backtest/screen_idea.py` (`ticker_context`, `_overlap`, `_restricted`, `with_diagnostics`, `hypothesis`, `_level_hypothesis`, `render_results`); C `tests/backtest_scripts/golden/hypotheses_pre_v211.json` (captured first, from the base commit); M `tests/backtest_scripts/test_screen_level_context.py` | `scope_sentence(idea)` level branch = the exact copy in Global Constraints; `_level_hypothesis(idea) -> str` = `_short_hypothesis(idea)` + `, context BREADTH_ATR1, ^VIX levels from 2009-06-01 (v211 shock screen). ` + scope sentence; `hypothesis()` checks `context_kind == "level"` first; `ctx["context"]` holds the ticker's context mapping (or `None`); `_overlap` passes it to the partner; `_restricted` and `with_diagnostics` return `None`/the summary untouched for level ideas; `render_results` appends `_render_context` only for `context_kind == "z"` |
| V211-6 | Opt-in per-ticker checkpoint for `screen_universe` | 2 | sonnet | M `scripts/backtest/screen_idea.py` (`screen_universe`, `build_parser`, a `_run_screens` helper for `main`); C `tests/backtest_scripts/test_screen_checkpoint.py` | `screen_universe(..., checkpoint_dir: Path \| None = None)`: writes `<dir>/manifest.json` `{"idea", "start", "end", "tickers_sha256"}` and one `<ticker>.pkl` (pickled `TickerScreen`) per finished ticker, written to a temp name then renamed; on restart loads existing pickles and skips them; a differing manifest raises `ValueError("checkpoint ... belongs to another run")`; CLI `--checkpoint-dir PATH` (default none = today's behaviour) |
| V211-7 | `_shock_breakdown.py`: frozen constants, daily SHOCK state with episodes | 3 | opus | C `swingbot/core/backtesting/screen/ideas/_shock_breakdown.py`; C `tests/backtesting/screen/test_shock_breakdown_state.py` | `BREADTH = "BREADTH_ATR1"`, `VIX = "^VIX"`, `CONTEXT = (BREADTH, VIX)`, `ENTER_BREADTH = 0.40`, `RELEASE_BREADTH = 0.10`, `LOW_WINDOW = 20`, `SHOCK_PARAMS = {"breadth": "BREADTH_ATR1", "vix": "^VIX", "enter": 0.40, "release": 0.10}`, `FAMILY = ("shock_support_break_short", "shock_failed_bounce_short")`, `SOURCE`; `shock_state(breadth: pd.Series, vix: pd.Series) -> pd.DataFrame` (context calendar; columns `shock: bool`, `episode: int` 0 when NORMAL, 1.. per episode, a re-entry the day after a release starts a new id); `ticker_state(df: pd.DataFrame, context: Mapping[str, pd.DataFrame]) -> pd.DataFrame` (same columns on `df.index`, absent dates NORMAL/0); `prior_low(df, n=LOW_WINDOW) -> pd.Series` = `Low.shift(1).rolling(n).min()`; `prior_atr(df) -> pd.Series` = `indicators.atr(df).shift(1)` |
| V211-8 | Idea 1 `shock_support_break_short` + registry | 3 | opus | C `swingbot/core/backtesting/screen/ideas/shock_support_break_short.py`; M `swingbot/core/backtesting/screen/ideas/__init__.py` (`IDEA_MODULES`); M `tests/backtesting/screen/test_ideas_registry.py`; C `tests/backtesting/screen/test_idea_shock_support_break_short.py`; M `tests/backtest_scripts/test_screen_context_runner.py` (`_ctx_cache` default `context` gains `"BREADTH_ATR1", "^VIX"`, so the grown `context_tickers()` union hashes) | module attrs `CAP = 10`, `RACE = "fixed"`, `DIRECTION = "short"`, `CONTEXT = sb.CONTEXT`, `CONTEXT_KIND = "level"`, `FAMILY = sb.FAMILY`, `PARAMS = {**sb.SHOCK_PARAMS, "low_window": 20, "side": "short"}`; `events(df, context) -> pd.Series` (bool, name `shock_support_break_short`, on `df.index`); `control_events(df) -> pd.Series` (fresh 20-day-low close, shock ignored) |
| V211-9 | Idea 2 `shock_failed_bounce_short` + registry | 3 | opus | C `swingbot/core/backtesting/screen/ideas/shock_failed_bounce_short.py`; M `swingbot/core/backtesting/screen/ideas/__init__.py`; M `tests/backtesting/screen/test_ideas_registry.py`; C `tests/backtesting/screen/test_idea_shock_failed_bounce_short.py` | same attrs as V211-8 with `PARAMS = {**sb.SHOCK_PARAMS, "decline_atr": 1.0, "high_from": 10, "high_to": 2, "bounce_from": 5, "bounce_to": 1, "side": "short"}`; `bounce_bar(df) -> pd.Series` (float position of the latest qualifying `b` for each `t`, NaN when none — conditions 1–3 and 5); `events(df, context)`; `control_events(df)` (conditions 1–5, shock ignored) |
| V211-10 | `shock_readouts.py`: gap buckets, day of episode, shock-day null, preflight counts | 4 | opus | C `swingbot/core/backtesting/screen/shock_readouts.py`; C `tests/backtesting/screen/test_shock_readouts.py` | `SHOCK_STRESS_SLIPPAGE_FACTOR = 3`; `GAP_BUCKETS = ("<= -1%", "-1% .. +1%", ">= +1%")`; `gap_bucket(gap_pct: float) -> str \| None` (None for NaN); `event_tags(df, state: pd.DataFrame, breadth: pd.Series, signal_pos: np.ndarray) -> list[dict]` → `{"signal_date", "gap_pct", "gap_bucket", "episode_day": "peak" \| "later"}`; `shock_null(df, event_pos, pool: np.ndarray, k: int, seed, *, cap: int, atr, shape: str, direction: str, slippage_bps=None, commission=None) -> ShockNull` (`ShockNull(event_pos: np.ndarray, null_mean_r: np.ndarray, dropped: int)`, no month/trend match, `null.MIN_CANDIDATES` floor, `replace=False`); `preflight_years(state: pd.DataFrame, event_dates: Iterable[pd.Timestamp], years=verdict.YEARS) -> dict[int, dict]` → `{year: {"shock_days", "shock_weeks", "events"}}` (ISO weeks) |
| V211-11 | Runner wiring: `TickerScreen.shock`, shock blocks in summary and results doc, short-family q-values | 4 | opus | M `scripts/backtest/screen_idea.py` (`TickerScreen.shock`, `_shock_report`, `with_shock_blocks`, `_render_shock_blocks`, `_render_level_context`, `SHORT_SCREEN_IDS`, `short_family_q`, `_context_run`, `render_results`, `main` via the V211-6 helper); C `tests/backtest_scripts/test_screen_shock_blocks.py` | `TickerScreen.shock: dict \| None = None` (`{"null2": rows, "null2_dropped": int, "stress3": rows, "tags": list[dict]}`, level ideas only); `with_shock_blocks(summary, screens, idea) -> dict` adds `"shock"` (`null2` and `stress3` `Verdict`s, `gap` and `episode_day` per-bucket `{n, exp_r_event, delta_exp_r}`, `skipped_overlap`); `SHORT_SCREEN_IDS = ("v104-b-short-mechanisms", "screen-range_breakdown_close", "screen-range_breakdown_stop", "screen-shock_support_break_short", "screen-shock_failed_bounce_short")`; `short_family_q(rows: list[dict], row: dict) -> dict[str, float]` (BH over the ids present, via `stats.ledger_qvalues`) |
| V211-12 | `--count-only` for context ideas, with the outcome-blind preflight block | 4 | sonnet | M `scripts/backtest/screen_idea.py` (`count_ticker`, `count_universe`, `run_count`, `render_counts`, `_preflight_block`); C `tests/backtest_scripts/golden/count_only_range_breakdown_close.md` (captured first, from the base); C `tests/backtest_scripts/test_screen_preflight.py` | `count_ticker(idea, ticker, df, spans, context=None)`; `count_universe(..., context=None)`; `run_count` loads context through `_context_step` (refuses on a context or hash error, exit 2); for `context_kind == "level"` the printout ends with a per-year table `year · shock days · shock weeks · events` (2011–2019) and the totals; everything else byte-identical |
| V211-13 | Build `^VIX`/`BREADTH_ATR1` on the real cache, pin, preflight, shot 1 (`shock_support_break_short`) | 5 | sonnet | C `docs/superpowers/results/<run-date>-v211-shock-preflight.md`; M `docs/superpowers/results/2026-10-18-v174-context-hashes.json`; C `docs/superpowers/results/<run-date>-screen-shock_support_break_short.md`; M `docs/superpowers/results/preregistration-ledger.jsonl` | ledger row `screen-shock_support_break_short`; the preflight doc (both ideas' per-year tables, committed **before** the shot); the pin file with `BREADTH_ATR1` and `^VIX` |
| V211-14 | Shot 2 (`shock_failed_bounce_short`) | 5 | sonnet | C `docs/superpowers/results/<run-date>-screen-shock_failed_bounce_short.md`; M `docs/superpowers/results/preregistration-ledger.jsonl` | ledger row `screen-shock_failed_bounce_short` (its doc's q-values include shot 1's row) |
| V211-15 | Record the verdicts: closed list, summary doc | 5 | sonnet | M `docs/claude/backtest-methodology.md` (two rows in § Closed pre-registrations); M `AGENTS.md` only if it mirrors that table (grep first); C `docs/superpowers/results/<date>-v211-shock-short-screens.md` | the summary doc: both verdicts, the short-family q-values across `SHORT_SCREEN_IDS`, what a pass or a fail opens (spec § What the screens can and cannot say, § Follow-on pre-registrations) |
| V211-16 | `/panel` (staff-engineer, quant-researcher, veteran-trader) + `/close-out` | 5 | sonnet | M (moved by `/close-out`) the v211 plan files → `docs/superpowers/plans/implemented/` (or `no-lift/` if neither shot passes); M the spec only when plans v209 **and** v210 are already closed (then moved with this close-out), otherwise left in `specs/` with one line in the close-out commit saying which plan still holds it; `VERSION.json` not modified (`Bump: none`) | none (last task) |

16 ledger rows (`b` rows included).

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-06-v211-shock-short-screens_1-data.md` | V211-1, V211-2, V211-3 | context stems out of ticker listings; `^VIX.csv` fetch aligned to SPY; `BREADTH_ATR1` builder |
| 2 | `2026-11-06-v211-shock-short-screens_2-runner-level-kind.md` | V211-4, V211-5, V211-6 | `CONTEXT_KIND = "level"` load path and pin; level seams with byte-identical pins; per-ticker checkpoint |
| 3 | `2026-11-06-v211-shock-short-screens_3-ideas.md` | V211-7, V211-8, V211-9 | SHOCK state and family; the two frozen ideas and their controls; registry |
| 4 | `2026-11-06-v211-shock-short-screens_4-readouts.md` | V211-10, V211-11, V211-12 | printed read-outs (shock-day null, gap, episode day, 3× stress, q-values); `--count-only` preflight |
| 5 | `2026-11-06-v211-shock-short-screens_5-shots-closeout.md` | V211-13, V211-14, V211-15, V211-16 | real data build and pin, preflight, the two shots, closed-list rows, `/panel`, `/close-out` |
