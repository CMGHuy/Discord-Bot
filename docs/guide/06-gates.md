---
title: Filters and gates
slug: gates
order: 6
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/strategy_types.py:admits
  - swingbot/core/market/strategy_types.py:REGIME_ALLOW
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/entry_filters.py:apply_regime_gate
  - swingbot/core/scanning/regime.py:get_market_regime
  - swingbot/core/scanning/regime.py:get_htf_bias
  - swingbot/core/scanning/confidence.py
  - swingbot/core/scanning/requirements.py:_build_requirement_checks
  - swingbot/core/scanning/qualify.py:_confirmed
  - swingbot/core/scanning/qualify.py:_rs_blocked
  - swingbot/core/scanning/strategy_pass.py:_rs_blocked
  - swingbot/core/edge/rs_gate.py:rs_verdict
  - swingbot/core/market/mtf.py:adjacent_aligned
  - swingbot/core/scanning/analyze.py:veto_bullish_for
  - swingbot/core/edge/gates.py:pullback_dryup_blocks
  - swingbot/core/edge/gates.py:headroom_active
  - swingbot/admin/guide/live_switches.py:SWITCH_ROWS
  - swingbot/config.py:enforce_gap_reclaim_coupling
  - swingbot/config.py:REGIME_GATES_ENABLED
  - swingbot/config.py:MARKET_REGIME_TICKER
  - swingbot/config.py:RS_GATE
  - swingbot/config.py:RS_LEADER_PERCENTILE
  - swingbot/config.py:RS_LAGGARD_PERCENTILE
  - swingbot/config.py:MTF_ADJACENT_GATE
  - swingbot/config.py:HTF_CONFLUENCE_ENABLED
  - swingbot/config.py:SIGNAL_CONFIRMATION_SCANS
  - swingbot/config.py:MARKET_ENTRY_NEXT_OPEN
  - swingbot/config.py:GAP_RECLAIM_ATR
---

> **In plain words** A gate is a yes-or-no check that can stop a setup from becoming an alert. It never moves a price; it only says "not this one". A gate is used live only after it helped on past prices it was not tuned on. Several gates were built, measured and found not to help: they stay in the code, unused, and the table at the end of this chapter shows which is which, read straight from the settings.

## What a gate does

A [gate](/insights/guide/glossary#gate) drops a setup; it never changes a plan's entry, stop or target. Each one exists because a measured group of past trades lost money or diluted the rest, and each is judged the same way: measured on one stretch of history, then tested once on a later stretch it was never tuned on ([TRAIN and validation](/insights/guide/glossary#train-and-validation)). A gate that passes ships; one that fails stays in the code, unused, so the result is not lost.

Fewer alerts is a cost, not a goal. A gate that raises the win rate but lowers what the average trade earns ([expectancy](/insights/guide/glossary#expectancy-expr)) is not used.

## Gates in the live scan

A level setup from [chapter 4](/insights/guide/levels) must pass:

- the level rules of chapter 4: minimum move, minimum stop distance, reward-to-risk and confluence count;
- confirmation: the same setup seen on {{SIGNAL_CONFIRMATION_SCANS}} consecutive scans before it alerts;
- relative strength (below);
- a confidence level of at least {{MIN_ALERT_CONFIDENCE_LEVEL}}, a score the [market regime](#market-regime) feeds;
- a trade plan that can be built within the stop rules (chapter 7), then the portfolio limits (chapter 8);
- every row of the switch table at the end of this chapter that reads "applied".

A strategy signal from [chapter 5](/insights/guide/strategies#how-a-strategy-alert-is-sent) must pass:

- the [direction and horizon masks](#direction-and-horizon-masks) and the [shared entry gates](#shared-entry-gates) its rule uses;
- for a short, relative strength;
- a plan that can be built within the stop rules (chapter 7);
- every row of the switch table that reads "applied".

<details><summary>Under the hood</summary>

Level setups: the level rules are `requirements._build_requirement_checks`, the confirmation debounce `qualify._confirmed`, the relative-strength block `qualify._rs_blocked` and its twin in `scan_run`. Strategy signals: `entries_for` applies the mask and the regime gate; `strategy_pass._emit_signal` applies the rest.

</details>

## Direction and horizon masks

Each strategy may trade only some directions on some horizons. The live mask, read from the code:

{{gates.list}}

A mask is not a filter on a finished signal: the rule's output is switched off before anything else sees it, so a masked cell produces no signal, no plan and no record. A cell is opened only where the strategy's measured record supports it; a [masked](/insights/guide/glossary#masked) strategy is closed everywhere ([chapter 5](/insights/guide/strategies#masked-strategies)). The glossary's [direction mask](/insights/guide/glossary#direction-mask) has the short version.

<details><summary>Under the hood</summary>

`strategy_types.admits` reads each strategy's `directions`, `horizons`, `horizons_by_direction` and research `cells` in `STRATEGY_GATES`, plus `MASKED_BY_DEFAULT_HORIZONS`. `entries_for` zeroes a masked side right after the entry function runs.

</details>

## Shared entry gates

The five shared gates defined in [chapter 5](/insights/guide/strategies#reading-a-card) are part of each strategy's own entry rule rather than a separate filter: uptrend, medium-term trend, a floor and a ceiling on the average daily range, and volume. They keep a rule from firing in a falling market, in dead-flat or panicking trade, or on a bar few people traded. A rule's card says which it uses; shorts use the downtrend versions.

Their thresholds are constants of the strategy code, not settings: changing one changes every strategy that uses it, and is measured as such.

<details><summary>Under the hood</summary>

`entry_filters.compute_shared_gates(df)` computes every gate once per frame; each entry function combines the series it needs. The thresholds are the module constants `ATR_FLOOR_PCT`, `ATR_CALM_MULT` and `VOL_OK_MULT`.

</details>

## Market regime

The [market regime](/insights/guide/glossary#market-regime) is the broad market's trend: the benchmark named by the setting `MARKET_REGIME_TICKER`, measured against its long-term average. Above the average is bullish, below it bearish; the average's slope is shown beside the result but does not change it. In the live scan it is a score, not a gate: a level setup in line with the regime earns [confidence](/insights/guide/glossary#confidence) points, one against it earns none, and the confidence threshold does the rest.

A true regime gate exists for strategy signals: a table of which strategy may trade in which regime. That table is empty, so no strategy-and-regime pair has been admitted and the gate lets everything through whatever its switch says. Its state is the first row of the switch table at the end of this chapter.

<details><summary>Under the hood</summary>

`regime.get_market_regime` compares the benchmark's close with its long EMA (`ema200` in the code): above is bullish, otherwise bearish. The EMA's slope is computed and reported with the result but is not used to set the trend. The result feeds the "Market regime alignment" factor of `scanning/confidence.py`. The strategy gate is `entry_filters.apply_regime_gate`, active only with `REGIME_GATES_ENABLED` set and a non-empty `strategy_types.REGIME_ALLOW`.

</details>
