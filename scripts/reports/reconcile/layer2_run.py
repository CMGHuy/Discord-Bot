"""v232 layer 2 runner: the unchanged live scan code over the window (spec ### Layer 2).

Cross-sectional per decision date, so one checkpoint per lane. Frames: the adjusted store,
the bars the live scan saw. Only layer2.adapt output is stored (partner decision 4).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from swingbot import config
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from swingbot.core.marketdata import history_store, universe
from swingbot.core.marketdata.pit_membership import load_intervals
from swingbot.core.scanning import scan_replay
from swingbot.core.scanning.short_candidates import admitted_short_modes, extra_symbols

from . import layer2

SNAPSHOT_FN = scan_replay.ReplaySpec(base_tickers=(), horizons=()).snapshot_fn


def replay_tickers(export) -> tuple[str, ...]:
    """The current watchlist plus every ticker in a live plan or a gate rejection."""
    tickers = set(export.watchlist) | {rec.ticker for rec in export.records}
    tickers |= {r["ticker"] for r in export.rejections if r.get("ticker")}
    return tuple(sorted(tickers))


def live_short_modes() -> frozenset[str]:
    """The SHORT extra lane's modes as the live configuration has them today."""
    return frozenset(admitted_short_modes(config))


def _sector_etfs() -> tuple[str, ...]:
    from swingbot.core.scanning.fetch import _etf_symbol_of_sector
    return tuple(sorted(set(_etf_symbol_of_sector().values())))


def _pit_members() -> tuple[str, ...]:
    return tuple(sorted(load_intervals(os.path.join(universe.UNIVERSE_DIR,
                                                    "sp500_membership.csv"))))


def reference_symbols(modes) -> tuple[str, ...]:
    """The benchmark and sector ETFs; with an extra lane on, the point-in-time members too."""
    symbols = {config.MARKET_REGIME_TICKER, *_sector_etfs()}
    if modes:
        symbols.update(_pit_members())
    return tuple(sorted(symbols))


def load_frames(symbols, *, load=history_store.load) -> tuple[dict, list[str]]:
    """({symbol: daily frame}, [symbols the store lacks]), in the order given."""
    frames: dict = {}
    missing: list[str] = []
    for symbol in symbols:
        try:
            frame = load(symbol, "daily")
        except history_store.MissingStoreError:
            frame = None
        if frame is None:
            missing.append(symbol)
        else:
            frames[symbol] = frame
    return frames, missing


def _has_bar(frame, day: str) -> bool:
    return frame is not None and pd.Timestamp(day) in frame.index


def _missing_days(frames: dict, tickers, days) -> dict:
    counts = {t: sum(not _has_bar(frames.get(t), d) for d in days) for t in tickers}
    return {t: n for t, n in sorted(counts.items()) if n}


def _panel_gaps(frames: dict, days) -> dict:
    panel = (config.MARKET_REGIME_TICKER,) + _sector_etfs()
    gaps = {d: [s for s in panel if not _has_bar(frames.get(s), d)] for d in days}
    return {d: symbols for d, symbols in gaps.items() if symbols}


def _extra_gaps(frames: dict, days, base_tickers, snapshot_fn) -> tuple[list, dict]:
    no_snapshot: list = []
    missing: dict = {}
    for day in days:
        snapshot = snapshot_fn(day)
        if snapshot is None:
            no_snapshot.append(day)
            continue
        n = sum(not _has_bar(frames.get(s), day) for s in extra_symbols(snapshot, base_tickers))
        if n:
            missing[day] = n
    return no_snapshot, missing


def coverage(frames, window, *, base_tickers, modes, snapshot_fn) -> dict:
    """Which decision sessions lack an input: base bars, the panel, the snapshot, extra bars."""
    spy = frames.get(config.MARKET_REGIME_TICKER)
    days = scan_replay.decision_dates(spy, window) if spy is not None else []
    no_snapshot, extra_missing = ([], {})
    if modes:
        no_snapshot, extra_missing = _extra_gaps(frames, days, base_tickers, snapshot_fn)
    return {"window": list(window), "sessions": len(days), "spy_missing": spy is None,
            "base_missing_days": _missing_days(frames, base_tickers, days),
            "panel_gaps": _panel_gaps(frames, days), "snapshot_missing": no_snapshot,
            "extra_missing": extra_missing}


def params_digest(params) -> str:
    blob = json.dumps(dataclasses.asdict(params), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _meta(lane: str, window, params, base_tickers: tuple, modes) -> dict:
    tickers = hashlib.sha256("\n".join(base_tickers).encode("utf-8")).hexdigest()
    return {"kind": "meta", "lane": lane, "window": list(window),
            "params_digest": params_digest(params), "tickers_digest": tickers,
            "modes": sorted(modes)}


def _read_lane(path: Path, meta: dict) -> list | None:
    if not path.is_file():
        return None
    try:
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except json.JSONDecodeError:
        return None
    if len(rows) < 2 or rows[0] != meta or rows[-1] != {"kind": "end", "n": len(rows) - 2}:
        return None
    return [layer2.ReplaySignal.from_dict(row["signal"]) for row in rows[1:-1]]


def _write_lane(path: Path, meta: dict, signals: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    body = ([meta] + [{"kind": "signal", "signal": s.to_dict()} for s in signals]
            + [{"kind": "end", "n": len(signals)}])
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for row in body:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _lane(name: str, replay, meta: dict, checkpoint_dir: Path, out) -> list:
    path = Path(checkpoint_dir) / f"lane-{name}.jsonl"
    cached = _read_lane(path, meta)
    if cached is not None:
        out(f"layer 2 lane {name}: {len(cached)} signals from {path.name}")
        return cached
    out(f"layer 2 lane {name}: replaying {meta['window'][0]}..{meta['window'][1]}")
    signals = [layer2.adapt(alert) for alert in replay().alerts]
    _write_lane(path, meta, signals)
    out(f"layer 2 lane {name}: {len(signals)} signals written to {path.name}")
    return signals


def run_layer2(frames, window: tuple[str, str], params, *, base_tickers, modes,
               checkpoint_dir: Path, out=print) -> list:
    """Base lane, then the extra SHORT lane when `modes` is non-empty; one checkpoint each."""
    if config.MARKET_REGIME_TICKER not in frames:
        raise ValueError(f"no {config.MARKET_REGIME_TICKER} frame: the replay has no dates")
    base = tuple(sorted(base_tickers))
    spec = scan_replay.ReplaySpec(base_tickers=base, horizons=tuple(LEGACY_HORIZONS))
    lanes = {"base": lambda: scan_replay.replay_base_scan(frames, window, params, spec=spec)}
    if modes:
        lanes["extra"] = lambda: scan_replay.replay_extra_short_scan(
            frames, window, params, spec=spec, allowed_modes=frozenset(modes))
    signals: list = []
    for name, replay in lanes.items():
        signals.extend(_lane(name, replay, _meta(name, window, params, base, modes),
                             checkpoint_dir, out))
    return signals
