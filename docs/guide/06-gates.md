---
title: Filters and gates
slug: gates
order: 6
reviewed_for: 2.19.5
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

- the level rules of [chapter 4](/insights/guide/levels#the-minimum-move): minimum move, minimum stop distance, reward-to-risk and confluence count;
- confirmation: the same setup seen on {{SIGNAL_CONFIRMATION_SCANS}} consecutive scans before it alerts;
- relative strength (below);
- a confidence level of at least {{MIN_ALERT_CONFIDENCE_LEVEL}}, a score the [market regime](#market-regime) feeds;
- a trade plan that can be built within the stop rules ([chapter 7](/insights/guide/trade-plan#the-stop-distance-cap-and-the-clamp)), then the portfolio limits ([chapter 8](/insights/guide/sizing-risk#portfolio-and-correlated-heat));
- every row of the switch table at the end of this chapter that reads "applied".

A strategy signal from [chapter 5](/insights/guide/strategies#how-a-strategy-alert-is-sent) must pass:

- the [direction and horizon masks](#direction-and-horizon-masks) and the [shared entry gates](#shared-entry-gates) its rule uses;
- for a short, relative strength;
- a plan that can be built within the stop rules ([chapter 7](/insights/guide/trade-plan#the-stop-distance-cap-and-the-clamp));
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

## Relative strength

[Relative strength](/insights/guide/glossary#relative-strength) ranks a stock's recent move against the benchmark and its sector, as a percentile of the scanned universe. The gate's switch reads {{RS_GATE}}, and it has two arms:

- **Long arm**: a long needs a percentile of at least {{RS_LEADER_PERCENTILE}}. When measured, this arm cut good trades with the bad at every threshold tried, so it ships at its floor, where every long passes.
- **Short arm**: a short needs a percentile of at most {{RS_LAGGARD_PERCENTILE}}: the bot shorts laggards, not leaders. This arm passed its validation test with a small win-rate gain for a small cut in alerts: a measured improvement, not a large edge.

Currencies, futures, indices and crypto have no meaningful comparison with the stock benchmark and are exempt, as is every setup in a scan where the benchmark could not be fetched.

<details><summary>Under the hood</summary>

`edge/rs_gate.rs_verdict` returns pass, block or exempt. Level setups are checked in `scan_run` and `qualify._rs_blocked` while `RS_GATE` is set; the strategy pass checks bearish signals only, in `strategy_pass._rs_blocked`, without reading `RS_GATE`.

</details>

## Higher-horizon alignment

Two readings compare a setup with the trend of a longer horizon ([chapter 4](/insights/guide/levels#higher-horizon-alignment)):

- **Adjacent-horizon gate**: drops a setup when the next horizon up trends against it, such as a short-horizon long while the longer horizon falls. In its validation test it lowered the win rate slightly and was not adopted; whether it applies now is in [the switch table](#measured-not-used).
- **Higher-timeframe bias**, now {{HTF_CONFLUENCE_ENABLED}}: compares the stock with its own longer moving average and marks a counter-trend alert with a warning. It flags the alert and feeds the plan's quality score, and it never removes an alert.

<details><summary>Under the hood</summary>

The gate is `mtf.adjacent_aligned`, called in `analyze` only while `MTF_ADJACENT_GATE` is set; only an "opposed" verdict drops a scenario. The bias is `regime.get_htf_bias`, computed only while `HTF_CONFLUENCE_ENABLED` is set.

</details>

## Post-signal fill vetoes

Two linked settings change how a market plan is filled once the signal is decided. The first makes the plan wait for the next session's open instead of entering at the scan price. The second adds a veto: if that open has already gapped toward the stop by a set multiple of the ATR, the plan waits for price to come back to its planned entry during that session, or is cancelled at the close. The second works only with the first; set alone, it is ignored and an error is logged.

Because they act after the signal, they are judged as a change to the fill, not as a new entry idea. Measured, the reclaim veto raised the win rate but cut the average result per trade, because the trades it re-priced turned from winners into roughly break-even ones; it was not adopted. Its state is the "Next-open market entry and gap reclaim" row of [the switch table](#measured-not-used).

<details><summary>Under the hood</summary>

The settings are `MARKET_ENTRY_NEXT_OPEN` and `GAP_RECLAIM_ATR`; `config.enforce_gap_reclaim_coupling` zeroes the reclaim threshold, with an error log, while next-open entry is not set.

</details>

## Measured, not used

Every gate and exit rule that was built and measured, with its settings, their values now and whether the live scan applies the rule. The table is read from the settings each time the page loads, so a switch flipped on the server shows here at once:

{{gates.switches}}

"Measured, not used" means the rule is in the code and was tested, and the test did not justify using it. What the measurements found:

- The dead-cat bounce veto (no long when the chart looks like a dead-cat bounce) and the headroom veto (no setup when another level blocks the path to the first target) are built but off by default. The first passed its first stage and failed validation; the second showed no lift for strategies and changed nothing measurable for level setups.
- The pullback volume dry-up veto showed no lift for either path.
- No earnings blackout window cleared the rule.
- Minimum touches for Support/Resistance and extra confirm bars for MA Ribbon each left the win rate below the floor a strategy must clear, and a longer turn for RSI Divergence made its results worse; the fair value gap level modes were refused at the first stage.
- Data-driven stops and the stall exit could not be measured as built, and the runner structure exit was refused at its early stages; none of them is adopted.

A row that reads "applied" is in use, whatever this list says about how it was measured.

<details><summary>Under the hood</summary>

`live_switches.SWITCH_ROWS` lists each row's settings and the test that decides "applied". The full records are the closed pre-registration rows in `docs/claude/backtest-methodology.md`.

</details>
