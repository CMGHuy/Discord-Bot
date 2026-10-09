"""Hand-built v143 trade rows. No test_ prefix: not collected."""
from swingbot.core.backtesting import fvg_diagnostic as fd


def row(year="2020", fav=True, outcome="win", r=1.0, role="target", quality=60, **kw):
    out = {"outcome": outcome, "r": r, "exit_mix": "tp1+runner_trail" if outcome == "win" else "stop"}
    features = {"fvg_role": role, "gap_age": 5 if fav else 50, "gap_height_atr": 1.0,
                "displacement": True, "gap_open": True, "stop_atr": 1.5, "quality": quality,
                "trend_aligned": True, "volatility": 0.02, "earnings_distance": 10}
    features.update(kw)
    return {"ticker": "AAA", "horizon_key": "2w", "signal_date": f"{year}-03-02", "year": year,
            "direction": "bullish", "features": features,
            "outcomes": {"live": out, "g125": out, "g100": out}}


def table(fav_per_year=40, fav_wins=24, unfav_r=-0.5, win_r=1.0, loss_r=None):
    """Favourable side: per year `fav_wins` wins at `win_r` (an int, or a
    {year: wins} dict) and the rest losses at -1R (`loss_r`: {year: r}
    overrides). Unfavourable side: 10 losses a year at `unfav_r`."""
    rows = []
    for year in fd.YEARS:
        wins = fav_wins[year] if isinstance(fav_wins, dict) else fav_wins
        lost = (loss_r or {}).get(year, -1.0)
        rows += [row(year, outcome="win", r=win_r) for _ in range(wins)]
        rows += [row(year, outcome="loss", r=lost) for _ in range(fav_per_year - wins)]
        rows += [row(year, fav=False, outcome="loss", r=unfav_r) for _ in range(10)]
    return rows
