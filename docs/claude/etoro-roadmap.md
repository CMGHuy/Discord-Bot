# eToro roadmap (decided 2026-10-10)

Partner's stated plan, in order:

1. **Now:** a place to configure the eToro keys, left empty. Done:
   `ETORO_USER_KEY` / `ETORO_API_KEY` in `swingbot/config.py` (section "eToro
   Paper Trading"), `.env.example`, `tests/infra/test_config_etoro.py`. Nothing
   reads them yet.
2. **Near:** issue the bot's trade plans to an eToro **demo** account through the
   eToro Public API, alongside the bomeo-capital.com page. Needs its own spec
   (`Edge: none (integrity)`), demo-only, one `prepare-trade` -> `place-trade`
   per explicit approval unless the spec durably authorises automation.
3. **Far:** real-money trades via the same API, only once the plan performance
   is acceptable: consecutive monthly profits, better win rate, more profit,
   less loss. The partner decides when; no agent flips this on its own.

Rules until stage 3 is explicitly unlocked:
- Always `account: "demo"`; never `real`, never `execute-write` to force a trade.
- Keys only in `.env` (hot-reloaded, `sensitive=True`); never committed, logged
  or pasted in chat. The skill's embedded `x-api-key` is not a project secret.
- swingbot itself stays "paper trades only" for its internal ledger; the eToro
  demo account is an additional mirror, not a replacement for it.
- Pooled expectancy / win-rate gates (`backtest-methodology.md`) still decide
  whether a strategy's plans are worth issuing at all.
