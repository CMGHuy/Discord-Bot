# v237 — Guide trading core (spec v215 Plan B): Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V237-9" -A 400 <part file>`); never read a part whole.

**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md), Plan B ("Trading core"): chapters 4–8.
**Depends on:** v235 — [2026-11-18-v235-guide-foundation_0-index.md](2026-11-18-v235-guide-foundation_0-index.md) and v236 — [2026-11-18-v236-guide-page_0-index.md](2026-11-18-v236-guide-page_0-index.md), both written and unimplemented; v237 starts only after both are merged on `main`.
**Brief:** `.superpowers/briefs/2026-11-18-v237-guide-trading-core.md` (read its "READ FIRST" and § 6 Traps before any task)

## Goal

After v235 and v236 the admin site has a Guide with three chapters: what the
bot is, the pipeline diagram and the glossary. The pipeline diagram names five
stages — levels, strategies, gates, plan construction, sizing — and every one
of those boxes still leads nowhere. Those five stages are where a trader's
real questions live: why this level and not that one, which strategies can
fire on which horizon and how well they measured, what blocked an alert, how
the stop and targets were chosen, why the suggested size is what it is. Today
the only answers are in code or in developer docs that admit they lag the code.

Once v237 ships the Guide holds chapters 4 `levels`, 5 `strategies`, 6
`gates`, 7 `trade-plan` and 8 `sizing-risk`, each written from the code
(not from the spec, which has drifted in a few places — see Handoff 6), each
with its `sources:` checked by the content test. Chapter 5 renders one live
card per registered strategy: the idea and entry rule come from a checked
card file `docs/guide/strategies/<slug>.md`, the allowed directions and
horizons come from `admits()`, and the badge comes from the registry row with
its window, N, run date and "costs not recorded; before tax" — or "no registry
row — masked, research only" for the eight masked strategies, never a fake
"WEAK, N = 0". Chapter 6 lists every gate with whether the live scan applies
it, read from the setting itself, so a gate that is built but switched off
reads "measured, not used" and flips the day its flag flips.

How it works: three new placeholder tables (plan rules, gate switches,
strategy cards) join v235's whitelist, the sizing placeholders move from the
`.env` seed values to the stored account row the sizer actually reads, and a
small card loader parses the card files. Chapters 7 and 8 contain no bare
number before `%`: every rule number is a placeholder, so a changed default
cannot leave stale prose.

