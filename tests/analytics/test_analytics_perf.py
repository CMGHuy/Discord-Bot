"""Sanity bound on build_snapshot's cost over a realistically-large trade
history -- generous enough that normal CI noise (a slow shared runner, a
cold Python import) doesn't flake it, but tight enough to catch an
accidentally-O(n^2) aggregation (e.g. a per-row full-list rescan) before
it ships."""
import time

from swingbot.core.analytics.snapshots import build_snapshot

N_SYNTHETIC_TRADES = 5000


def _synthetic_trades(n: int) -> list[dict]:
    strategies = ["Fibonacci", "EMA Crossover", "VWAP", "Support/Resistance", "RSI"]
    tiers = ["A", "B", "C"]
    trades = []
    for i in range(n):
        status = "win" if i % 3 != 0 else "loss"
        day = 1 + (i % 27)
        month = 1 + (i // 27) % 12
        trades.append({
            "id": f"synthetic-{i}",
            "ticker": f"SYM{i % 50}",
            "target_sources": [strategies[i % len(strategies)]],
            "strategy": strategies[i % len(strategies)],
            "status": status,
            "direction": "bullish" if i % 2 == 0 else "bearish",
            "entry": 100.0,
            "stop_loss": 95.0 if i % 2 == 0 else 105.0,
            "exit_price": (104.0 if i % 2 == 0 else 96.0) if status == "win"
                          else (96.0 if i % 2 == 0 else 104.0),
            "realized_pnl_amount": 80.0 if status == "win" else -40.0,
            "opened_at": f"2025-{month:02d}-{day:02d}T10:00:00+00:00",
            "closed_at": f"2025-{month:02d}-{min(day + 2, 28):02d}T10:00:00+00:00",
            "horizon_key": "4w",
            "tier": tiers[i % 3],
            "badge": "VALIDATED" if i % 3 == 0 else "WEAK",
            "source": "confluence" if i % 2 == 0 else "strategy",
            "confidence_level": 1 + (i % 5),
            "quality_score": i % 100,
        })
    return trades


def test_build_snapshot_5000_trades_under_2_seconds():
    trades = _synthetic_trades(N_SYNTHETIC_TRADES)
    start = time.perf_counter()
    snap = build_snapshot(trades, starting_balance=10_000.0, registry_entries=[])
    elapsed = time.perf_counter() - start
    assert snap["overall"]["n"] == N_SYNTHETIC_TRADES
    assert elapsed < 2.0, f"build_snapshot took {elapsed:.2f}s for {N_SYNTHETIC_TRADES} trades (budget: 2.0s)"
