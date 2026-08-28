"""Intra-scan and sector-level candidate deduplication."""
from collections import defaultdict

from swingbot import config


def _plans_similar(plan_a, plan_b, tol_pct: float = config.DEDUP_TOLERANCE_PCT) -> bool:
    def close(a, b):
        ref = max(abs(a), abs(b))
        if ref == 0:
            return True
        return abs(a - b) / ref * 100 <= tol_pct

    return close(plan_a.entry, plan_b.entry) and close(plan_a.take_profit, plan_b.take_profit) and close(plan_a.stop_loss, plan_b.stop_loss)


def dedup_scan_items(items: list) -> list:
    groups = defaultdict(list)
    for item in items:
        groups[(item.result.ticker, item.result.trend)].append(item)

    deduped = []
    for _, group_items in groups.items():
        clusters = []
        for item in group_items:
            placed = False
            for cluster in clusters:
                if _plans_similar(cluster[0].plan, item.plan):
                    cluster.append(item)
                    placed = True
                    break
            if not placed:
                clusters.append([item])

        for cluster in clusters:
            cluster.sort(key=lambda it: it.conf.score, reverse=True)
            rep = cluster[0]
            rep.combined_from = [
                {"strategy": it.result.strategy, "horizon_key": it.result.horizon_key, "level": it.conf.level}
                for it in cluster
            ]
            deduped.append(rep)

    return dedup_sector_items(deduped)


def _item_ticker(item) -> str:
    """A real ScanItem keeps its ticker on `.result`, not on itself -- reading
    `item.ticker` raises AttributeError. Lightweight doubles carry it directly,
    so both shapes resolve here rather than at each call site."""
    result = getattr(item, "result", None)
    return getattr(result, "ticker", None) or getattr(item, "ticker", "") or ""


def dedup_sector_items(items: list) -> list:
    """Portfolio-level dedup (Task E78): multiple same-sector signals in one
    scan collapse to the highest-follow-score one, gaining `also_qualifying`
    -- the correlation/sector caps would block the extras anyway, so don't
    tease untakeable trades. Items without a `sector` attribute (every real
    ScanItem today -- sector stamping from universe.sector_map is not wired
    up anywhere yet) pass through untouched, making this a documented no-op
    live until that lands, same as this plan's other pre-registered-but-
    unwired factors (E33's REGIME_ALLOW, E40's blocked sub-step)."""
    by_sector: dict = {}
    passthrough = []
    for it in items:
        sec = getattr(it, "sector", None)
        (by_sector.setdefault(sec, []) if sec else passthrough).append(it)
    out = list(passthrough)
    for sec, group in by_sector.items():
        group.sort(key=lambda i: getattr(i, "follow_score", 0) or 0, reverse=True)
        best = group[0]
        best.also_qualifying = [_item_ticker(g) for g in group[1:]]
        out.append(best)
    out.sort(key=lambda i: getattr(i, "follow_score", 0) or 0, reverse=True)
    return out
