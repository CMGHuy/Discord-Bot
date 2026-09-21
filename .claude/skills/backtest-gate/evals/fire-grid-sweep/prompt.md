---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Sweep the RSI strategy's pullback depth: run `python scripts/backtest/tune_strategy.py --strategy "RSI" --grid pullback_atr=0.5,0.75,1.0 --exit-model v2 --scale-out` and tell me which cell wins.
