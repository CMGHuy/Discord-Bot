"""Pre-registered v93 bearish-arm decision clauses."""
WR_FLOOR, MIN_N, MAX_SCRATCH_SHARE, FOLD_MIN_N, FOLDS_REQUIRED, PLATEAU_MIN_NEIGHBOURS = 50.0, 30, .5, 15, 2, 4


def pooled_stats(trades):
    closed = [trade for trade in trades if trade.outcome in ("win", "loss", "scratch", "timeout")]
    decided = [trade for trade in closed if trade.outcome in ("win", "loss")]
    wins = sum(trade.outcome == "win" for trade in decided)
    returns = [trade.r_multiple for trade in closed if trade.r_multiple is not None]
    return {"n": len(decided), "wins": wins, "losses": len(decided) - wins,
            "win_rate": wins / len(decided) * 100 if decided else None,
            "expectancy_r": sum(returns) / len(returns) if returns else None,
            "scratch_timeout_share": (len(closed) - len(decided)) / len(closed) if closed else None}


def stage1_verdict(pooled, folds):
    good = sum((fold["stats"].get("n") or 0) >= FOLD_MIN_N and (fold["stats"].get("expectancy_r") or 0) > 0 for fold in folds)
    clauses = {"wr": (pooled.get("win_rate") or 0) >= WR_FLOOR, "exp_r": (pooled.get("expectancy_r") or 0) > 0,
               "n": pooled.get("n", 0) >= MIN_N, "scratch_share": (pooled.get("scratch_timeout_share") or 1) <= MAX_SCRATCH_SHARE,
               "folds": good >= FOLDS_REQUIRED}
    return {"clears": all(clauses.values()), "clauses": clauses, "good_folds": good}


def stage2_allowed(pooled):
    return (pooled.get("expectancy_r") or 0) > 0 and (pooled.get("win_rate") or 100) < WR_FLOOR


def neighbour_subsets(subset, all_horizons):
    order = list(all_horizons); indexes = sorted(order.index(h) for h in subset); output = []
    output.extend(tuple(order[j] for j in indexes if j != index) for index in indexes if len(indexes) > 1)
    if indexes[0] > 0: output.append(tuple([order[indexes[0] - 1]] + [order[j] for j in indexes]))
    if indexes[-1] < len(order) - 1: output.append(tuple([order[j] for j in indexes] + [order[indexes[-1] + 1]]))
    return output


def plateau_ok(subset_stats, neighbour_stats):
    return len(neighbour_stats) >= PLATEAU_MIN_NEIGHBOURS and all((row.get("win_rate") or 0) >= WR_FLOOR and row.get("n", 0) >= MIN_N for row in neighbour_stats)
