"""v190 §2.4: membership-symbol rename ranges for Alpaca history.

Fetch the Alpaca symbol over [start, end), store under the membership symbol,
and retain the membership symbol's identity reference. Unmapped members remain
listed under no_bars in the integrity report.
"""
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path

import pandas as pd

ALIASES_PATH = Path("data/universe/symbol_aliases.json")


@dataclass(frozen=True)
class Alias:
    member: str
    alpaca: str
    start: str
    end: str | None

    def clip(self, frame: pd.DataFrame | None) -> pd.DataFrame | None:
        if frame is None or frame.empty:
            return None
        dates = frame.index.normalize()
        start = pd.Timestamp(self.start, tz=dates.tz)
        keep = dates >= start
        if self.end is not None:
            keep &= dates < pd.Timestamp(self.end, tz=dates.tz)
        clipped = frame[keep]
        return clipped if not clipped.empty else None


def _date(value, path: Path) -> str:
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{path}: expected an ISO YYYY-MM-DD date") from exc
    return value


def _alias(entry, path: Path) -> Alias:
    if not isinstance(entry, dict):
        raise ValueError(f"{path}: alias entry must be an object")
    symbols = [entry.get(key) for key in ("member", "alpaca")]
    if any(not isinstance(s, str) or not s.strip() for s in symbols):
        raise ValueError(f"{path}: member and alpaca symbols are required")
    member, alpaca = [s.strip().upper() for s in symbols]
    start = _date(entry.get("start"), path)
    end = entry.get("end")
    if end is not None:
        end = _date(end, path)
        if end <= start:
            raise ValueError(f"{path}: end must follow start")
    if member == alpaca:
        raise ValueError(f"{path}: member and alpaca must differ")
    return Alias(member, alpaca, start, end)


def load_aliases(path: Path) -> dict[str, Alias]:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"{path}: invalid JSON alias table") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("aliases"), list):
        raise ValueError(f"{path}: expected an object with an aliases list")
    result = {}
    for entry in doc["aliases"]:
        alias = _alias(entry, path)
        if alias.member in result:
            raise ValueError(f"{path}: duplicate member {alias.member}")
        result[alias.member] = alias
    return result