What it leaves alone: no trading behaviour, no frontend code (cards are
Markdown through v236's renderer), no chapters 2, 9, 10, 11 (Plan C), no
`docs/strategy*/` rewrite. Success is measured by the content test passing
over the real guide (cards file set equals the registered keys, every
source symbol still defined, every placeholder resolves), the per-chapter
text tests, the layout check at 390/820/1440 px with eight chapters, and a
green CI run.

## Architecture

- `swingbot/admin/guide/live_risk.py` (v235) gains an account-row reader:
  `_load_account` (module attribute, `= account.load_account_config`) feeds
  `RISK_PER_TRADE_PCT`, `MAX_RISK_AMOUNT_ABSOLUTE`, `POSITION_SIZING_MODE`
  and three new `MAX_*` names; a read failure renders "not available right
  now" through `swallowed`.
- Three new placeholder modules, each one table merged by
  `placeholders._merge`: `live_rules.py` (plan and level rule numbers, the
  drawdown throttle), `live_switches.py` (`gates.switches` and single flags),
  `live_strategies.py` (`strategies.cards`).
- `swingbot/admin/guide/cards.py` parses `docs/guide/strategies/*.md` into
  `StrategyCard(path, strategy, reviewed_for, sources, body)`; the shape
  (`.path`, `.sources`, `.reviewed_for`) lets v235's `source_problems` and
  `version_problems` run over cards unchanged.
- Chapters are Markdown under `docs/guide/0N-<slug>.md`, tested by
  `tests/admin/test_guide_chapter_text.py` (v236) and the generic
  `tests/admin/test_guide_content.py` (v235).

## Global Constraints

- Chapters and cards carry `reviewed_for: 2.19.2` (bot line of `VERSION.json` today; must stay ≤ the bot version at test time).
- Chapter front matter: `title`, `slug`, `order`, `reviewed_for`, `sources`; file name `f"{order:02d}-{slug}.md"`; first block `> **In plain words** …`; developer boxes `<details><summary>Under the hood</summary> … </details>`; `##`/`###` headings only, none inside `<details>`, no placeholder on a heading line.
- Chapters 7 and 8 (orders 7–9) contain no bare number followed by `%` outside code fences (`_BARE_PCT`); every rule number in chapters 4–8 is a placeholder; card prose types no performance figure (figures come only from the registry badge).
- `sources:` entries are real paths (`swingbot/core/market/levels.py`, never the spec's `levels.py`); a `path:symbol` names a module-level def/class/assignment, a `Class.method`, or a `config.py` `Field` name; never a re-export (`requirements.py:_build_requirement_checks`, not `embeds.py`).
- Links: only `/insights/guide/<slug>` for slugs `what-it-is`, `pipeline`, `levels`, `strategies`, `gates`, `trade-plan`, `sizing-risk`, `glossary`, and glossary anchors in `GLOSSARY_LINKED` (30 from v236, plus the ones V237-8 pins). No link to `reading-an-alert`, `after-the-alert`, `measuring-edge`, `admin-tour`.
- Chapter 8 opens, right after the plain-words callout, with the one-line notice: `Education about a paper-trading tool, not advice: alerts are not tailored to you, a suggested size is a default, and past results do not predict future ones.` (v236 `GUIDE_NOTICE`, verbatim).
- Every performance figure renders with `provenance_label` (source, N, run date, costs, "before tax"); a badge never renders without N and date.
- Every new function stays under cyclomatic complexity 15; every new `except Exception` that does not re-raise calls `swallowed(log, "<unique tag>", exc, ...)`.
- No DB in tests: guide test modules patch `live_market._load_trades` and `live_risk._load_account`; cards read the committed `validation_registry.json` only through a patched `live_strategies._badge` in unit tests.
- `frontend/src/app/workspaces/guide/guide-anchors.json` is regenerated with `python scripts/dev/guide_anchors.py`, never edited by hand.
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`); only V237-15 runs the full suite, through CI.
- Do not change trading behaviour; v237 touches only `swingbot/admin/guide/`, `docs/guide/`, guide tests and the guide layout check.

## Parallelisation

Implementation is almost entirely sequential; part *writers* may run two at a time because the ledger fixes every cross-task name.

- **V237-1 → V237-2 → V237-3**: all three edit `placeholders.py`'s `PLACEHOLDERS = _merge(...)` line and the whitelist assertions in `tests/admin/test_guide_live_market.py::test_registry_merges_both_tables_and_nothing_else` (shared file); V237-1 also owns `live_risk.py` and `test_guide_placeholders.py`.
- **V237-4 after V237-3**: edits `placeholders.provenance_label` and `test_guide_placeholders.py` (shared files with V237-1..3); contract-independent otherwise.
- **V237-5 after V237-4**: consumes `cards.load_cards`, `StrategyCard`, `provenance_label(costs_included=None)`; edits the `_merge` line and the registry test again.
- **V237-6 after V237-4** (consumes `cards.load_cards`, `parse_card`); could run beside V237-5 (disjoint files: `test_guide_content.py`, `test_guide_sources.py`) — the one parallel pair.
- **V237-7 after V237-5 and V237-6**: the cards must pass the card checks and render through `strategies.cards`.
- **V237-8 → V237-9 → … → V237-13**: every chapter task edits `tests/admin/test_guide_chapter_text.py` and regenerates `guide-anchors.json` (shared files, Handoff 9); chapters link to glossary anchors V237-8 pins and use placeholders from V237-1..5; chapter 5 needs the cards (V237-7).
- **V237-14 after V237-13**: the layout check counts eight chapters in the drawer.
- **V237-15 last**: full suite via CI.

## Task ledger

| Id | Title | Part | Model | Files | Produces (consumed later) |
|---|---|---|---|---|---|
| V237-1 | Sizing placeholders read the stored account row | 1 | sonnet | M `swingbot/admin/guide/live_risk.py`, M `tests/admin/test_guide_placeholders.py`, M `tests/admin/test_guide_content.py` (fixture), M `tests/admin/test_guide_chapter_text.py` (fixture), M `tests/admin/test_api_v1_guide.py` (fixture, only if it resolves chapter bodies) | `live_risk._load_account: Callable[[], dict]` (module attr, `= account.load_account_config`, monkeypatchable); `live_risk.UNAVAILABLE = "not available right now"`; `live_risk._account_value(key: str) -> object \| None` (None after `swallowed(log, "ops.admin.guide.account_row", exc, ...)`); `RISK_PER_TRADE_PCT` ← row `risk_pct`, `MAX_RISK_AMOUNT_ABSOLUTE` ← `max_risk_amount_absolute`, `POSITION_SIZING_MODE` ← `sizing_mode`; new names `MAX_POSITION_SIZE_PCT` ← `max_position_pct` (`"10%"`), `MAX_POSITION_VALUE_ABSOLUTE` ← `max_position_value_absolute` (`"$1,000"`), `MAX_OPEN_POSITIONS` ← `max_open_positions` (`"30"`); `RISK_PLACEHOLDERS` = 21 names; test fixture dict `_ACCOUNT_ROW` and autouse fixture `_stored_account` (patches `live_risk._load_account`) in each guide test module that resolves chapters |
| V237-2 | Plan, level and throttle rule placeholders | 1 | sonnet | C `swingbot/admin/guide/live_rules.py`, M `swingbot/admin/guide/placeholders.py`, C `tests/admin/test_guide_rules.py`, M `tests/admin/test_guide_live_market.py` | `live_rules.RULE_PLACEHOLDERS: dict[str, Callable[[], str]]` with exactly: `MIN_REWARD_PCT` (`"3%"`), `MIN_RISK_REWARD_RATIO` (`"1.5:1"`), `MAX_RISK_REWARD_RATIO` (`"2.5:1"`), `CONFLUENCE_DEVIATION_PCT` (`"5%"`), `MIN_TARGET_CONFLUENCE_COUNT` (`"2"`), `DEDUP_TOLERANCE_PCT` (`"2%"`), `SIGNAL_CONFIRMATION_SCANS` (`"1"`), `MIN_ALERT_CONFIDENCE_LEVEL` (`"4"`), `stop.hard_cap` (`risk_limits.HARD_MAX_PLANNED_LOSS_PCT`, `"2%"`), `stop.clamp_level` (`HARD_MAX_PLANNED_LOSS_PCT - builders.CLAMP_HEADROOM_PCT`, `"1.75%"`), `plan.tp1_share` (`params.TP1_FRACTION`, `"50%"`), `plan.runner_floor` (`params.RUNNER_FLOOR_FRACTION`, `"67%"`), `plan.breakeven_trigger` (`strategy_types.BREAKEVEN_TRIGGER_FRACTION`, `"50%"`), `plan.trail_atr` (`params.TRAIL_ATR_MULT`, `"2.5 × ATR(14)"`), `plan.expiry_bars` (`params.DEFAULT_EXPIRY_BARS`, `"5 bars"`), `levels.touch_atr` (`levels_lifecycle.TOUCH_ATR_MULT`, `"0.25 × ATR"`), `levels.break_atr` (`BREAK_ATR_MULT`, `"1 × ATR"`), `throttle.ladder` (table `\| Drawdown from peak \| New-entry size \|` from `throttle.DD_LADDER`, last row "paused"), `throttle.resume` (`RESUME_DD_PCT`, `"15%"`), `throttle.streak` (`STREAK_TRIGGER`/`STREAK_MULT` sentence), `DD_THROTTLE_ENABLED` (on/off), `KILLSWITCH_DEFAULT_ON` (on/off); `PLACEHOLDERS = _merge(RISK_PLACEHOLDERS, MARKET_PLACEHOLDERS, RULE_PLACEHOLDERS)` |
| V237-3 | Gate switch placeholders | 1 | sonnet | C `swingbot/admin/guide/live_switches.py`, M `swingbot/admin/guide/placeholders.py`, C `tests/admin/test_guide_switches.py`, M `tests/admin/test_guide_live_market.py` | `@dataclass(frozen=True) SwitchRow(label: str, settings: tuple[str, ...], active: Callable[[], bool])`; `live_switches.SWITCH_ROWS: tuple[SwitchRow, ...]` (labels, in order: `Market regime gate`, `Adjacent-horizon alignment`, `Relative strength, long arm`, `Relative strength, short arm`, `Dead-cat bounce veto`, `Earnings blackout`, `Pullback volume dry-up`, `Headroom to the first target`, `S/R minimum level touches`, `MA Ribbon confirm bars`, `RSI Divergence turn confirmation`, `FVG level mode`, `Next-open market entry and gap reclaim`, `Data-driven stops`, `Stall exit`, `Runner structure exit`); `live_switches.APPLIED = "applied"`, `NOT_USED = "measured, not used"`; `SWITCH_PLACEHOLDERS` with exactly: `gates.switches` (table `\| Gate \| Setting \| Now \| In the live scan \|`), `STRATEGY_ALERTS_MODE` (option label + value, e.g. ``"Off (`off`)"``), `STRATEGY_ALERTS_LIVE_STRATEGIES` (`"every strategy"` when empty), `RS_GATE`, `RS_LEADER_PERCENTILE`, `RS_LAGGARD_PERCENTILE`, `HTF_CONFLUENCE_ENABLED`, `AVWAP_LEVELS_ENABLED`, `LEVEL_LIFECYCLE_STOPS_ENABLED`, `SCALE_OUT_ENABLED`, `PLAN_ENGINE_V2` (flags render `on`/`off`, percentiles as numbers); `PLACEHOLDERS = _merge(RISK_…, MARKET_…, RULE_…, SWITCH_PLACEHOLDERS)` |
| V237-4 | Strategy card loader and "costs not recorded" | 1 | sonnet | C `swingbot/admin/guide/cards.py`, C `tests/admin/test_guide_cards.py`, M `swingbot/admin/guide/placeholders.py` (`provenance_label`), M `tests/admin/test_guide_placeholders.py` | `@dataclass(frozen=True) StrategyCard(path: Path, strategy: str, reviewed_for: str, sources: tuple[str, ...], body: str)`; `cards.cards_dir(root: Path \| None = None) -> Path` (`(root or chapters.guide_dir()) / "strategies"`); `cards.parse_card(path: Path) -> StrategyCard` (`GuideFormatError` when: front matter missing; `strategy` not a non-empty str; `reviewed_for` not `N.N.N`; `sources` not a non-empty list; body empty; a body line starts with `#`; body contains `{{`; file stem ≠ `live_market.strategy_file_slug(strategy)`); `cards.load_cards(root: Path \| None = None) -> list[StrategyCard]` (sorted by file name; `[]` when the folder is absent); `provenance_label(*, source, n, run_date, costs_included: bool \| None)` — `None` renders `"costs not recorded"` |
| V237-5 | `strategies.cards` placeholder | 1 | sonnet | C `swingbot/admin/guide/live_strategies.py`, M `swingbot/admin/guide/placeholders.py`, C `tests/admin/test_guide_strategies.py`, M `tests/admin/test_guide_live_market.py` | `live_strategies._load_cards: Callable[[], list[StrategyCard]]` (`= cards.load_cards`), `live_strategies._badge: Callable[[str], Badge]` (`= lambda key: registry.get_badge("strategy", key)`), both module attrs; `NO_ROW = "no registry row"`, `NO_ROW_MASKED = "no registry row — masked, research only"`; `window_kind(window: str) -> str` (`"TRAIN-window"` when the window ends before `2024-01-01`, else `"validation-window"`); `badge_line(key: str, masked: bool) -> str`; per key in `registered_strategy_keys()` order a block `### <key>` / `**Status:** live` or `masked — research only` / `**Long:** <cell> · **Short:** <cell>` (cells from `live_market._side_cell`) / `**Badge:** <STATUS> — ExpR <+0.195R>, win rate <49.1%>; <provenance_label(source=f"{kind} backtest {window}", n, run_date, costs_included=None)>` or `NO_ROW` / `NO_ROW_MASKED` (no row ⇔ `n == 0 and not run_date`) / card body; a registered key without a card, or a card whose `strategy` is not registered, raises `GuideFormatError`; `STRATEGY_PLACEHOLDERS = {"strategies.cards": …}`; `PLACEHOLDERS = _merge(RISK_…, MARKET_…, RULE_…, SWITCH_…, STRATEGY_PLACEHOLDERS)` |
| V237-6 | Content checks extended to strategy cards | 1 | sonnet | M `tests/admin/test_guide_content.py`, M `tests/scripts/test_guide_sources.py` | `card_problems(root: Path \| None = None) -> list[str]` (parse errors and unregistered `strategy:` values, as strings); `REAL_CHECKS` gains `"card format"`, `"card sources"` (`source_problems(cards.load_cards())`), `"card reviewed_for"` (`version_problems(cards.load_cards(), _bot_version())`); each with a synthetic-card test; `guide_sources.touched()` test over a `StrategyCard` |
| V237-7 | The nineteen strategy cards | 2 | sonnet | C `docs/guide/strategies/{break-retest,bull-trap,downtrend-overbought-fade,earnings-gap-drift,elliott-wave,ema-crossover,fibonacci,fibonacci-continuation,fibonacci-limit,first-bearish-compression-release,ma-ribbon,macd,rsi,rsi-divergence,supportresistance,turtle-soup,vol-expansion-breakdown,volume-profile,vwap}.md`, M `tests/admin/test_guide_strategies.py` | one card per registered key; body shape `**Idea.** …` / `**Entry rule.**` bullets / `**Where it fires.** …` (where the rule fires vs what `admits` allows) / optional `<details><summary>Under the hood</summary>`; live cards ≤ ~850 bytes, masked ≤ ~550 bytes; `test_real_cards_render_for_every_registered_key` |
| V237-8 | Glossary: terms chapters 4–8 link | 2 | haiku | M `docs/guide/12-glossary.md`, M `tests/admin/test_guide_chapter_text.py` (`GLOSSARY_LINKED`), Regenerate `frontend/src/app/workspaces/guide/guide-anchors.json` | new `###` terms: `Level lifecycle` (`level-lifecycle`), `Direction mask` (`direction-mask`), `Drawdown throttle` (`drawdown-throttle`), `Kill switch` (`kill-switch`); `GLOSSARY_LINKED` += those four and the existing `masked`, `clamp`, `rejected-plan`, `suggested-size`, `entry`, `shadow-mode`, `support-and-resistance`, `provenance-label`, `train-and-validation`, `plan-states`, `expectancy-expr` |
| V237-9 | Chapter 4: Finding levels and setups | 2 | sonnet | C `docs/guide/04-levels.md`, M `tests/admin/test_guide_chapter_text.py`, Regenerate `guide-anchors.json` | slug `levels`, order 4, title `Finding levels and setups`; anchors `the-next-level-idea`, `level-families`, `confluence-counts-families`, `bonus-confirmations`, `touch-break-and-the-four-states`, `higher-horizon-alignment`, `closed-bars-only`, `the-minimum-move`, `duplicate-merge` |
| V237-10 | Chapter 5: Strategies | 3 | sonnet | C `docs/guide/05-strategies.md`, M `tests/admin/test_guide_chapter_text.py`, Regenerate `guide-anchors.json` | slug `strategies`, order 5, title `Strategies`; anchors `strategies-are-not-level-families`, `how-a-strategy-alert-is-sent`, `reading-a-card`, `masked-strategies`, `the-cards` (`{{strategies.cards}}` is the last line of that section) |
| V237-11 | Chapter 6: Filters and gates | 3 | sonnet | C `docs/guide/06-gates.md`, M `tests/admin/test_guide_chapter_text.py`, Regenerate `guide-anchors.json` | slug `gates`, order 6, title `Filters and gates`; anchors `what-a-gate-does`, `gates-in-the-live-scan`, `direction-and-horizon-masks`, `shared-entry-gates`, `market-regime`, `relative-strength`, `higher-horizon-alignment`, `post-signal-fill-vetoes`, `measured-not-used`; uses `{{gates.list}}`, `{{gates.switches}}` |
| V237-12 | Chapter 7: Building the trade plan | 3 | sonnet | C `docs/guide/07-trade-plan.md`, M `tests/admin/test_guide_chapter_text.py`, Regenerate `guide-anchors.json` | slug `trade-plan`, order 7, title `Building the trade plan`; anchors `entry`, `the-stop`, `the-stop-distance-cap-and-the-clamp`, `the-stop-never-widens`, `targets-that-pay-for-the-risk`, `scale-out-and-the-runner`, `how-a-plan-closes`, `backtest-and-live-use-the-same-plan` |
| V237-13 | Chapter 8: Sizing and risk | 4 | sonnet | C `docs/guide/08-sizing-risk.md`, M `tests/admin/test_guide_chapter_text.py`, Regenerate `guide-anchors.json` | slug `sizing-risk`, order 8, title `Sizing and risk`; anchors `three-limits-not-one`, `how-the-share-count-is-found`, `sizing-modes`, `gap-aware-sizing`, `portfolio-and-correlated-heat`, `drawdown-throttle-and-kill-switch`, `reject-clamp-or-size-0`, `caps-that-are-not-applied`, `costs-turnover-and-tax` |
| V237-14 | Layout check covers chapters 4–8 | 4 | sonnet | M `scripts/dev/guide_layout_check.py`, M `tests/scripts/test_guide_layout_check.py`, M `frontend/scripts/layout-audit-lib.mjs`, M `frontend/scripts/layout-audit-lib.test.mjs`, C `docs/superpowers/results/2026-11-18-v237-guide-layout.md` | `CHAPTERS_IN_DRAWER = 8`; `PAGES` += `"strategies"`, `"sizing-risk"`; `DEEP_LINKS` += `"sizing-risk#reject-clamp-or-size-0"`; layout-audit `ROUTES` += `/insights/guide/strategies` (count +1) |
| V237-15 | Full-suite verification | 4 | haiku | none (run only; CI) | push, then watch the CI run green (`0 failed`, `0 xfailed`) |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-18-v237-guide-trading-core_1-placeholders.md` | V237-1..V237-6 | account-row sizing, rule and switch placeholders, card loader, `strategies.cards`, card content checks |
| 2 | `2026-11-18-v237-guide-trading-core_2-cards-levels.md` | V237-7, V237-8, V237-9 | nineteen cards, glossary terms, chapter 4 |
| 3 | `2026-11-18-v237-guide-trading-core_3-strategies-gates-plan.md` | V237-10, V237-11, V237-12 | chapters 5, 6, 7 |
| 4 | `2026-11-18-v237-guide-trading-core_4-sizing-layout.md` | V237-13, V237-14, V237-15 | chapter 8, layout check, CI |

## Handoff

Controller decisions, 2026-11-18 (binding on every part writer):

1. **Card contract is Plan B's.** V237-4 adds the card front-matter parser with a required `strategy:` field holding the exact registry key (the file-slug → key mapping is lossy: `Support/Resistance` → `supportresistance`); V237-5 adds `strategies.cards` in the new `swingbot/admin/guide/live_strategies.py`; V237-6 adds the card checks to v235's `tests/admin/test_guide_content.py` (file set equals registered keys — v235's existing `strategy cards` check; every card's `strategy:` is registered; sources and `reviewed_for` checks run over cards). `scripts/dev/guide_sources.touched()` already accepts any object with `.path`/`.sources`; its own `load_cards()` is left as is.
2. **Masked strategies** (no registry row): the card prints `no registry row — masked, research only`, never a default WEAK/N = 0 badge. A live key without a row prints `no registry row`.
3. **Card provenance**: the registry row's own window (`TRAIN-window` 2020–2023 refresh vs `validation-window` 2024–2025, from `Badge.window`), N, run date, and `costs not recorded` (rows carry no friction flag; `provenance_label(costs_included=None)`); never "costs included". Always "before tax".
4. **Live sizing values come from the stored account row** (`load_account_config()`), not the `.env` seed keys (`account.py:_SEED_ENV_KEYS`): V237-1 changes `RISK_PER_TRADE_PCT`, `MAX_RISK_AMOUNT_ABSOLUTE`, `POSITION_SIZING_MODE` and adds `MAX_POSITION_SIZE_PCT`, `MAX_POSITION_VALUE_ABSOLUTE`, `MAX_OPEN_POSITIONS` reading the row, with `not available right now` via `swallowed` on failure. `RISK_PER_TRADE_PCT.max` stays the schema `Field.max`. Heat caps stay `config` reads (they are read live from config by the scan).
5. **Chapters describe only what is live.** Chapter 6 says headroom and dead-cat vetoes are built but off by default ("measured, not used") and takes the on/off state from `{{gates.switches}}`, never hard-coded. Chapter 8 never says a sector or per-horizon cap blocks alerts: `sector_check`, `horizon_check`, `SECTOR_HEAT_CAP_PCT`, `MAX_OPEN_PER_HORIZON` have no caller in the scan — say they exist (sector heat is a Risk-page reading) and are not applied to the live scan. `MAX_OPEN_POSITIONS` never blocks an alert. Prefer a placeholder reading a flag over a hard-coded "off" wherever a flag exists (V237-2/3 tables).
6. **Spec drift — write from the code, not the spec**: stops live in `swingbot/core/planning/builders.py`, `planning/stop_scope.py`, `planning/lifecycle.py`, `swingbot/core/risk_limits.py` (`edge/stops.py` is off behind `DATA_DRIVEN_STOPS_ENABLED`; mention it only as measured, not used); `levels_lifecycle` states are `fresh`/`tested`/`delivered`/`decaying` (no "retest"); `MIN_REWARD_PCT` defaults 3.0 and is floored lower per horizon (not "5%"); cite `swingbot/core/scanning/requirements.py:_build_requirement_checks`.
7. **New placeholders for chapters 7–8** (no bare `N%`): V237-1/2/3 add them and update v235's whitelist assertions (`test_risk_table_has_exactly_the_planned_names`, `test_registry_merges_both_tables_and_nothing_else`) in the same task.
8. **Links**: only chapters that exist after v236 + v237 (1, 3, 4–8, 12) and glossary anchors pinned in `GLOSSARY_LINKED` (v236's 30 plus V237-8's 15). No links to chapters 2, 9, 10, 11 (Plan C). Self-links `(#anchor)` name a heading of the same chapter.
9. **Each chapter task carries the full chapter text** with `sources:` verified against code (`git grep -n` each symbol before writing); chapter tasks regenerate `guide-anchors.json` and run one at a time.
10. **Verification**: per-task narrow runs; V237-15 is the single full-suite task, run by CI. Max 20 tasks (15 here); each task < 20 KB.

Plan-writer decisions (index, 2026-11-18), for the controller to check:

- **Card split fallback.** V237-7 writes all nineteen cards in one task because v235's `strategy cards` check fails the moment `docs/guide/strategies/` holds any `.md` without the full set. Budget: live card ≤ ~850 bytes, masked ≤ ~550 bytes, so the task lands near 18 KB. If it still passes 20 KB, split as `V237-7` (eleven live cards) + `V237-7b` (eight masked cards); V237-7's verification then deselects `test_the_real_guide_passes[strategy cards]` and `[card format]` (named in its step), V237-7b turns them green, and both merge together.
- **Account row in tests.** `live_risk._load_account` would open the database; every guide test module that resolves chapter bodies gets an autouse `_stored_account` fixture beside its existing `_no_live_book` (V237-1 lists the files after `git grep -ln "resolve(" tests/admin/test_guide_*.py tests/admin/test_api_v1_guide.py`).
- **Layout check pins three chapters** (`CHAPTERS_IN_DRAWER = 3` in v236's `guide_layout_check.py`); V237-14 moves it to 8 — the check fails after V237-9 until then, which is why V237-14 runs right after V237-13 and before V237-15.
- **Card headings come from the placeholder** (`### <key>` per card): they reach the API heading list, the TOC and search, but not `guide-anchors.json` (raw headings); no `?` link may target a card anchor.
- **Badge kind threshold** `2024-01-01` lives as `live_strategies._VALIDATION_FROM` (the validation window start, `docs/claude/backtest-methodology.md`); no shared constant exists in `swingbot/`.
