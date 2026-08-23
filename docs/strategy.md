# Strategy

How the bot decides. Split into three files so a session reads only the part it
needs — see `CLAUDE.md` -> "Token discipline".

| File | Covers |
|---|---|
| [strategy-signals.md](strategy-signals.md) | The core idea (next support/resistance, not indicator crossovers), levels from every method at once, the three extra filters, duplicate merging, `!check`, and the 10 swing horizons |
| [strategy-plans.md](strategy-plans.md) | Entry / target / stop construction, the minimum-stop and tight-stop rules, the confluence-based confidence score, what every alert contains, live monitoring and trade tracking |
| [strategy-gates.md](strategy-gates.md) | Market regime filter, the relative-strength gate (measured, ON), horizon-to-horizon trend alignment (measured, OFF), ticker symbol resolution, command hints |

Code is authoritative where these tables lag — the horizons themselves live in
`swingbot/core/market/strategy_types.py:HORIZONS`.
