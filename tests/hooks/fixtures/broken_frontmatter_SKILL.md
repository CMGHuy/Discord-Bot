---
name: veteran-trader
description: Use when reviewing a spec, plan, diff or alert from the veteran-trader seat -- whether a setup is tradeable: fills, gaps, liquidity, regime, session timing, and whether an alert can be placed as resting orders before the open -- or when the expert-reviewer agent is dispatched with role=veteran-trader. Not for whether a lift is statistically real (quant-researcher) and not for position sizing or heat caps (risk-manager).
---

# Veteran trader

Fixture, not a skill: the `description:` above is the one that shipped in
v145. Its inner `: ` makes the unquoted scalar invalid YAML, so the loader
listed the skill as "Veteran trader" and it never triggered.
