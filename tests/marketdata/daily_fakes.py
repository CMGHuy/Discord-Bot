"""v171 D4 test fakes: one raw series served by a fake Alpaca and a fake
yfinance, each adjusted as of the day it is asked (a dividend/split counts
only once it is published), so cache + delta can be compared with a full
fresh download on either basis."""
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from swingbot.core.marketdata import daily_delta as dd

DAYS = pd.bdate_range("2026-01-02", "2026-10-16")
OHLCV = ["Open", "High", "Low", "Close", "Volume"]
PRICE = ["Open", "High", "Low", "Close"]


@dataclass
class Market:
    divs: list = field(default_factory=list)     # (ex_date "YYYY-MM-DD", amount, published date)
    splits: list = field(default_factory=list)   # (date "YYYY-MM-DD", ratio, published date)
    calls: list = field(default_factory=list)
    missing: set = field(default_factory=set)    # {(op, basis)} answered with {}

    def _raw(self) -> pd.DataFrame:
        i = np.arange(len(DAYS), dtype=float)
        close = 100.0 + 5.0 * np.sin(i / 7.0) + 0.05 * i
        return pd.DataFrame({"Open": close - 0.3, "High": close + 1.0, "Low": close - 1.0,
                             "Close": close, "Volume": 1e6 + i}, index=DAYS)

    def frame(self, basis: str, as_of: date, start: date | None = None,
              end: date | None = None) -> pd.DataFrame:
        df = self._raw()
        df = df[df.index.date <= as_of].copy()
        acts = pd.DataFrame(0.0, index=df.index, columns=["Dividends", "Stock Splits"])
        for ex, amount, pub in self.divs:
            if pub <= as_of:
                before = df.index < pd.Timestamp(ex)
                df.loc[before, PRICE] *= 1.0 - amount / df.loc[before, "Close"].iloc[-1]
                acts.loc[pd.Timestamp(ex), "Dividends"] = amount
        for d, ratio, pub in self.splits:
            if pub <= as_of:
                before = df.index < pd.Timestamp(d)
                df.loc[before, PRICE] /= ratio
                df.loc[before, "Volume"] *= ratio
                acts.loc[pd.Timestamp(d), "Stock Splits"] = ratio
        if basis == dd.BASIS_YF:
            df = df.join(acts)
        if start is not None:
            df = df[df.index.date >= start]
        if end is not None:
            df = df[df.index.date <= end]
        df.attrs["source"] = "alpaca" if basis == dd.BASIS_ALPACA else "yfinance"
        return df

    def providers(self, as_of: date):
        def window(tickers, start, end, basis):
            self.calls.append(("window", basis, start, end, tuple(tickers)))
            if ("window", basis) in self.missing:
                return {}
            return {t: self.frame(basis, as_of, start, end) for t in tickers}

        def full(tickers, basis):
            self.calls.append(("full", basis, tuple(tickers)))
            if ("full", basis) in self.missing:
                return {}
            return {t: self.frame(basis, as_of) for t in tickers}
        return window, full
