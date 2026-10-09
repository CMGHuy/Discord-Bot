"""v144: the outlook run's result, as plain data for the renderers and posters."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OutlookLine:
    """One digest row: an issued plan, a watch name or a near-miss."""
    ticker: str
    direction: str
    strategy: str
    entry: float
    stop: float
    target: float
    risk_dollars: float | None = None    # issued plans only
    reason: str | None = None            # near-misses only


@dataclass
class OutlookResult:
    run_date: dt.date                    # the Berlin date of the 23:30 slot
    target: dt.date | None               # the session D the plans are valid for; None = no session tomorrow
    bar_date: dt.date | None = None      # the closed bar the scan read (Sunday -> Friday)
    unavailable: str | None = None       # set = nothing was issued, and this says why
    regime_lines: list[str] = field(default_factory=list)
    plans: list[OutlookLine] = field(default_factory=list)
    watch: list[OutlookLine] = field(default_factory=list)
    near_misses: list[OutlookLine] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    alerts: list[tuple] = field(default_factory=list)   # (embed, chart_path, plan, simple_embed)
