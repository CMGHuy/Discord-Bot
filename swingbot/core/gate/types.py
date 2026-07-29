"""Result dataclasses shared by every gate module. Pure — no I/O, no config."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class CheckResult:
    check_id: str          # e.g. "htf_trend", "rf_fake_breakout"
    section: str           # "context" | "setup" | "redflag" | "risk" | "timing"
    status: str            # "pass" | "warn" | "fail" | "unknown"
    weight: float          # scoring weight, 0 for pure-info checks
    detail: str            # one human sentence, embed-ready
    evidence: dict = field(default_factory=dict)   # raw numbers the detail cites


def scoreable(checks: Sequence[CheckResult]) -> list[CheckResult]:
    """THE degradation contract: status='unknown' (provider down / not
    computable) is excluded entirely — its weight never enters the
    denominator, so missing data can only widen uncertainty, never
    penalize a candidate."""
    return [c for c in checks if c.status in ("pass", "warn", "fail")]


@dataclass(frozen=True)
class GateResult:
    ticker: str
    strategy: str
    as_of: str                     # ISO date of the signal bar
    checks: tuple[CheckResult, ...]
    score: float                   # 0-100 (G6)
    tier: str                      # "A+" | "A" | "B" | "C"
    hard_blocks: tuple[str, ...]   # check_ids that force C regardless of score
    macro_stale: bool              # snapshot older than TTL at eval time
    advisory_decision: str = "pass"  # what enforce WOULD do — set by decide() (G76)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["checks"] = [asdict(c) for c in self.checks]
        d["hard_blocks"] = list(self.hard_blocks)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GateResult":
        return cls(
            ticker=d["ticker"], strategy=d["strategy"], as_of=d["as_of"],
            checks=tuple(CheckResult(**c) for c in d.get("checks", [])),
            score=float(d["score"]), tier=d["tier"],
            hard_blocks=tuple(d.get("hard_blocks", ())),
            macro_stale=bool(d.get("macro_stale", False)),
            advisory_decision=d.get("advisory_decision", "pass"),
        )
